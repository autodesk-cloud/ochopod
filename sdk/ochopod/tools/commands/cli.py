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

from cmd import Cmd
from ochopod.core.core import ROOT
from ochopod.core.fsm import diagnostic
from ochopod.tools.io import fire, run
from ochopod.tools.tool import Template

#: Our ochopod logger.
logger = logging.getLogger('ochopod')


def go():

    class _Tool(Template):
        """
        Simple CLI shell allowing interactive operations against a given Mesos cluster.
        """

        help = \
            '''
                starts our cool interactive CLI shell !
            '''

        tag = 'cli'

        def body(self, args, proxy):

            #
            # - use a cmd wrapper to implement the shell
            #
            class Shell(Cmd):

                prompt = '> '
                ruler = '-'

                def emptyline(self):
                    pass

                def do_exit(self, _):

                    """aborts the shell"""

                    raise KeyboardInterrupt

                def do_grep(self, line):

                    """displays a quick summary for the selected pods"""

                    tokens = line.split(' ') if line else ['*']
                    for token in tokens:

                        def _query(zk):
                            out = {}
                            responses = fire(zk, token, 'info')
                            for pod, (_, hints, code) in responses.items():
                                if code == 200:
                                    out[pod] = '[%s / %s] @ %s (%s)' % \
                                               (hints['state'], hints['process'], hints['node'], hints['public'])

                            return len(responses), out

                        total, js = run(proxy, _query)
                        if not total:
                            logger.info('\n<%s> no pods found' % token)

                        else:
                            pct = (len(js) * 100) / total
                            unrolled = ['%s %s' % (k, js[k]) for k in sorted(js.keys())]
                            logger.info(
                                '\n<%s> %d%% replies (%d pods total) ->\n\n- %s\n' % (token, pct, total, '\n- '.join(unrolled)))

                def do_info(self, line):

                    """displays full information for the selected pods"""

                    tokens = line.split(' ') if line else ['*']
                    for token in tokens:

                        def _query(zk):
                            responses = fire(zk, token, 'info')
                            return {key: hints for key, (_, hints, code) in responses.items() if code == 200}

                        js = run(proxy, _query)
                        unrolled = ['%s\n%s\n' % \
                                    (k, json.dumps(js[k], indent=4, separators=(',', ': '))) for k in sorted(js.keys())]
                        logger.info('\n<%s> %d pods ->\n\n- %s' % (token, len(js), '\n- '.join(unrolled)))

                def do_log(self, line):

                    """retrieve the last 32 lines of log for each selected pod"""

                    tokens = line.split(' ') if line else ['*']
                    for token in tokens:

                        def _query(zk):
                            return fire(zk, token, 'log')

                        js = run(proxy, _query)
                        for pod in sorted(js.keys()):
                            _, log, code = js[pod]
                            if code == 200:
                                logger.info('\n%s ->\n\n- %s' % (pod, '- '.join(log[-32:])))

                def do_reset(self, line):

                    """fully resets the selected pods without impacting their sub-process"""

                    tokens = line.split(' ') if line else ['*']
                    for token in tokens:

                        def _query(zk):
                            return fire(zk, token, 'reset')

                        run(proxy, _query)

                def do_on(self, line):

                    """switches the selected pods on"""

                    tokens = line.split(' ') if line else ['*']
                    for token in tokens:

                        def _query(zk):
                            return fire(zk, token, 'control/on')

                        run(proxy, _query)


                def do_off(self, line):

                    """switches the selected pods off"""

                    tokens = line.split(' ') if line else ['*']
                    for token in tokens:

                        def _query(zk):
                            return fire(zk, token, 'control/off')

                        run(proxy, _query)

            logger.info('welcome to the ochopod CLI ! (CTRL-C to exit)')
            while 1:
                try:
                    #
                    # - run the shell
                    # - trap / re-run in case of exception
                    #
                    Shell().cmdloop()

                except Exception as failure:

                    logger.error('internal failure <- %s' % diagnostic(failure))

    return _Tool()