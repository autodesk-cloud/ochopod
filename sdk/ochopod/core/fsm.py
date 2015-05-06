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
import copy
import logging
import sys
import time
import traceback

from pykka import ThreadingActor, ThreadingFuture, Timeout
from pykka.exceptions import ActorDeadError
from threading import Event, Thread

#: our pycse logger
logger = logging.getLogger('ochopod')


def spin_lock(latch, strict=1, spin=0.5):
    """
    Simple "spin lock" where we wait on a future with a small timeout and loop back until something is
    set.

    :type latch: :class:`pykka.ThreadingFuture`
    :param latch: future to block on
    :type strict: bool
    :param strict: if true the method will raise if ever the future outcome is an exception
    :type spin: float
    :param spin: wait timeout in seconds
    :rtype: the future outcome
    """
    while 1:
        try:
            Event()
            out = latch.get(timeout=spin)
            if strict and isinstance(out, Exception):
                raise out

            return out
        except Timeout:
            pass


def block(creator, strict=1, spin=0.5, collect=None):
    """
    Compound spin-lock creating a latch, passing it to a lambda and then blocking.

    :type creator: lambda
    :param creator: lambda taking a :class:`pykka.ThreadingFuture` as parameter
    :type strict: bool
    :param strict: if true the method will raise if ever the future outcome is an exception
    :type spin: float
    :param spin: wait timeout in seconds
    :type collect: list
    :param collect: receives the lambda result if specified
    :rtype:
    """

    latch = ThreadingFuture()
    ref = creator(latch)
    if collect is not None:
        collect.append(ref)

    spin_lock(latch, strict, spin)


def block_n(creators, strict=1, spin=0.5, collect=None):
    """
    Compound spin-lock creating a set of latches latch, passing them to lambdas and then blocking on all
    of them.

    :type creators: list
    :param creators: one or more lambdas returning a :class:`pykka.ThreadingFuture`
    :type strict: bool
    :param strict: if true the method will raise if ever *any* future outcome is an exception
    :type spin: float
    :param spin: wait timeout in seconds
    :type collect: list
    :param collect: receives the lambda results if specified
    :rtype:
    """

    def _start():
        latch = ThreadingFuture()
        ref = creator(latch)
        if collect is not None:
            collect.append(ref)
        return latch

    out = []
    latches = [_start() for creator in creators]
    top = latches.pop()
    while 1:
        try:
            Event()
            out.append(top.get(timeout=spin))
            if not len(latches):
                break
            top = latches.pop()
        except Timeout:
            pass

    for item in out:
        if strict and isinstance(item, Exception):
            raise item

    return out


def shutdown(actor_ref, timeout=None):
    """
    Shuts a state-machine down and wait for it to acknowledge it's down using a latch.

    :type actor_ref: :class:`pykka.ActorRef`
    :param actor_ref: a pykka actor reference
    :type timeout: float
    :param timeout: optional timeout in seconds
    """
    try:
        if not actor_ref:
            return

        latch = ThreadingFuture()
        actor_ref.tell({'request': 'shutdown', 'latch': latch})
        Event()
        latch.get(timeout=timeout)

    except Timeout:
        pass

    except ActorDeadError:
        pass


def diagnostic(failure):
    """
    Returns a pretty-printed blurb describing an exception.

    :type failure: :class:`Exception`
    :param failure: the exception to diagnose
    :rtype: str
    """
    _, _, tb = sys.exc_info()
    info = traceback.extract_tb(tb)
    filename, line, _, _ = info[-1]
    where = filename if len(filename) < 18 else '..' + filename[-18:]
    why = ' (%s)' % failure if failure else ""
    return '%s (%d) -> %s%s' % (where, line, type(failure).__name__, why)


class Retry(Exception):
    """
    Exception thrown to trip the machine back to the same state after an optional pause.
    """

    def __init__(self, why='N/A', delay=0):
        self.why = why
        self.delay = delay


class PoisonPill(Exception):
    """
    Exception thrown to terminate the machine.
    """
    pass


class Aborted(Exception):
    """

    """

    def __init__(self, log):
        self.log = log if isinstance(log, list) else [log]

    def __str__(self):
        return str(self.log[-1])


