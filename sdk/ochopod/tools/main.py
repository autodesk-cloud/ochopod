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
import imp
import logging
import os
import sys

from os import listdir
from os.path import dirname, isfile, join
from ochopod.tools import commands
from ochopod.tools.tool import Template
from ochopod.core.fsm import diagnostic

#: Our ochopod logger.
logger = logging.getLogger('ochopod')


def go():
    """
    Entry point for the ochopod CLI tool-suite. This script will look for python modules in the current directory,
    in a /tools sub-directory as well as in within our package (e.g the default tools such as cli or ls).

    If the $OCHOPOD_PATH variable is exported we will split it on : and scan each directory as well.
    """

    #
    # - start by simplifying a bit the console logger to look more CLI-ish
    #
    for handler in logger.handlers:
        handler.setFormatter(logging.Formatter('%(message)s'))

    try:

        def _import(where, funcs):
            try:
                for script in [f for f in listdir(where) if isfile(join(where, f)) and f.endswith('.py')]:
                    try:
                        module = imp.load_source(script[:-3], join(where, script))
                        if hasattr(module, 'go') and callable(module.go):
                            tool = module.go()
                            assert isinstance(tool, Template), 'boo'
                            assert tool.tag, ''
                            funcs[tool.tag] = tool

                    except Exception as failure:
                        logger.debug('failed to import %s (%s)' % (script, diagnostic(failure)))

            except OSError:
                pass

        #
        # - disable .pyc generation
        # - scan for tools to import (include $OCHOPOD_PATH if exported)
        # - each .py module must have a go() callable as well as a COMMAND attribute (which tells us what its
        #   command + sub-commands look like, for instance "cli" or "marathon upload")
        #
        tools = {}
        sys.dont_write_bytecode = True
        path = os.environ['OCHOPOD_PATH'] if 'OCHOPOD_PATH' in os.environ else ''
        src = path.split(':') + ['.', 'tools', '%s/commands' % dirname(__file__)]
        [_import(path, tools) for path in src]

        def _usage():
            return 'available commands -> %s' % ', '.join(sorted(tools.keys()))

        parser = argparse.ArgumentParser(description='ocho', prefix_chars='+', usage=_usage())
        parser.add_argument('command', type=str, help='command (e.g cli or ls for instance)')
        parser.add_argument('extra', metavar='extra arguments', type=str, nargs='*', help='zero or more arguments')
        args = parser.parse_args()
        total = [args.command] + args.extra

        def _sub(sub):
            for i in range(len(total)-len(sub)+1):
                if sub == total[i:i+len(sub)]:
                    return 1
            return 0

        matched = [tool for tool in tools.keys() if _sub(tool.split(' '))]
        if not matched:
            logger.info('unknown command (%s)' % _usage())
        elif len(matched) > 1:
            logger.info('more than one command were matched (%s)' % _usage())
        else:

            #
            # - simply invoke the tool
            # - remove the command tokens first and pass the rest as arguments
            # - each tool will parse its own commandline
            #
            picked = matched[0]
            tokens = len(picked.split(' ')) - 1
            exit(tools[picked].run(args.extra[tokens:]))

    except KeyboardInterrupt:

        logger.warning('shutting down <- CTRL-C pressed')

    except AssertionError as failure:

        logger.error('shutting down <- %s' % failure)

    except Exception as failure:

        logger.error('shutting down <- %s' % diagnostic(failure))

    exit(1)