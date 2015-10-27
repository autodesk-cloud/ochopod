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

from ochopod.api import Tool
from ochopod.core.utils import shell

#: Our ochopod logger.
logger = logging.getLogger('ochopod')


class Shell(Tool):
    """
    Basic shell tool allowing to run arbitrary commands from the CLI.
    """

    tag = 'shell'

    def body(self, args, cwd):

        #
        # - simply execute the snippet from the temporary directory
        # - any file uploaded in the process will be found in there as well
        #
        return shell(args, cwd=cwd)