class FSM(ThreadingActor):
    """
    Simple finite state-machine actor that will loop through one or more states. Each state is implemented as
    a method.
    """

    def __init__(self, payload=None):

        super(FSM, self).__init__()

        self.dying = 0
        self.latches = []
        self.path = '?'
        self.payload = _Container(copy.deepcopy(payload) if payload else {})
        self.terminate = 0

    def exitcode(self, code=None):

        #
        # - release our latches
        #
        while len(self.latches) > 0:
            self.latches.pop().set(code)
            Event()

        #
        # - we're done, commit suicide
        #
        raise PoisonPill

    def reset(self, data):

        #
        # - pass the exception that caused the reset back to the latch or re-package it as an Aborted
        #   and seed its log using the failure diagnostic otherwise
        #
        logger.debug('%s : reset (%s)' % (self.path, data.cause))
        self.exitcode(data.cause if isinstance(data.cause, Aborted) else Aborted(data.diagnostic))

    def initial(self, data):

        raise NotImplementedError

    def specialized(self, msg):

        assert 'request' in msg, 'bogus message received ?'
        req = msg['request']

        if req == 'shutdown':

            #
            # - set the termination trigger
            # - if the user specified a latch keep it around
            #
            self.terminate = 1
            latch = msg['latch'] if 'latch' in msg else None
            if latch:
                #
                # - we the actor is already going down set the latch immediately
                # - otherwise we might deadlock the caller
                #
                if self.dying:
                    msg['latch'].set()

                #
                # - otherwise keep track of the new latch
                #
                else:
                    self.latches.append(msg['latch'])

    def fire(self, payload, delay=0):

        if delay > 0:
            #
            # - run an ancillary thread that will sleep and then fire the message
            # - the machine itself won't block and will be able to process incoming messages
            #
            scheduled = _Scheduled(self.actor_ref, payload, delay)
            scheduled.start()

        else:
            #
            # - fire right now
            #
            self.actor_ref.tell(payload)

    def on_start(self):

        #
        # - trip the machine into its initial state
        #
        self.actor_ref.tell({'fsm': {'state': 'initial', 'data': self.payload}})

    def on_receive(self, msg):

        #
        # - default processing handler for any incoming actor message
        #
        if 'fsm' not in msg:
            try:
                #
                # - not our internal state-switch message : run the specialized handler
                # - make sure to return its outcome so that we can reply to other actors
                #
                return self.specialized(msg)

            except Exception as failure:
                logger.debug('%s : exception trapped while handling specialized messages (%s)' % (self.path, str(failure)))
                pass

        else:
            cmd = msg['fsm']
            try:
                if self.dying:
                    #
                    # - skip if we're shutting down
                    #
                    pass
                else:
                    func = getattr(self, cmd['state'], None)
                    assert func, '<' + cmd['state'] + '> does not exist'
                    assert callable(func), '<' + cmd['state'] + '> must be a callable'
                    next, data, delay = func(cmd['data'])
                    data['previous'] = cmd['state']
                    payload = \
                        {
                            'fsm':
                                {
                                    'state': next,
                                    'data': data
                                }
                        }
                    assert delay >= 0, 'the delay until the next state switch must be positive'
                    self.fire(payload, delay)

            except PoisonPill:

                _kill(self.actor_ref)
                self.dying = 1

            except Retry as failure:

                assert cmd['state'] != 'reset', 'retrying is not allowed from the reset state'
                delay = failure.delay
                now = time.time()

                if 'retried at' not in cmd:

                    #
                    # - 1st attempt to retry : set the timestamp
                    # - loop back to the same state
                    #
                    cmd['retried at'] = now
                    self.fire(msg, delay)

                else:

                    self.fire(msg, delay)

            except Aborted as failure:

                data = cmd['data']
                data.cause = failure
                data.previous = cmd['state']
                data.diagnostic = str(failure)
                self.actor_ref.tell({'fsm': {'state': 'reset', 'data': data}})

            except Exception as failure:

                #
                # - if an assert blew up or if we got interrupted, get the file/line information and reset
                # - if this happened in the 'reset' state, kill the actor
                #
                if cmd['state'] == 'reset':

                    logger.debug('%s : exception trapped while resetting (%s)' % (self.path, str(failure)))
                    _kill(self.actor_ref)
                    self.dying = 1

                else:

                    data = cmd['data']
                    data.cause = failure
                    data.previous = cmd['state']
                    data.diagnostic = diagnostic(failure)
                    logger.debug('%s : exception trapped -> (%s)' % (self.path, data.diagnostic))
                    self.actor_ref.tell({'fsm': {'state': 'reset', 'data': data}})


class _Scheduled(Thread):
    """
    Thread emulating a scheduled message (e.g posted to the state-machine after some delay.
    """

    def __init__(self, ref, msg, lapse):
        super(_Scheduled, self).__init__()
        assert lapse >= 0, 'invalid duration (cannot be negative)'
        self.ref = ref
        self.msg = msg
        self.lapse = lapse

    def run(self):
        time.sleep(self.lapse)
        try:
            #
            # - the tell() can raise if ever the actor has been nuked in the meantime
            # - this would typically happen if exitcode() was invoked
            #
            self.ref.tell(self.msg)
        except Exception:
            pass


class _Container(dict):
    """
    Dict we pass across states (e.g that *data* parameter) with some extra attributes (*cause* for instance).
    """
    pass

def _kill(actor_ref):
    """
    Forcefully kill a pykka actor by emitting a 'pykka_stop' command and returns false if ever the actor
    has already been killed.

    :type actor_ref: :class:`pykka.ActorRef`
    :param actor_ref: a pykka actor reference
    :rtype: bool
    """
    try:
        if not actor_ref:
            return False

        actor_ref.tell({'command': 'pykka_stop'})
        return True

    except ActorDeadError:
        pass

    return False
