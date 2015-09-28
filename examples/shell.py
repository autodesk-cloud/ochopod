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
This script is what your container should run. You have the flexibility to define what you need to run and how to
configure it (possibly across a fleet of containers spanning multiple machines).

This minimalistic example will just spawn a shell command using the Marathon bindings. Just start a local
standalone Zookeeper server and run "python shell.py".
"""

from ochopod.bindings.generic.marathon import Pod
from ochopod.models.piped import Actor as Piped


if __name__ == '__main__':

    class Strategy(Piped):

        #
        # - you can override the default settings, for instance here to tell ochopod what configure()
        #   returns should actually be treated as a shell command
        #
        shell = True

        #
        # - you can also pipe the sub-process stderr/out and include them in the pod log
        #
        pipe_subprocess = True

        def configure(self, _):

            #
            # - simply return what you wish to run (a simple shell statement in our case)
            # - deriving from Piped means the SDK will use popen() to fork an ancillary process
            # - you can also set optional environment variables on that process (presently $LAPSE)
            # - note that whatever value you pass will be turned into a string (e.g you can use numbers)
            #
            return "sleep $LAPSE && echo 'hello world' && exit 0", {'LAPSE': 5}

    #
    # - that's it, just boot the SDK with your process strategy
    # - the local=1 means we force everything to be looked up on localhost
    # - if you run this script locally you should see 'hello world' printed on stdout after 5 seconds
    # - since we exit with 0 the pod will automatically be finalized (e.g shutdown gracefully)
    # - simply type CTRL-C to exit
    #
    Pod().boot(Strategy, local=1)
