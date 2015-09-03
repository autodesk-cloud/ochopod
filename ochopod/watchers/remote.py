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

from kazoo.exceptions import NoNodeError
from ochopod.core.core import ROOT, SAMPLING
from ochopod.core.fsm import Aborted, FSM

#: Our ochopod logger.
logger = logging.getLogger('ochopod')


class Watcher(FSM):
    """
    Ancillary actor whose job is to flag updates to a given zk node using a watch. We use this mechanism
    to keep track of the pod dependencies.
    """

    def __init__(self, model, zk, scope, tag):
        super(Watcher, self).__init__()

        self.model = model
        self.path = 'watcher (%s.%s)' % (scope, tag)
        self.query = 1
        self.scope = scope
        self.tag = tag
        self.zk = zk

    def reset(self, data):

        #
        # - notify the controller
        # - this actor is purely ancillary and can go down now
        #
        self.model.tell(
            {
                'request': 'watcher failure'
            })

        return super(Watcher, self).reset(data)

    def initial(self, data):

        #
        # - go straight to spinning
        #
        data.latest = None
        return 'spin', data, 0

    def spin(self, data):

        #
        # - if the termination trigger is set, abort immediately
        #
        if self.terminate:
            self.exitcode()

        if self.query:

            #
            # - the flip-flop trigger is on
            # - issue a get() on the dependency snapshot/ node
            # - if this node is not there yet (or the dependency path invalid), no big deal
            #
            pods = {}
            try:
                path = '%s/%s.%s/snapshot' % (ROOT, self.scope, self.tag)
                value, stat = self.zk.get(path, watch=self.feedback)
                try:
                    pods = json.loads(value)
                except ValueError:
                    pass

                #
                # - unset the flip-flop
                #
                self.query = 0

            except NoNodeError:
                pass

            #
            # - notify the model we have a snapshot for that dependency
            #
            if pods != data.latest:
                data.latest = pods
                logger.debug('%s : change detected in dependency' % self.path)
                self.model.tell(
                    {
                        'request': 'snapshot update',
                        'key': self.tag,
                        'pods': pods
                    })

        return 'spin', data, SAMPLING
    
    def specialized(self, msg):

        assert 'request' in msg, 'bogus message received ?'
        req = msg['request']

        if req == 'watch triggered':

            #
            # - the zk watch was activated
            # - simply set the flip-flop which will result in a new get()
            # - the watch will then be reset again on the node
            #
            self.query = 1
            
        else:
            super(Watcher, self).specialized(msg)

    def feedback(self, event):

        #
        # - watch notification from the zk client
        # - forward to the actor
        #
        self.actor_ref.tell(
            {
                'request': 'watch triggered'
            })
