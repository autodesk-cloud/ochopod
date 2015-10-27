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

"""
This script illustrates how you can define optional tools that can be connected for instance to the
ochothon CLI interface.

This minimalistic example will let you execute a remote 'ls' command. Just start a local standalone Zookeeper
server and run "python tool.py". Then do a curl -XPOST localhost:8080/exec -H "X-Shell: echo foo". You should get
back a JSON response with the output of 'your command was foo'.
"""

from ochopod.api import Tool
from ochopod.bindings.generic.marathon import Pod
from ochopod.core.utils import shell
from ochopod.models.piped import Actor as Piped
from ochopod.core.tools import Shell


if __name__ == '__main__':

    class Echo(Tool):

        #: the tag is mandatory and used to identify the tool when you HTTP POST to the pod
        tag = 'echo'

        def body(self, args, _):

            #
            # - simply exec the echo
            # - please note we don't need any command line parsing
            # - the output will be returned back to the caller
            #
            return shell('echo "your command was %s"' % args)

    class Strategy(Piped):

        def configure(self, _):

            #
            # - just go to sleep, the point is not to run anything meaningful
            #
            return 'sleep 3600', {}

    #
    # - specify the tools your pod should support in the boot() call
    # - note you can also include default tools that are shipped with ochopod (e.g Shell for instance)
    #
    Pod().boot(Strategy, tools=[Echo, Shell], local=1)
