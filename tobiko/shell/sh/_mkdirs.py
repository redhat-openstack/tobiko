# Copyright (c) 2021 Red Hat, Inc.
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


from tobiko.shell.sh import _execute
from tobiko.shell import ssh


def make_remote_dirs(file_name: str,
                     ssh_client: ssh.SSHClientType = None,
                     sudo: bool = None):
    _execute.execute(f'mkdir -p "{file_name}"',
                     ssh_client=ssh_client,
                     sudo=sudo)
