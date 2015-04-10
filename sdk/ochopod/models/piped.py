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
import json
import logging
import pykka
import time

from collections import deque
from copy import deepcopy
from ochopod.api import Cluster, Piped
from ochopod.core.core import SAMPLING
from ochopod.core.fsm import Aborted, FSM, diagnostic
from pykka import ThreadingFuture
from subprocess import Popen

#: Our ochopod logger.
logger = logging.getLogger('ochopod')

#: Delay in seconds between two health-checks.
SANITY = 5.0


class _Cluster(Cluster):
    """
    Wrapper packaging the leader information in a user-friendly way and providing a dependency lookup
    helper.
    """

    def __init__(self, js):
        super(_Cluster, self).__init__()

        self.key = js['key']
        self.pods = js['pods']
        self.dependencies = js['dependencies']
        self.index = sorted(self.pods.keys()).index(self.key)
        self.seq = self.pods[self.key]['seq']
        self.size = len(self.pods)

    def grep(self, dependency, port, public=False):

        if not dependency in self.dependencies:
            return ''

        out = []
        nodes = self.dependencies[dependency]
        for node in nodes.values():
            ip = node['public' if public else 'ip']
            assert str(port) in node['ports'], 'pod from %s not exposing port %d ?' % (dependency, port)
            out.append('%s:%d' % (ip, node['ports'][str(port)]))
        return ','.join(out)


