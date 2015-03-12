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
    """
    Entry-point looked up by the *ocho* command-line tool. Any module exporting a go() callable returning an
    instance of :class:`ochopod.tools.tool.Template` will be loaded and made available as a tool.

    :rtype: an instance of :class:`ochopod.tools.tool.Template`
    """

    class _Tool(Template):
        """
        Sample tool that shows how to retrieve information about pods running on a given cluster. We basically
        just used a template class and implement a callback. This tool can be invoked by doing "ocho count".

        Look at :class:`ochopod.tools.tool.Template` for more details.
        """

        help = \
            '''
                our own tool !
            '''

        tag = 'count'

        def body(self, _, proxy):

            def _query(zk):

                #
                # - this closure will run in our zookeeper proxy actor
                # - in this case we'll HTTP POST a /info query to all our pods (you can use a glob pattern)
                # - fire() will figure out where the pods are running from and what their control port is
                # - we simply return the number of pods who answered with HTTP 200
                # - please note all the I/O is done on parallel for each pod and the outcome aggregated for you
                #
                responses = fire(zk, '*', 'info')
                return sum(1 for key, (_, _, code) in responses.items() if code == 200)

            #
            # - run our query using the closure above
            # - this call will block and return whatever _query() returns
            #
            total = run(proxy, _query)
            logger.info('%d pods' % total)

    return _Tool()