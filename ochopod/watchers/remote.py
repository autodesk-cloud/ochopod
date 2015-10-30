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

    def __init__(self, model, zk, scope, tag, remote):
        super(Watcher, self).__init__()

        self.model = model
        self.path = 'watcher (%s.%s)' % (scope, tag)
        self.pod = '%s.%s' % (scope, tag)
        self.query = 1
        self.remote = remote
        self.scope = scope
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
            # - go get to the zk nodes we want to look at
            # - any dependency starting with '/' is absolute
            # - the lookup will be done starting in the pod's namespace otherwise
            #
            pods = {}
            where = self.remote[1:] if self.remote[0] == '/' else '%s.%s' % (self.scope, self.remote)
            if '*' in self.remote:

                #
                # - regex dependency, which is slightly more involved
                # - from @pferro -> leave a watch on the ROOT in case a new node matching
                #   the regex appears later on
                # - each zk node matching the regex will also leave a watch on
                #
                for child in self.zk.get_children(ROOT, watch=self.feedback):
                    if fnmatch.fnmatch(child, where):
                        try:

                            #
                            # - do *not* include the current pod in the watch
                            # - this edge case could be hit when using absolute dependencies
                            #
                            if child == self.pod:
                                continue

                            #
                            # - same as the regular case: grab the json payload and leave a watch
                            # - from @pferro -> we need to make sure we leave a watch around in case the
                            #   snapshot node does not exist yet (the regular case does not require it since
                            #   the self.query flip-flop would be left on by default)
                            #
                            path = '%s/%s/snapshot' % (ROOT, child)
                            if self.zk.exists(path, watch=self.feedback):
                                value, stat = self.zk.get(path, watch=self.feedback)
                                try:
                                    pods.update(json.loads(value))
                                except ValueError:
                                    pass

                        except NoNodeError:
                            pass

                #
                # - unset the flip-flop
                #
                self.query = 0

            else:

                #
                # - no regex specified -> simply do a single get() on the appropriate zk node
                # - issue a get() on the dependency snapshot/ node
                # - if this node is not there yet (or the dependency path invalid), no big deal
                #
                try:
                    if where != self.pod:
                        path = '%s/%s/snapshot' % (ROOT, where)
                        value, stat = self.zk.get(path, watch=self.feedback)
                        try:
                            pods.update(json.loads(value))
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
                        'key': self.remote,
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
