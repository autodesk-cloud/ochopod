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
import fnmatch
import json
import logging
import pykka
import requests
import time

from collections import deque
from kazoo.client import KazooClient, KazooState
from kazoo.exceptions import NoNodeError
from ochopod.core.core import ROOT
from ochopod.core.fsm import diagnostic, shutdown, spin_lock, Aborted, FSM
from pykka import Timeout
from requests.exceptions import Timeout as HTTPTimeout
from threading import Event, Thread


#: Our ochopod logger.
logger = logging.getLogger('ochopod')


def lookup(zk, regex, subset=None):
    """
    Helper retrieving information about zero or more pods using a glob pattern (e.g "*.zookeeper" for instance). The
    outcome is a dict keying a compound identifier (cluster + pod sequence index) to the pod's settings(as a dict).

    There is no HTTP request sent to the pods as this is solely a zookeeper query.

    :type zk: :class:`kazoo.client.KazooClient`
    :type regex: str
    :type subset: list
    :param zk: the underlying zookeeper client
    :param regex: a glob pattern (e.g "*.zookeeper")
    :param subset: optional integer array used to select specific pods based on their sequence index
    :rtype: dict
    """

    pods = {}
    ts = time.time()
    try:
        #
        # - use a glob style regex to match the cluster (handy to retrieve multiple
        #   clusters at once)
        #
        clusters = [cluster for cluster in zk.get_children(ROOT) if fnmatch.fnmatch(cluster, regex)]
        for cluster in clusters:
            kids = zk.get_children('%s/%s/pods' % (ROOT, cluster))
            for kid in kids:
                js, _ = zk.get('%s/%s/pods/%s' % (ROOT, cluster, kid))
                hints = \
                    {
                        'id': kid,
                        'cluster': cluster
                    }

                #
                # - the number displayed by the tools (e.g shared.docker-proxy #4) is that monotonic integer
                #   derived from zookeeper
                #
                hints.update(json.loads(js))
                seq = hints['seq']
                if not subset or seq in subset:
                    pods['%s #%d' % (cluster, seq)] = hints

    except NoNodeError:
        pass

    ms = 1000 * (time.time() - ts)
    logger.debug('<- zookeeper (%d pods, %d ms)' % (len(pods), int(ms)))
    return pods


def fire(zk, cluster, command, subset=None, timeout=10.0):
    """
    Helper looking zero or more pods up and firing a HTTP control request to each one in parallel. The pod control
    port will be looked up & remapped automatically. The outcome is a dict keying a compound identifier (cluster + pod
    sequence index) to a 2-uple (the pod response and the corresponding HTTP code).

    :type zk: :class:`kazoo.client.KazooClient`
    :type cluster: str
    :type command: str
    :type subset: list
    :type timeout: float
    :param zk: the underlying zookeeper client
    :param cluster: the cluster(s) to query, as a glob pattern (e.g "*.zookeeper")
    :param subset: optional integer array used to select specific pods based on their sequence index
    :param timeout: optional timeout in seconds
    :rtype: dict
    """

    class _Post(Thread):
        """
        We optimize a bit the HTTP queries to the pods by running them on separate threads (this can be a
        tad slow otherwise for more than 10 queries in a row)
        """

        def __init__(self, key, hints):
            super(_Post, self).__init__()

            self.key = key
            self.hints = hints
            self.body = None
            self.code = None

        def run(self):

            url = 'n/a'
            try:
                ts = time.time()
                port = self.hints['port']
                assert port in self.hints['ports'], 'ochopod control port not exposed @ %s (user error ?)' % self.key
                url = 'http://%s:%d/%s' % (self.hints['public'], self.hints['ports'][port], command)
                reply = requests.post(url, timeout=timeout)
                self.body = reply.json()
                self.code = reply.status_code
                ms = 1000 * (time.time() - ts)
                logger.debug('-> %s (HTTP %d, %s ms)' % (url, reply.status_code, int(ms)))

            except HTTPTimeout:
                logger.debug(' -> %s (timeout)' % url)

            except Exception as failure:
                logger.debug('-> %s (i/o error, %s)' % (url, failure))

        def join(self, timeout=None):

            Thread.join(self)
            return self.key, self.hints['seq'], self.body, self.code

    #
    # - lookup our pods based on the cluster(s) we want
    # - fire a thread for each
    #
    threads = []
    pods = lookup(zk, cluster, subset=subset)
    for pod, hints in pods.items():
        thread = _Post(pod, hints)
        threads.append(thread)
        thread.start()

    out = [thread.join() for thread in threads]
    return {key: (seq, body, code) for (key, seq, body, code) in out if code}


