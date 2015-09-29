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
import os
import logging

from ochopod.bindings.ec2.marathon import Pod as EC2Marathon
from ochopod.frameworks.marathon import Marathon
from ochopod.core.utils import shell

#: Our ochopod logger.
logger = logging.getLogger('ochopod')


class Pod(Marathon):
    """
    Implementation for the :class:`ochopod.frameworks.marathon.Marathon` base class.
    """

    def get_node_details(self):

        #
        # - try out the other marathon binding flavors
        # - use the first one that does not assert
        #
        candidates = \
            [
                EC2Marathon
            ]

        for binding in candidates:
            try:

                return binding().get_node_details()

            except:
                pass

        #
        # - nothing worked, default to using getent and $HOST as a last resort
        #
        def _peek(snippet):
            _, lines = shell(snippet)
            return lines[0] if lines else ''

        assert 'HOST' in os.environ, '$HOST not exported ?'

        return \
            {
                'ip':       _peek("getent ahostsv4 $HOST | grep STREAM | awk '{print $1}'"),
                'node':     os.environ['HOST']
            }