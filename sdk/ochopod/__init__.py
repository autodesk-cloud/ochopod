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

from logging import DEBUG, INFO, Formatter
from logging.config import fileConfig
from logging.handlers import RotatingFileHandler
from os.path import dirname

#: our package version
__version__ = '1.0.2'

#: the location on disk used for reporting back to the CLI (e.g. our rotating file log)
LOG = '/var/log/ochopod.log'

#
# - load our logging configuration from resources/log.cfg
# - make sure to not reset existing loggers
#
fileConfig('%s/resources/log.cfg' % dirname(__file__), disable_existing_loggers=False)


def enable_cli_log(debug=0):
    """
    Use this helper to add a rotating file handler to the 'ochopod' logger. This file will be
    located in /var/log so that the CLI can go get it. This is typically used when your pod is simply running
    another python script (e.g you can log from that script and see it in the CLI).

    :type debug: boolean
    :param debug: true to switch debug logging on
    """

    #
    # - add a small capacity rotating log
    # - this will be persisted in the container's filesystem and retrieved via /log requests
    # - an IOError here would mean we don't have the permission to write to /var/log for some reason (just skip)
    #
    logger = logging.getLogger('ochopod')
    try:
        handler = RotatingFileHandler(LOG, maxBytes=32764, backupCount=3)
        handler.setLevel(INFO)
        handler.setFormatter(Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        logger.addHandler(handler)

    except IOError:
        pass

    #
    # - switch all handlers to DEBUG if requested
    #
    if debug:
        for handler in logger.handlers:
            handler.setLevel(DEBUG)