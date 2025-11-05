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
    cmd = f'cat /proc/{pid}/cmdline'

    # Sometimes the `cat /proc/{pid}/cmdline` command gets stuck forever on
    # some machines. Due to this, we are running the command with timeout and
    # retrying it when it fails
    which_timeout = _execute.execute("which timeout",
                                     ssh_client=ssh_client,
                                     expect_exit_status=None)
    if which_timeout.exit_status == 0:
        cmd = f'timeout 1 {cmd}'

    for _ in tobiko.retry(timeout=60, interval=3):
        try:
            output = _execute.execute(cmd,
                                      ssh_client=ssh_client).stdout
        except _exception.ShellCommandFailed as ex:
            # Don't retry on legitimate errors like "No such file or directory"
            # (which means the PID doesn't exist)
            if 'No such file or directory' in ex.stderr:
                raise GetCommandLineError(error=ex.stderr) from ex
            # Retry on timeout or other transient errors
            LOG.error(f'Error getting command line for pid {pid}')
        else:
            break

    command_line = _command.ShellCommand(output.strip().split('\0')[:-1])
    if not command_line:
        raise GetCommandLineError(error="command line is empty")

    if command is not None and os.path.basename(command_line[0]) != command:
        raise GetCommandLineMismatch(pid=pid, command=command,
                                     command_line=command_line)
    return command_line
