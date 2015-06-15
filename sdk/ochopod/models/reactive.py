#
# Copyright (c) 2015 Autodesk Inc.
# All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import hashlib
import json
import logging
import pykka
import requests
import time

from copy import deepcopy
from flask import Flask, request
from kazoo.exceptions import NoNodeError, NodeExistsError
from ochopod.api import Reactive
from ochopod.core.core import ROOT, SAMPLING
from ochopod.core.fsm import Aborted, FSM, diagnostic, shutdown
from ochopod.models.piped import _Cluster
from ochopod.watchers.local import Watcher as Local
from ochopod.watchers.remote import Watcher as Remote
from requests.exceptions import Timeout
from threading import Thread

#: Our ochopod logger.
logger = logging.getLogger('ochopod')


class _Post(Thread):
    """
    Ancillary actor performing a HTTP POST to send a control request to a pod. We subclass :class:`threading.Thread`
    to support parallelism.
    """

    def __init__(self, key, url, js=None, timeout=60.0):
        super(_Post, self).__init__()

        self.code = None
        self.js = js
        self.key = key
        self.url = url
        self.timeout = timeout

    def run(self):

        try:
            #
            # - simply POST the control request to the pod
            # - any failure to reach the pod or timeout will be silently trapped (but the thread will
            #   join() with an empty code)
            #
            logger.debug('control -> %s' % self.url)
            reply = requests.post(self.url, data=json.dumps(self.js), timeout=self.timeout)
            self.code = reply.status_code
            logger.debug('control <- %s (HTTP %d)' % (self.url, self.code))

        except Timeout:

            #
            # - just log something
            # - the thread will simply return a None for return code
            #
            logger.debug('control <- %s (timeout)' % self.url)

    def join(self, timeout=None):

        Thread.join(self)
        return self.key, self.code


