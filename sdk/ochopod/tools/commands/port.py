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
        Quick lookup tool that will display the current remapping for a given TCP port. Any pod matching the
        cluster identifier(s) provided and exposing that port will be displayed (public IP + exposed port).
        """

        help = \
            '''
                displays the current remapping for a given TCP port
            '''

        tag = 'port'

        def customize(self, parser):

            parser.add_argument('port', type=int, nargs=1, help='TCP port to lookup')
            parser.add_argument('clusters', type=str, nargs='*', default='*', help='1+ clusters (can be a glob pattern, e.g foo*)')

        def body(self, args, proxy):

            port = str(args.port[0])
            for cluster in args.clusters:

                def _query(zk):
                    responses = fire(zk, cluster, 'info')
                    return {key: '%d\t\t%s' % (hints['ports'][port], hints['public'])
                            for key, (_, hints, code) in responses.items() if code == 200 and port in hints['ports']}

                js = run(proxy, _query)
                if js:
                    unrolled = ['%s\t\t%s' % (ip, node) for node, ip in js.items()]
                    logger.info('%s (%d pods exposing %s) ->\n - %s' % (cluster, len(js), port, '\n - '.join(unrolled)))

    return _Tool()