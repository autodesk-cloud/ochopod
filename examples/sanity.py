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
This script illustrates how we handle process level sanity checks. This is an optional feature which lets you
customize how you want ochopod to know what you're running is healthy. You could curl the process or run some script
for instance.

Too many sanity check failures will turn the pod off (which can be seen in the CLI for instance). Just start a local
standalone Zookeeper server and run "python sanity.py".
"""

from ochopod.bindings.ec2.marathon import Pod
from ochopod.models.piped import Actor as Piped


if __name__ == '__main__':

    class Strategy(Piped):

        #
        # - by default ochopod will only allow for one single sanity check to fail before turning off the pod
        # - you can specify both how many times you are ready to fail and how much time should go by in between
        # - here we want to tolerate up to 3 sanity check failures in a row with 5 seconds between each
        #
        checks = 3

        check_every = 5.0

        def sanity_check(self, _):

            #
            # - this optional callback will be invoked by ochopod on a regular basis
            # - you can do whatever you want inside and the goal is to not throw
            # - you can for instance simply assert if something is not right
            # - let's make it fail for the sake of illustration
            # - the callback will be invoked (and will blow up) every 5 seconds up to 3 times
            #
            assert 0, 'let us fail the sanity check just for fun'

        def configure(self, _):

            #
            # - just go to sleep, the point is not to run anything meaningful
            # - the sanity-check will keep failing until the pod turns off
            #
            return 'sleep 3600', {}

    #
    # - if you run this script locally you will notice the pod will turn off after around 15 seconds
    # - simply type CTRL-C to exit
    #
    Pod().boot(Strategy, local=1)
