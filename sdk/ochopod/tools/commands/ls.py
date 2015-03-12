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
import logging

from ochopod.tools.io import fire, run
from ochopod.tools.tool import Template

#: Our ochopod logger.
logger = logging.getLogger('ochopod')


def go():

    class _Tool(Template):
        """
        Quick lookup tool that will list all running containers.
        """

        help = \
            '''
                lists the running containers (e.g the ones that are not dead nor idling but actively running
                their sub-process)
            '''

        tag = 'ls'

        def body(self, args, proxy):

            def _query(zk):
                responses = fire(zk, '*', 'info')
                return {key: hints['process'] for key, (_, hints, code) in responses.items() if code == 200}

            js = run(proxy, _query)
            if not js:
                logger.info('no pods detected (make sure you point to the right zookeeper)')
            else:
                running = [pod for pod, state in js.items() if state == 'running']
                pct = int((100 * len(running)) / len(js))
                logger.info('%d pods total, %d%% running ->\n - %s' % (len(js), pct, '\n - '.join(sorted(running))))

    return _Tool()