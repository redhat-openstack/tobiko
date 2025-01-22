# Copyright (c) 2025 Red Hat, Inc.
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

from oslo_log import log

from tobiko.shell.sh import _execute
from tobiko.shell import ssh


LOG = log.getLogger(__name__)


def get_nm_connection_ids(ssh_client: ssh.SSHClientType = None) -> list:
    result = _execute.execute('nmcli -g UUID con',
                              ssh_client=ssh_client)
    return result.stdout.splitlines()


def get_nm_connection_values(connection: str,
                             values: str,
                             ssh_client: ssh.SSHClientType = None) -> list:
    result = _execute.execute(f'nmcli -g {values} con show "{connection}"',
                              ssh_client=ssh_client)
    return_values = []
    for line in result.stdout.splitlines():
        if line:
            for value in line.split('|'):
                # nmcli adds escape char before ":" and we need to remove it
                return_values.append(value.strip().replace('\\', ''))

    return return_values
