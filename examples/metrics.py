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
This script illustrates how you can report simple user metrics. Just start a local standalone Zookeeper server and run
"python metrics.py".
"""

from ochopod.bindings.generic.marathon import Pod
from ochopod.models.piped import Actor as Piped
from time import time

if __name__ == '__main__':

    class Strategy(Piped):

        check_every = 1.0

        pid = None

        since = 0.0

        def sanity_check(self, pid):

            #
            # - simply use the provided process ID to start counting time
            # - this is a cheap way to measure the sub-process up-time
            #
            if pid != self.pid:
                self.pid = pid
                self.since = time()

            lapse = (time() - self.since) / 60.0

            return {'uptime': '%.2f minutes (pid %s)' % (lapse, pid)}

        def configure(self, _):

            #
            # - just go to sleep, the point is not to run anything meaningful
            #
            return 'sleep 3600', {}

    #
    # - if you run this script locally and curl http://locahost:8080/info you will see the metrics.
    # - simply type CTRL-C to exit
    #
    Pod().boot(Strategy, local=1)
