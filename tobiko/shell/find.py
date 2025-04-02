# Copyright (c) 2020 Red Hat, Inc.
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

import math
import typing

import tobiko
from tobiko.shell import sh
from tobiko.shell import ssh
from tobiko.shell.sh import _command


class FilesNotFound(tobiko.TobikoException):
    message = ("Files not found (path={path}, name={name}, login={login}, "
               "exit_status={exit_status}):\n{stderr}")


NameType = typing.Union[None, str, typing.List[str]]
PathType = typing.Union[str, typing.Iterable[str]]


def find_files(path: _command.ShellCommandType,
               name: NameType = None,
               command: _command.ShellCommandType = 'find',
               max_depth: int = None,
               modified_since: tobiko.Seconds = None,
               ssh_client: ssh.SSHClientType = None,
               type: str = None,
               **execute_params) -> typing.List[str]:
    # pylint: disable=redefined-builtin
    if not path:
        raise ValueError("Path can't be empty")

    command_line = sh.shell_command(command) + path

    if max_depth is not None:
        command_line += f"-maxdepth '{max_depth}'"

    if type is not None:
        command_line += f"-type '{type}'"

    if name is not None:
        if isinstance(name, str):
            names = [name]
        else:
            names = list(name)
        if names:
            command_line += ' -o '.join(f"-name '{name}'" for name in names)

    if modified_since is not None:
        # round seconds to the next minute
        minutes = math.ceil(modified_since / 60.)
        command_line += f"-mmin {minutes}"

    result = sh.execute(command_line,
                        ssh_client=ssh_client,
                        expect_exit_status=None,
                        **execute_params)
    file_names: typing.List[str] = [line.strip()
                                    for line in result.stdout.splitlines()
                                    if line.strip()]
    if not file_names:
        ssh_client = ssh.ssh_client_fixture(ssh_client)
        login: typing.Optional[str] = None
        if ssh_client is not None:
            login = ssh_client.login
        raise FilesNotFound(path=path,
                            name=name,
                            login=login,
                            exit_status=result.exit_status,
                            stderr=result.stderr.strip())
    return file_names
