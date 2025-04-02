# Copyright (c) 2019 Red Hat, Inc.
#
# All Rights Reserved.
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

from os.path import expanduser

from oslo_log import log

import tobiko


LOG = log.getLogger(__name__)


def get_user_home_dir():
    """return a str path of the current user's home"""
    return expanduser("~")


class ExecutePathFixture(tobiko.SharedFixture):

    def __init__(self, executable_dirs=None, environ=None):
        super(ExecutePathFixture, self).__init__()
        self.executable_dirs = list(executable_dirs or
                                    [])  # type: typing.List[str]
        self.environ = dict(environ or {})  # type: typing.Dict[str, str]

    def setup_fixture(self):
        missing_dirs = []
        for executable_dir in self.executable_dirs:
            if (executable_dir not in self.path_dirs and
                    executable_dir not in missing_dirs):
                missing_dirs.append(executable_dir)
        if missing_dirs:
            new_path_dirs = missing_dirs + self.path_dirs
            self.addCleanup(self.remove_executable_dirs, missing_dirs)
            self.environ['PATH'] = ':'.join(new_path_dirs)
            LOG.debug('Directories added to executable path: %s',
                      ', '.join(sorted(new_path_dirs)))

    @property
    def path_dirs(self):
        return list(self.environ.get('PATH', '').split(':'))

    def remove_executable_dirs(self, removal_dirs):
        removal_dirs = set(removal_dirs) & set(self.path_dirs)
        if removal_dirs:
            new_path_dirs = [p
                             for p in self.path_dirs
                             if p not in removal_dirs]
            self.environ['PATH'] = ':'.join(new_path_dirs)
            LOG.debug('Directories removed from executable path: %s',
                      ', '.join(sorted(removal_dirs)))
