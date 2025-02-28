# Copyright 2019 Red Hat
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from __future__ import absolute_import

import contextlib
import os
import tempfile
import time

from oslo_log import log


from tobiko.common import _exception

LOG = log.getLogger(__name__)


def makedirs(name, mode=0o777, exist_ok=True):
    """Creates directory and its parents if directory doesn't exists.

    This emulates Python3 os.makedirs behavior[1]

    [1] https://docs.python.org/3/library/os.html#os.makedirs)
    """
    try:
        os.makedirs(name, mode)
    except Exception:
        if not exist_ok or not os.path.isdir(name):
            raise


@contextlib.contextmanager
def open_output_file(filename, mode='w', temp_dir=None, text=False):
    basename = os.path.basename(filename)
    dirname = os.path.dirname(filename)
    prefix, suffix = os.path.splitext(basename)
    prefix += '-'
    temp_fd, temp_filename = tempfile.mkstemp(prefix=prefix,
                                              suffix=suffix,
                                              dir=temp_dir or dirname,
                                              text=text)
    try:
        with os.fdopen(temp_fd, mode) as temp_stream:
            yield temp_stream
        os.rename(temp_filename, filename)
    finally:
        with _exception.exc_info():
            if os.path.isfile(temp_filename):
                os.remove(temp_filename)


def get_truncated_filename(filepath: str) -> str:
    check_time = time.strftime("%Y_%m_%d-%H-%M-%S")
    return f'{filepath}_checked_{check_time}'


def truncate_logfile(filepath):
    """append _checked to a ping statistics file once finished it's check"""
    os.rename(filepath, get_truncated_filename(filepath))
