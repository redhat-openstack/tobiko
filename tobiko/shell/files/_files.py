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


import os

import tobiko
from tobiko.shell import sh
from tobiko.shell import ssh


def get_homedir(ssh_client: ssh.SSHClientType = None) -> str:
    if ssh_client:
        return sh.execute(
            'echo ~', ssh_client=ssh_client).stdout.rstrip()
    else:
        return sh.get_user_home_dir()


def get_home_absolute_filepath(path: str,
                               ssh_client: ssh.SSHClientType = None) -> str:
    if ssh_client is None:
        return _get_local_filepath(path)
    else:
        return _get_remote_filepath(path, ssh_client)


def _get_local_filepath(path: str) -> str:
    final_dir_path = f'{sh.get_user_home_dir()}/{path}'
    if not os.path.exists(final_dir_path):
        os.makedirs(final_dir_path)
    return final_dir_path


def _get_remote_filepath(path: str,
                         ssh_client: ssh.SSHClientType) -> str:
    homedir = get_homedir(ssh_client)
    final_dir_path = f'{homedir}/{path}'
    sh.make_remote_dirs(final_dir_path, ssh_client=ssh_client)
    return final_dir_path


def truncate_client_logfile(
        logfile: str,
        ssh_client: ssh.SSHClientType = None) -> None:
    if ssh_client:
        _truncate_remote_logfile(logfile, ssh_client)
    else:
        tobiko.truncate_logfile(logfile)


def _truncate_remote_logfile(logfile: str,
                             ssh_client: ssh.SSHClientType) -> None:
    truncated_logfile = tobiko.get_truncated_filename(logfile)
    sh.execute(f'/usr/bin/mv {logfile} {truncated_logfile}',
               ssh_client=ssh_client)


def remove_old_logfile(logfile: str,
                       ssh_client: ssh.SSHClientType = None):
    if ssh_client:
        sh.execute(f'/usr/bin/rm -f {logfile}',
                   ssh_client=ssh_client)
    else:
        try:
            os.remove(logfile)
        except FileNotFoundError:
            pass
