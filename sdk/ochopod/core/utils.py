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
import time

from copy import deepcopy
from subprocess import Popen, PIPE


def merge(left, right):
    """
    Recursive dict merge handling nested lists & dicts.

    :type left: dict
    :param left: dict to be merged
    :type right: dict
    :param right: dict to merge with
    :rtype: dict
    """

    if not isinstance(right, dict):
        return right

    merged = deepcopy(left)
    for k, v in right.iteritems():
        if k in merged and isinstance(merged[k], dict):
            merged[k] = merge(merged[k], v)
        elif k in merged and isinstance(v, list) and isinstance(merged[k], list):
            merged[k] = merged[k] + deepcopy(v)
        else:
            merged[k] = deepcopy(v)

    return merged


def retry(timeout, pause=5.0, default=None):
    """
    Decorator implementing a simple unconditional re-try policy, e.g it will invoke the decorated
    method again upon any exception. If we keep invoking for too long a :class:`AssertionError` will be
    raised unless a default return value is defined.

    :type timeout: float
    :param timeout: maximum amount of time in seconds we will keep re-trying for
    :type pause: float
    :param pause: amount of time in seconds we'll pause for before retrying
    :type default: anything
    :param default: optional value to return upon a timeout
    """

    def decorator(func):
        def wrapper(*args, **kwargs):
            ts = time.time()
            while 1:
                try:

                    return func(*args, **kwargs)

                except Exception as _:

                    bad = time.time() - ts > timeout
                    if bad and default is None:
                        assert 0, 'timeout exceeded @ %s()' % func.__name__
                    elif bad:
                        return default
                    else:
                        time.sleep(pause)

        return wrapper
    return decorator


def shell(snippet):
    """
    Helper invoking a shell command and returning its stdout broken down by lines as a list. The sub-process
    exit code is also returned.

    :type snippet: str
    :param snippet: shell snippet, e.g "echo foo > /bar"
    :rtype: (int, list) 2-uple
    """

    pid = Popen(snippet, shell=True, stdout=PIPE, stderr=PIPE)
    pid.wait()
    code = pid.returncode
    out = pid.stdout.read().split('\n')
    return code, out
