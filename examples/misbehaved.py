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
This script illustrates how the sanity check mechanism can guard against processes that keep failing (or can't start
for whatever reason).

Just start a local standalone Zookeeper server and run "python misbehaved.py".
"""

from ochopod.bindings.generic.marathon import Pod
from ochopod.models.piped import Actor as Piped


if __name__ == '__main__':

    class Strategy(Piped):

        #
        # - ochopod will detect cases where the sub-process fails on a non-zero exit code
        # - if we can't get the sub-process to either exit normally or just keep running the sanity check will fail
        # - here we want to tolerate up to 3 sanity check failures in a row with 5 seconds between each
        #
        checks = 3

        check_every = 5.0

        shell = True

        def configure(self, _):

            #
            # - attempt something that will fail on a non-zero exit code
            # - ochopod will attempt to re-run the command but the next sanity check will automatically trip
            # - after 3 such failures the pod will be turned off automatically
            #
            return 'echo kaboom && exit 1', {}

    #
    # - if you run this script locally you will notice the pod will turn off after around 15 seconds
    # - simply type CTRL-C to exit
    #
    Pod().boot(Strategy, local=1)
