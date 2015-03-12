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
import argparse
import logging
import os

from logging import DEBUG
from ochopod.core.core import ROOT
from ochopod.core.fsm import diagnostic, shutdown
from ochopod.tools.io import fire, run, ZK

#: Our ochopod logger.
logger = logging.getLogger('ochopod')


class Template():
    """
    High-level template setting a ZK proxy up and handling the initial command-line parsing. All the user has
    to do is implementing the actual logic.

    The *ocho* command line tool will import
    """

    #: Optional short tool description. This is what's displayed if using --help.
    help = ""

    #: Mandatory identifier. The tool will be invoked using "ocho <tag>"
    tag = ""

    def run(self, cmdline):
        """
        Top-level method invoked by *ocho* when using this tool. This is where we preset all the
        command-line parsing, $OCHOPOD_ZK lookup, etc.

        :type cmdline: str
        :param cmdline: the flat command line
        """

        parser = argparse.ArgumentParser(prog='ocho %s' % self.tag, description=self.help)
        self.customize(parser)
        parser.add_argument('-d', '--debug', action='store_true', help='debug mode')
        parser.add_argument('--zk', action="store", dest="zk", type=str, help='zookeeper cnx string (e.g <ip>:2181,...')
        args = parser.parse_args(cmdline)
        if args.debug:
            for handler in logger.handlers:
                handler.setLevel(DEBUG)

        #
        # - the zookeeper nodes are first looked up in the environment (OCHOPOD_ZK & OCHOPOD_FWK)
        # - they can be forced from the command line using the -- overrides
        #
        zk = os.environ['OCHOPOD_ZK'] if 'OCHOPOD_ZK' in os.environ else None
        if args.zk:
            zk = args.zk
        assert zk, 'no zookeeper nodes (export $OCHOPOD_ZK or use --zk)'
        logger.debug('zookeeper @ %s' % zk)
        proxy = ZK.start([node for node in zk.split(',')])
        try:

            return self.body(args, proxy)

        finally:

            shutdown(proxy)

    def customize(self, parser):
        """
        Optional callback allowing to add specialized argparse options.

        :type parser: :class:`argparse.ArgumentParser`
        :param parser: the parser to use
        """
        pass

    def body(self, args, proxy):
        """
        Mandatory callback to implement (e.g this is where the actual tool code goes).

        :type args: dict
        :param args: the parsed command-line arguments as a dict
        :type proxy: :class:`ochopod.tools.io.ZK`
        :param proxy: the proxy to use when requesting data from zookeeper
        """
        raise NotImplementedError