def run(proxy, func, timeout=60.0):
    """
    Helper asking the zookeeper proxy actor to run the specified closure and blocking until either the timeout is
    reached or a response is received.

    :type proxy: string
    :type func: callable
    :type timeout: float
    :param proxy: our ancillary zookeeper proxy actor
    :param func: the closure to run within the proxy actor
    :param timeout: optional timeout in seconds
    :rtype: dict
    """
    try:
        latch = pykka.ThreadingFuture()
        proxy.tell(
            {
                'request': 'execute',
                'latch': latch,
                'function': func
            })
        Event()
        out = latch.get(timeout=timeout)
        if isinstance(out, Exception):
            raise out

        return out

    except Timeout:

        assert 0, 'request timeout'


class ZK(FSM):
    """
    Small actor maintaining a read-only zookeeper client and able to run closures (to run arbitrary lookup
    queries). This is used by all our tools to retrieve information about the pods.
    """

    def __init__(self, brokers, data={}):
        super(ZK, self).__init__()

        self.connected = 0
        self.brokers = brokers
        self.data = data
        self.pending = deque()
        self.path = 'zk proxy'

    def feedback(self, state):

        #
        # - forward the state change to the actor via a message
        # - the specialized() hook will process this safely
        #
        self.actor_ref.tell(
            {
                'request': 'state change',
                'state': state
            })

    def reset(self, data):

        if hasattr(data, 'zk'):
            data.zk.stop()
            data.zk.close()

        return 'initial', data, 0

    def initial(self, data):

        if self.terminate:

            #
            # - we're done, commit suicide
            # - the zk connection is guaranteed to be down at this point
            #
            self.exitcode()

        cnx_string = ','.join(self.brokers)
        data.zk = KazooClient(hosts=cnx_string, timeout=30.0, read_only=1, randomize_hosts=1)
        data.zk.add_listener(self.feedback)
        data.zk.start()

        return 'wait_for_cnx', data, 0

    def wait_for_cnx(self, data):

        if self.terminate:
            raise Aborted('terminating')

        if not self.connected:
            return 'wait_for_cnx', data, 1.0

        return 'spin', data, 0

    def spin(self, data):

        if self.terminate:
            raise Aborted('terminating')

        while len(self.pending) > 0:

            out = None
            msg = self.pending.popleft()
            try:

                #
                # - run the specified closure
                # - assign the latch to whatever is returned
                #
                out = msg['function'](data.zk)

            except Exception as failure:

                #
                # - in case of exception simply pass it upwards via the latch
                # - this will allow for finer-grained error handling
                #
                out = failure

            msg['latch'].set(out)

        return 'spin', data, 0.25

    def specialized(self, msg):

        assert 'request' in msg, 'bogus message received ?'
        req = msg['request']
        if req == 'state change':

            #
            # - we got a zk state change
            # - when ok is off the scheduling will be interrupted
            #
            state = msg['state']
            self.connected = state == KazooState.CONNECTED

        elif req == 'execute':

            #
            # - request to run some code, append to our FIFO
            #
            self.pending.append(msg)

        else:
            super(ZK, self).specialized(msg)