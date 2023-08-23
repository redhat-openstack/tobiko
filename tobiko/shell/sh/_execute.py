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

import collections
import enum

from oslo_log import log

import tobiko
from tobiko.shell.sh import _exception
from tobiko.shell.sh import _process


LOG = log.getLogger(__name__)


DATA_TYPES = (str, bytes)


@enum.unique
class ShellExecuteStatus(enum.Enum):
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    TIMEDOUT = 'TIMEDOUT'
    UNTERMINATED = 'UNTERMINATED'


def execute_result(command, exit_status=None, timeout=None,
                   status=None, login=None, stdin=None, stdout=None,
                   stderr=None, decode_streams=True):
    command = str(command)
    if exit_status is not None:
        exit_status = int(exit_status)
    if timeout is not None:
        timeout = float(timeout)
    if status is not None:
        status = ShellExecuteStatus(status)
    if decode_streams:
        stdin = _process.str_from_stream(stdin)
        stdout = _process.str_from_stream(stdout)
        stderr = _process.str_from_stream(stderr)
    else:
        stdin = _process.bytes_from_stream(stdin)
        stdout = _process.bytes_from_stream(stdout)
        stderr = _process.bytes_from_stream(stderr)
    return ShellExecuteResult(command=command,
                              exit_status=exit_status,
                              timeout=timeout,
                              status=status,
                              stdin=stdin,
                              stdout=stdout,
                              stderr=stderr,
                              login=login)


class ShellExecuteResult(collections.namedtuple(
        'ShellExecuteResult', ['command', 'exit_status', 'timeout', 'status',
                               'login', 'stdin', 'stdout', 'stderr'])):

    _details = None

    @property
    def details(self):
        details = self._details
        if details is None:
            self._details = details = self.get_details()
        return details

    def get_details(self):
        details = []
        details.append("command: {!r}".format(self.command))

        exit_status = self.exit_status
        if exit_status is not None:
            details.append("exit_status: {!r}".format(exit_status))

        timeout = self.timeout
        if timeout is not None:
            details.append("timeout: {!r}".format(timeout))

        status = self.status
        if status is not None:
            details.append("status: {!s}".format(status))

        login = self.login
        if login is not None:
            details.append("login: {!r}".format(login))

        stdin = self.stdin
        if stdin:
            details.append("stdin:\n{!s}".format(_indent(stdin)))

        stdout = self.stdout
        if stdout:
            details.append("stdout:\n{!s}".format(_indent(stdout)))

        stderr = self.stderr
        if stderr:
            details.append("stderr:\n{!s}".format(_indent(stderr)))
        return '\n'.join(details)

    def format(self):
        return self.details


def _indent(text, space='    ', newline='\n'):
    text = str(text)
    return space + (newline + space).join(text.split(newline))


def execute(command, environment=None, timeout=None, shell=None,
            stdin=None, stdout=None, stderr=None, ssh_client=None,
            expect_exit_status=0, decode_streams=True, **kwargs):
    """Execute command inside a remote or local shell

    :param command: command argument list

    :param timeout: command execution timeout in seconds

    :param check: when False it doesn't raises ShellCommandError when
    exit status is not zero. True by default

    :param ssh_client: SSH client instance used for remote shell execution

    :raises ShellTimeoutExpired: when timeout expires before command execution
    terminates. In such case it kills the process, then it eventually would
    try to read STDOUT and STDERR buffers (not fully implemented) before
    raising the exception.

    :raises ShellCommandError: when command execution terminates with non-zero
    exit status.
    """
    process = _process.process(command=command,
                               environment=environment,
                               timeout=timeout,
                               shell=shell,
                               stdin=stdin,
                               stdout=stdout,
                               stderr=stderr,
                               ssh_client=ssh_client,
                               **kwargs)
    login = getattr(ssh_client, 'login', None)
    return execute_process(process=process,
                           stdin=stdin,
                           login=login,
                           expect_exit_status=expect_exit_status,
                           decode_streams=decode_streams,
                           timeout=timeout)


def execute_process(process: _process.ShellProcessFixture,
                    stdin=None,
                    expect_exit_status=0,
                    login=None,
                    decode_streams=True,
                    timeout=None) \
        -> ShellExecuteResult:
    error = None
    status = None
    try:
        with process:
            if stdin and isinstance(stdin, DATA_TYPES):
                process.send_all(data=stdin, timeout=timeout)
    except _exception.ShellTimeoutExpired:
        status = ShellExecuteStatus.TIMEDOUT
        if expect_exit_status is not None:
            error = tobiko.exc_info()
    else:
        if expect_exit_status is not None:
            try:
                process.check_exit_status(expect_exit_status)
            except _exception.ShellCommandFailed:
                status = ShellExecuteStatus.FAILED
                error = tobiko.exc_info()
            except _exception.ShellProcessNotTerminated:
                status = ShellExecuteStatus.UNTERMINATED
            else:
                status = ShellExecuteStatus.SUCCEEDED

    result = execute_result(command=process.command,
                            exit_status=process.exit_status,
                            timeout=process.timeout,
                            status=status,
                            login=login,
                            stdin=process.stdin,
                            stdout=process.stdout,
                            stderr=process.stderr,
                            decode_streams=decode_streams)
    if error:
        LOG.info("Command error:\n%s\n", result.details)
        error.result = result
        error.reraise()

    LOG.debug("Command executed:\n%s\n", result.details)
    return result