class Actor(FSM, Piped):
    """
    Implementation for our pod life-cycle, managing an underlying sub-process.
    """

    def __init__(self, env, latch, hints):
        super(Actor, self).__init__()

        self.commands = deque()
        self.env = env
        self.hints = hints
        self.hints['process'] = 'stopped'
        self.initialized = 0
        self.last = {}
        self.latches.append(latch)
        self.path = 'lifecycle (piped process)'
        self.terminate = 0

    def initialize(self):
        pass

    def can_configure(self, js):
        pass

    def configure(self, js):

        #
        # - this is the only method that *must* be implemented by the user
        #
        raise NotImplementedError

    def sanity_check(self, running):
        pass

    def tear_down(self, running):
        
        #
        # - simply send by default a SIGTERM to the underlying process
        # - this should be good enough in the vast majority of cases
        #
        running.terminate()

    def finalize(self):
        pass

    def initial(self, data):

        data.command = None
        data.forked = None
        data.js = {}
        data.next_sanity_check = 0
        return 'spin', data, 0

    def reset(self, data):

        #
        # - the state-machine will often be reset on purpose
        # - this happens when we need to first terminate the process
        #
        if data.forked:
            try:
                logger.info('%s : tearing down process %s' % (self.path, data.forked.pid))
                self.hints['process'] = 'terminating'
                self.tear_down(data.forked)

            except Exception as _:
                pass

        #
        # - we now need to poll until the sub-process is deemed dead (if it is
        #   running at this point)
        #
        data.reset_at = time.time()
        return 'wait_for_termination', data, 0

    def wait_for_termination(self, data):

        elapsed = time.time() - data.reset_at
        if data.forked:

            #
            # - check whether or not the process is still running
            # - it may take some time (especially in term of graceful shutdown)
            #
            if data.forked.poll() is None:

                if elapsed < self.grace:

                    #
                    # - not done yet, spin
                    #
                    return 'wait_for_termination', data, SAMPLING

                else:

                    #
                    # - the process is stuck, force a SIGKILL
                    #
                    logger.info('%s : pid %s not terminating, killing it' % (self.path, data.forked.pid))
                    try:
                        data.forked.kill()

                    except Exception as _:
                        pass

            logger.debug('%s : pid %s terminated in %d seconds' % (self.path, data.forked.pid, int(elapsed)))

        data.forked = None
        self.hints['process'] = 'stopped'
        return 'spin', data, 0

    def spin(self, data):

        if self.terminate:
            if not data.forked:

                #
                # - kill the actor (which will release the latch and unlock the main loop)
                #
                self.exitcode()

            else:

                #
                # - this will force a reset and make sure we kill the process
                # - we'll loop back to spin() in any case and exitcode() this time
                #
                raise Aborted('terminating')

        if self.commands:

            #
            # - we have at least one request pending
            # - pop the next command and run it (e.g switch the state-machine to it)
            #
            req, js, latch = self.commands[0]
            data.js = js
            data.latch = latch
            return req, data, 0

        if data.forked:

            #
            # - no request to run
            # - check if the process is still running and run the user-defined sanity check once in a while
            #
            now = time.time()
            if data.forked.poll() is not None:
                code = data.forked.returncode
                if not code:

                    #
                    # - a successful exit code (0) will automatically force a shutdown
                    # - this is a convenient way for pods go down automatically once their task is done
                    #
                    logger.error('%s : pid %s exited, shutting down' % (self.path, data.forked.pid))
                    self._request(['kill'])

                else:

                    #
                    # - the process died on a non zero exit code
                    # - restart it gracefully
                    #
                    logger.info('%s : pid %s died (code %d), re-running' % (self.path, data.forked.pid, code))
                    self._request(['off', 'on'])

            elif now >= data.next_sanity_check:
                try:

                    #
                    # - run the sanity check and schedule the next one
                    # - reset it each time
                    #
                    data.next_sanity_check = now + SANITY
                    self.sanity_check(data.forked.pid)
                    data.checks = self.checks
                    
                except Exception as failure:
        
                    #
                    # - any failure trapped during the sanity check will decrement our counter
                    # - eventually the process is stopped (up to the user to decide what to do)
                    #
                    data.checks -= 1
                    if not data.checks:
                        self._request(['off'])

                    logger.warning('%s : sanity check (%d/%d) failed -> %s' %
                                   (self.path, self.checks - data.checks, self.checks, diagnostic(failure)))

        return 'spin', data, SAMPLING

    def on(self, data):

        if data.forked and data.js and (self.strict or data.js['dependencies'] != self.last['dependencies']):

            #
            # - if we already have a process, we want to re-configure -> force a reset first
            # - this will go through a graceful termination process
            # - we'll come back here afterwards (with data.forked set to None)
            #
            raise Aborted('resetting to terminate pid %s first' % data.forked.pid)

        elif data.forked:

            #
            # - the process is already running, fail gracefully on a 200
            # - this is the code-path used for instance up a leader request when strict is false
            #
            reply = {}, 200
            logger.debug('%s : skipping /control/on request' % self.path)
            data.latch.set(reply)

        else:

            #
            # - no more process running, go on with the configuration
            #
            try:

                if not self.initialized:

                    #
                    # - if this is the 1st time the pod is running invoke the initialize() callback
                    # - this is typically used to run once-only stuff such as attaching storage volumes, etc.
                    #
                    logger.info('%s : initializing pod' % self.path)
                    self.initialize()
                    self.initialized = 1

                if data.js:

                    #
                    # - run the configuration procedure if we have some json
                    # - we'll use whatever it returns to popen() a new process
                    # - keep track of the shell command line returned by configure() for later
                    #
                    cluster = _Cluster(data.js)
                    logger.info('%s : configuring pod %d/%d' % (self.path, 1 + cluster.index, cluster.size))
                    data.command, data.env = self.configure(cluster)
                    self.last = data.js

                assert data.command, 'request to start process while not yet configured (user error ?)'

                #
                # - combine our environment variables with the overrides from configure()
                # - popen() the new process
                # - reset the sanity check counter
                # - keep track of its pid to kill it later on
                #
                now = time.time()
                env = deepcopy(self.env)
                env.update(data.env)
                tokens = data.command if self.shell else data.command.split(' ')
                data.forked = Popen(tokens, cwd=self.cwd, env=env, shell=self.shell)
                data.checks = self.checks
                self.hints['process'] = 'running'
                logger.info('%s : started <%s> as pid %s' % (self.path, data.command, data.forked.pid))
                if data.env:
                    unrolled = '\n'.join(['\t%s -> %s' % (k, v) for k, v in data.env.items()])
                    logger.debug('%s : extra environment for pid %s ->\n%s' % (self.path, data.forked.pid, unrolled))

                reply = {}, 200
                data.next_sanity_check = now + SANITY
                data.latch.set(reply)

            except Exception as failure:

                #
                # - any failure trapped during the configuration -> HTTP 406
                # - the pod will shutdown automatically as well
                #
                reply = {}, 406
                logger.warning('%s : failed to configure -> %s, shutting down' % (self.path, diagnostic(failure)))
                self._request(['kill'])
                data.latch.set(reply)

        self.commands.popleft()
        return 'spin', data, 0

    def check(self, data):

        try:
            #
            # - simply invoke the user-defined readiness check (typically to allow making sure all
            #   the required dependencies are available before starting anything)
            #
            reply = {}, 200
            cluster = _Cluster(data.js)
            self.can_configure(cluster)
            data.latch.set(reply)

        except Exception as failure:

            #
            # - any failure trapped during the configuration -> HTTP 406
            #
            reply = {}, 406
            logger.warning('%s : failed to run pre-check -> %s' % (self.path, diagnostic(failure)))
            data.latch.set(reply)

        self.commands.popleft()
        return 'spin', data, 0

    def off(self, data):

        #
        # - the /stop request does basically nothing
        # - it only guarantees we terminate the process
        #
        if data.forked:
            raise Aborted('resetting to terminate pid %s' % data.forked.pid)

        reply={}, 200
        data.latch.set(reply)
        self.commands.popleft()
        return 'spin', data, 0

    def kill(self, data):

        #
        # - the /kill request will first guarantee we terminate the process
        #
        if data.forked:
            raise Aborted('resetting to terminate pid %s' % data.forked.pid)

        try:

            #
            # - invoke the optional finalize() callback
            #
            logger.info('%s : finalizing pod' % self.path)
            self.finalize()

        except Exception as failure:

            #
            # - log something if for some reason finalize() failed as we can't really recover
            # - don't bother responding with a 406
            #
            logger.warning('%s : failed to finalize -> %s' % (self.path, diagnostic(failure)))

        #
        # - in any case request a termination and tag the pod as 'dead'
        #
        reply = {}, 200
        self.terminate = 1
        self.hints['process'] = 'dead'
        data.latch.set(reply)
        self.commands.popleft()
        return 'spin', data, 0

    def signal(self, data):

        try:
            logger.debug('%s : user signal received' % self.path)
            js = self.signaled(data.js, process=data.forked)
            reply = js if js else {}, 200

        except Exception as failure:

            #
            # - abort on a 500 upon any failure
            #
            reply = {}, 500
            logger.warning('%s : failed to signal -> %s' % (self.path, diagnostic(failure)))

        data.latch.set(reply)
        self.commands.popleft()
        return 'spin', data, 0

    def specialized(self, msg):

        assert 'request' in msg, 'bogus message received ?'
        req = msg['request']
        if req in ['on', 'check', 'off', 'kill', 'signal']:

            #
            # - we got a request from the leader or the CLI
            # - pile it in the FIFO along with its latch
            #
            js = {}
            try:
                js = json.loads(msg['data'])

            except ValueError:
                pass

            self.commands.append((req, js, msg['latch']))

        else:
            super(Actor, self).specialized(msg)

    def _request(self, tokens):

        #
        # - we use this help to schedule commands internally (mostly used to switch
        #   the pod on/off)
        #
        for token in tokens:
            self.commands.append((token, {}, ThreadingFuture()))
