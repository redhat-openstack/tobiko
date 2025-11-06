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

import functools
import os

from oslo_log import log

import tobiko
from tobiko.shell.sh import _command
from tobiko.shell.sh import _exception
from tobiko.shell.sh import _execute
from tobiko.shell import ssh


LOG = log.getLogger(__name__)


class GetCommandLineError(tobiko.TobikoException):
    message = "Unable to get process command line: {error}"


class GetCommandLineMismatch(GetCommandLineError):
    message = ("Command line of process ({pid}) doesn't match its command "
               "({command}): {command_line}")


@functools.lru_cache(typed=True)
def get_command_line(pid: int,
                     ssh_client: ssh.SSHClientType = None,
                     command: str = None,
                     _cache_id: int = None) \
        -> _command.ShellCommand:
    try:
        output = _execute.execute(f'cat /proc/{pid}/cmdline',
                                  ssh_client=ssh_client).stdout
    except _exception.ShellCommandFailed as ex:
        raise GetCommandLineError(error=ex.stderr) from ex

    command_line = _command.ShellCommand(output.strip().split('\0')[:-1])
    if not command_line:
        raise GetCommandLineError(error="command line is empty")

    if command is not None and os.path.basename(command_line[0]) != command:
        raise GetCommandLineMismatch(pid=pid, command=command,
                                     command_line=command_line)
    return command_line
