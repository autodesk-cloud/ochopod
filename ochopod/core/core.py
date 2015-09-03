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
import ochopod
import pykka
import time
import uuid

from flask import Flask, request
from kazoo.exceptions import ConnectionClosedError, NodeExistsError
from kazoo.client import KazooClient, KazooState
from kazoo.recipe.lock import LockTimeout
from ochopod.core.fsm import shutdown, spin_lock, Aborted, FSM
from pykka import ThreadingFuture, Timeout
from threading import Event


#: Our ochopod logger
logger = logging.getLogger('ochopod')

#: Root zookeeper node path (under which we store the pod data for each cluster). This path will prefix any node
#: we read or write (including the lock).
ROOT = '/ochopod/clusters'

#: We use the same tick for all our state-machines (namely one second). This quantity can be scaled up or
#: down depending on the actor
SAMPLING = 1.0


class ZK(FSM):
    """
    Base layer dealing with zookeeper and in charge of writing the pod ephemeral node upon connection. The
    reset() state will by default loop back to initial() and properly de-allocate the kazoo driver. Once connected
    the machine will spin() until we raise something.

    Please note we support an explicit reset request which will trip the machine. This is used from the CLI to
    force a pod to completely disconnect/reconnect/reconfigure.
    """

    def __init__(self, brokers, scope, tag, breadcrumbs, hints):
        super(ZK, self).__init__()

        self.breadcrumbs = breadcrumbs
        self.connected = 0
        self.brokers = brokers
        self.force_reset = 0
        self.hints = hints
        self.hints['state'] = 'follower'
        self.id = uuid.uuid4()
        self.prefix = '%s/%s.%s' % (ROOT, scope, tag)
        self.scope = scope
        self.seq = None
        self.tag = tag

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

        self.connected = 0
        self.force_reset = 0
        self.hints['state'] = 'follower'
        logger.warning('%s : actor reset (%s)' % (self.path, data.cause))
        if hasattr(data, 'zk'):

            #
            # - gracefully shut our client down
            #
            data.zk.stop()
            logger.debug('%s : zk client stopped, releasing resources' % self.path)
            data.zk.close()

        if self.terminate:
            super(ZK, self).reset(data)

        return 'initial', data, 0

    def initial(self, data):

        #
        # - setup a new kazoo client
        #
        cnx_string = ','.join(self.brokers)
        logger.debug('%s : connecting @ %s' % (self.path, cnx_string))
        data.zk = KazooClient(hosts=cnx_string, timeout=5.0, read_only=0, randomize_hosts=1)
        data.zk.add_listener(self.feedback)
        data.zk.start()
        data.n = 0

        return 'wait_for_cnx', data, 0

    def wait_for_cnx(self, data):

        if self.force_reset or self.terminate:
            raise Aborted('resetting')

        #
        # - loop back if we haven't received a CONNECTED event from the driver
        #
        if not self.connected:
            return 'wait_for_cnx', data, SAMPLING

        #
        # - the /pods node holds all our ephemeral per-container data (one container == one child node)
        # - the /hash node stores the last recorded md5 hash (local pods + dependencies), which we use to
        #   flag any change amongst the pods or their dependencies
        #
        data.zk.ensure_path('%s/pods' % self.prefix)
        data.zk.ensure_path('%s/hash' % self.prefix)
        try:

            #
            # - register ourselves by creating an ephemeral
            # - this is where we can store arbitrary information (e.g our breadcrumbs)
            # - we ask for a sequence counter as well which we then keep (e.g in case of connection loss or reset
            #   we guarantee the pod won't get assigned a new index)
            # - this is *critical* for some use-cases (e.g Kafka where the broker index must remain the same)
            #
            path = data.zk.create('%s/pods/%s.' % (self.prefix, self.id), ephemeral=True, sequence=True)
            tokens = path.split('.')
            if self.seq is None:
                self.seq = int(tokens[-1])
            self.breadcrumbs['seq'] = self.seq
            js = json.dumps(self.breadcrumbs)
            data.zk.set(path, js)

        except NodeExistsError:

            #
            # - if the node is already there we just recovered from a zookeeper connection loss
            #   and /snapshot has not been phased out yet .. this is not an issue, simply pause a bit
            #   to re-attempt later
            #
            logger.debug('%s : pod %s is already there (probably a zk reconnect)' % (self.path, self.id))
            return 'wait_for_cnx', data, 5.0 * SAMPLING

        logger.debug('%s : registered as %s (#%d)' % (self.path, self.id, self.seq))
        data.connected_at = time.time()
        return 'spin', data, 0

    def spin(self, data):

        raise NotImplementedError

    def specialized(self, msg):

        assert 'request' in msg, 'bogus message received ?'
        req = msg['request']
        if req == 'state change':

            #
            # - we got a zk state change
            # - we only use the switch to CONNECTED to go from wait_for_cnx() to spin()
            # - ZK disconnects (LOST or SUSPENDED) are simply flagged when exceptions are raised
            #
            state = msg['state']
            current = 'connected' if self.connected else 'disconnected'
            logger.debug('%s : zk state change -> "%s" (%s)' % (self.path, str(state), current))
            if self.connected and state != KazooState.CONNECTED:
                logger.warning('%s : lost connection (%s) / forcing a reset' % (self.path, str(state)))
                self.force_reset = 1
                self.connected = 0

            elif state == KazooState.CONNECTED:
                self.connected = 1

        elif req == 'reset':

            #
            # - we got a request to explicitly force a reset
            # - this is typically invoked from the CLI
            #
            self.force_reset = 1

        else:
            super(ZK, self).specialized(msg)