class Actor(FSM, Reactive):
    """
    Implementation for our clustering model. This is run by the leader pod after it obtains the lock and shares
    the same Kazoo driver.
    """

    def __init__(self, zk, id, hints, scope, tag, port, latch):
        super(Actor, self).__init__()

        self.hints = hints
        self.id = id
        self.latches.append(latch)
        self.path = 'model (reactive)'
        self.port = port
        self.scope = scope
        self.snapshots = dict.fromkeys(self.depends_on, {})
        self.tag = tag
        self.updated = 0
        self.watchers = []
        self.zk = zk

    def reset(self, data):

        #
        # - make sure we kill our watcher actors before terminating
        #
        for watcher in self.watchers:
            shutdown(watcher)

        self.hints['status'] = ''
        super(Actor, self).reset(data)

    def initial(self, data):

        #
        # - the /hash node is where we store the md5 hash of all our pods + their dependencies
        # - the /snapshot node is where we store the last known state of our pods (e.g where they run from and what
        #   their port mapping is)
        #
        try:
            self.zk.create('%s/%s.%s/snapshot' % (ROOT, self.scope, self.tag), value='{}', ephemeral=True)

        except NodeExistsError:
            pass

        #
        # - start the watch our local pods
        # - this ancillary actor will piggy-back on our zk client and use it to query our pod
        #   information on a regular basis
        #
        data.dirty = 0
        data.last = None
        data.next_probe = 0
        self.snapshots['local'] = {}
        self.watchers = [Local.start(self.actor_ref, self.zk, self.scope, self.tag)]

        #
        # - add a set of extra watchers for our dependencies
        # - make sure to look for clusters within our own namespace
        # - start spinning (the watcher updates will be processed in there)
        #
        self.watchers += [Remote.start(self.actor_ref, self.zk, self.scope, tag) for tag in self.depends_on]
        logger.debug('%s : watching %d dependencies' % (self.path, len(self.depends_on)))
        logger.info('%s : leading for cluster %s.%s' % (self.path, self.scope, self.tag))
        return 'spin', data, 0

    def spin(self, data):

        #
        # - if the termination trigger is set or if we lost our connection, abort immediately
        # - this will free the lock and another controller will take the lead
        #
        if self.terminate:
            raise Aborted('terminating')
        
        #
        # - if it is time to run the probe callback do it now
        # - schedule the next one
        #
        now = time.time()
        if self.updated:

            #
            # - the update trigger is on
            # - unset it and query the last recorded hash
            # - any difference with what we have means we need to schedule a configuration
            #
            self.updated = 0
            last, stats = self.zk.get('%s/%s.%s/hash' % (ROOT, self.scope, self.tag))
            latest = self._md5()
            bad = latest != last
            if bad and not data.dirty:

                #
                # - the hash changed, switch the dirty trigger on
                # - this will start the countdown to configuration (which can be aborted if we fall back
                #   on the same hash again, typically after a transient zookeeper connection loss)
                #
                logger.info('%s : hash changed, configuration in %2.1f seconds' % (self.path, self.damper))
                logger.debug('%s : hash -> %s' % (self.path, latest))
                data.next = now + self.damper
                data.dirty = 1

            elif not bad:

                #
                # - this case would typically map to a pod losing cnx to zk and joining again later
                # - based on how much damper we allow we can bridge transient idempotent changes
                # - very important -> make sure we set the snapshot (which could have been reset to {})
                # - don't also forget to set data.last to enable probing
                #
                data.dirty = 0
                pods = self.snapshots['local']
                js = \
                    {
                        'pods': pods,
                        'dependencies': {k: v for k, v in self.snapshots.items() if k != 'local'}
                    }

                data.last = js
                data.last['key'] = str(self.id)
                self.zk.set('%s/%s.%s/snapshot' % (ROOT, self.scope, self.tag), json.dumps(pods))
                logger.debug('%s : pod update with no hash impact (did we just reconnect to zk ?)' % self.path)

        if not data.dirty:

            #
            # - all cool, the cluster is configured
            # - set the state as 'leader'
            # - fire a probe() if it is time to do so
            #
            self.hints['state'] = 'leader'
            if data.last and now > data.next_probe:
                try:

                    #
                    # - pass the latest cluster data to the probe() call
                    # - if successful (e.g did not assert) set the status to whatever the callable returned
                    # - unset if nothing was returned
                    #
                    snippet = self.probe(_Cluster(data.last))
                    self.hints['status'] = str(snippet) if snippet else ''

                except AssertionError as failure:

                    #
                    # - set the status to the assert message
                    #
                    self.hints['status'] = '* %s' % failure

                except Exception as failure:

                    #
                    # - something blew up in probe(), set the status accordingly
                    #
                    self.hints['status'] = '* probe() failed (check the code)'
                    logger.warning('%s : probe() failed -> %s' % (self.path, diagnostic(failure)))

                data.next_probe = now + self.probe_every
                if self.hints['status']:
                    logger.debug('%s : probe() -> "%s"' % (self.path, self.hints['status']))

        else:

            #
            # - trigger the configuration procedure
            #
            self.hints['state'] = 'leader (configuration pending)'
            remaining = max(0, data.next - now)
            self.hints['status'] = '* configuration in %2.1f seconds' % remaining
            if not remaining:
                return 'config', data, 0

            #
            # - print some cool countdown
            #
            else:
                logger.debug('%s : configuration in %2.1f seconds' % (self.path, remaining))

        return 'spin', data, SAMPLING

    def probe(self, cluster):
        pass

    def config(self, data):

        try:

            #
            # - make sure we persist the latest snapshot to zk
            # - order the dict to make sure we always assign the same index to the same pod
            # - unroll our pods into one URL list
            #
            data.last = None
            pods = self.snapshots['local']
            self.hints['state'] = 'leader (configuring)'
            self.hints['status'] = '* configuring %d pods' % len(pods)

            #
            # - map each pod to its full control URL
            # - this will allow us to send requests directly without worrying about remapping the control port
            # - pay attention to order the pod list to guarantee consistent sequencing
            #
            logger.info('%s : configuring (%d pods, i/o port %d)' % (self.path, len(pods), self.port))
            ordered = sorted(pods.items())
            local = str(self.port)
            urls = \
                {key: ('http://%s:%d' % (js['ip'], js['ports'][local])) for key, js in ordered if local in js['ports']}

            #
            # - they should all expose their control port
            #
            assert len(urls) == len(pods), '1+ pods are not exposing TCP %d (user error ?)' % self.port

            #
            # - this is the basic json payload we'll send to all our pods
            # - it contains all the information they need to know to carry their configuration out
            # - we'll also add each pod identifier + index
            #
            js = \
                {
                    'pods': pods,
                    'dependencies': {k: v for k, v in self.snapshots.items() if k != 'local'}
                }

            def _control(task):
                threads = []
                for key, url in urls.items():

                    #
                    # - add the key for each pod
                    # - this json payload will be sent over and turned into a Cluster instance on the other side
                    # - inflate the receiving timeout a bit
                    #
                    payload = deepcopy(js)
                    payload['key'] = key
                    seconds = self.grace * 1.25
                    thread = _Post(key, '%s/control/%s/%d' % (url, task, self.grace), js=payload, timeout=seconds)
                    threads.append(thread)

                if self.sequential:

                    #
                    # - start each HTTP POST thread and join immediately
                    #
                    def _start_join():
                        thread.start()
                        return thread.join()

                    logger.debug('%s : -> /control/%s (%d pods, sequential)' % (self.path, task, len(pods)))
                    return [_start_join() for thread in threads]

                else:

                    #
                    # - start all the HTTP POST threads at once
                    # - join them one by one
                    #
                    for thread in threads:
                        thread.start()

                    logger.debug('%s : -> /control/%s (%d pods)' % (self.path, task, len(pods)))
                    return [thread.join() for thread in threads]

            #
            # - perform a pre-check, typically to make sure all our dependencies are there
            # - if this fails for whatever reason we'll postpone the configuration to later
            # - note that any dead pod will fail this test
            #
            replies = _control('check')
            dead = [key for key, code in replies if code == 410]
            if dead:
                logger.warning('%s : dropping %d dead pods' % (self.path, len(dead)))
                for key in dead:
                    del pods[key]
                    del urls[key]

            assert all(code in [200, 410] for _, code in replies), '1+ pods failing the pre-check or unreachable'
            if pods:

                #
                # - we have at least one pod alive
                # - if a full shutdown has been requested start by sending a /off to each pod in order
                #
                if self.full_shutdown:
                    _control('off')

                #
                # - send a /on to each pod in order to configure and (re-)start them
                # - note we include an extra 'index' integer to the payload passed to the pod (this index
                #   can be used to tag the pod in logs or perform specific setup procedures)
                #
                logger.debug('%s : json payload ->\n%s' % (self.path, json.dumps(js, indent=4, separators=(',', ': '))))
                logger.info('%s : asking %d pods to configure' % (self.path, len(pods)))
                replies = _control('on')
                assert all(code == 200 for _, code in replies), '1+ pods failing to configure or unreachable'

                #
                # - operation successful -> ask each pod to run its configured() callback
                # - just fire & forget
                #
                _control('ok')

            #
            # - in any case update the md5 hash
            # - update also our /snapshot node (which will propagate if this cluster is a dependency for somebody else)
            #
            latest = self._md5()
            local = json.dumps(pods)
            self.zk.set('%s/%s.%s/snapshot' % (ROOT, self.scope, self.tag), local)
            self.zk.set('%s/%s.%s/hash' % (ROOT, self.scope, self.tag), latest)
            logger.debug('%s : new hash -> %s' % (self.path, latest))
            logger.info('%s : configuration complete (%d pods alive)' % (self.path, len(pods)))

            #
            # - all cool, we can now unset our trigger
            # - keep track of the cluster description
            # - go back to spinning & force a call to probe() right away
            #
            data.dirty = 0
            data.last = js
            data.last['key'] = str(self.id)
            data.next_probe = 0

        except AssertionError as failure:

            #
            # - any assert aborts the procedure
            # - leave the trigger on and reset the timestamp to re-attempt
            #
            logger.warn('%s : configuration failed -> %s' % (self.path, diagnostic(failure)))
            self.hints['state'] = 'leader (configuration pending)'
            data.next = time.time() + self.damper
            data.last = None

        return 'spin', data, SAMPLING

    def specialized(self, msg):

        assert 'request' in msg, 'bogus message received ?'
        req = msg['request']
        if req == 'snapshot update':

            #
            # - a snapshot changed value (either us or some dependency)
            # - update our snapshot dict
            # - set the trigger to force a comparison against the last recorded hash
            #
            key = msg['key']
            self.snapshots[key] = msg['pods']
            self.updated = 1

        elif req == 'watcher failure':

            #
            # - one of our watcher actors failed to read from zk
            # - force a termination to re-attempt a connection to zk (and re-register the pod)
            #
            logger.debug('%s : watcher failure, terminating' % self.path)
            self.terminate = 1

        else:
            super(Actor, self).specialized(msg)

    def _md5(self):

        #
        # - compute the MD5 of our snapshots serialized to json
        # - return something that's readable
        #
        hashed = hashlib.md5()
        hashed.update(json.dumps(self.snapshots))
        return ':'.join(c.encode('hex') for c in hashed.digest())