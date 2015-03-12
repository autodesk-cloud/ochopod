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

from copy import deepcopy
from kazoo.exceptions import NoNodeError
from ochopod.core.core import ROOT, SAMPLING
from ochopod.core.fsm import Aborted, FSM

#: Our ochopod logger.
logger = logging.getLogger('ochopod')


class Watcher(FSM):
    """
    Ancillary actor whose job is to flag updates to our local snapshot by querying & comparing.
    """

    def __init__(self, model, zk, scope, tag):
        super(Watcher, self).__init__()

        self.model = model
        self.path = 'watcher (%s.%s)' % (scope, tag)
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

        #
        # - query our /pods/* nodes
        # - split the pod UUID and the sequence counter
        # - concatenate into one dict
        # - store the sequence counter as 'index'
        #
        pods = {}
        prefix = '%s/%s.%s' % (ROOT, self.scope, self.tag)
        for pod in [tag for tag in self.zk.get_children('%s/pods' % prefix)]:
            (value, stat) = self.zk.get('%s/pods/%s' % (prefix, pod))
            tokens = pod.split('.')
            js = json.loads(value)
            pods[tokens[0]] = js

        #
        # - if we differ with our last snapshot, notify the model
        # - don't forget to copy the js payload as the receiving actor may edit it
        #
        if pods != data.latest:
            data.latest = pods
            self.model.tell(
                {
                    'request': 'snapshot update',
                    'key': 'local',
                    'pods': deepcopy(pods)
                })

        return 'spin', data, SAMPLING