class Coordinator(ZK):
    """
    Leader lock implementation logic, based on :class:`ZK`. The spin() state will attempt to grab a lock (we
    simply use the Kazoo recipe). If we obtain the lock we boot the controller actor (e.g the clustering model)
    and then stay there by spin-locking on its latch. If the controller goes down for any reason (typically a
    zookeeper error or a shutdown request) we'll reset (and disconnect from zookeeper).
    """

    def __init__(self, brokers, scope, tag, port, breadcrumbs, model, hints):
        super(Coordinator, self).__init__(brokers, scope, tag, breadcrumbs, hints)

        self.model = model
        self.path = 'coordinator'
        self.port = port

    def reset(self, data):

        if hasattr(data, 'controller'):

            #
            # - don't forget to nuke our controller before resetting
            #
            shutdown(data.controller)

        if hasattr(data, 'lock'):

            #
            # - make sure to remove the lock attribute
            # - it's useless to release the lock as we'll release the client altogether
            #
            delattr(data, 'lock')

        return super(Coordinator, self).reset(data)

    def spin(self, data):

        #
        # - if the termination trigger is set, abort immediately
        #
        if self.force_reset or self.terminate:
            raise Aborted('resetting')

        #
        # - attempt to fetch the lock
        # - allocate it if not already done
        # - it is *important* to just allocate one lock as there is a leak in kazoo
        #
        if not hasattr(data, 'lock'):
            data.lock = data.zk.Lock('%s/coordinator' % self.prefix)

        try:

            #
            # - attempt to lock within a 5 seconds timeout to avoid stalling in some cases
            #
            if data.lock.acquire(timeout=5.0 * SAMPLING):
                return 'start_controller', data, 0

        except LockTimeout:
            pass

        return 'spin', data, 0

    def start_controller(self, data):

        #
        # - if the termination trigger is set, abort immediately
        # - this is important as it is possible to somehow get the lock after a suspend (acquire() returns
        #   true in that case which is misleading)
        #
        if self.force_reset or self.terminate:
            raise Aborted('resetting')

        #
        # - we have the lock (e.g we are the leader)
        # - start the controller actor
        #
        data.latch = ThreadingFuture()
        logger.debug('%s : lock acquired @ %s, now leading' % (self.path, self.prefix))
        data.controller = self.model.start(data.zk, self.id, self.hints, self.scope, self.tag, self.port, data.latch)

        return 'lock', data, 0

    def lock(self, data):

        #
        # - if the termination trigger is set, abort immediately
        #
        if self.force_reset or self.terminate:
            raise Aborted('resetting')

        #
        # - spin-lock on the controller latch
        # - any catastrophic plug failure will be trapped that way
        #
        try:
            Event()
            out = data.latch.get(SAMPLING)
            if isinstance(out, Exception):
                raise out

        except Timeout:
            pass

        return 'lock', data, 0