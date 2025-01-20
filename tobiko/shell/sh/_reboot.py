# Copyright 2020 Red Hat
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

import enum
import typing  # noqa

from oslo_log import log

import tobiko
from tobiko.shell import ping
from tobiko.shell.sh import _command
from tobiko.shell.sh import _uptime
from tobiko.shell import ssh


LOG = log.getLogger(__name__)


class RebootHostMethod(enum.Enum):

    SOFT = '/sbin/reboot',
    HARD = 'echo 1 > /proc/sys/kernel/sysrq && echo b > /proc/sysrq-trigger',
    CRASH = 'echo 1 > /proc/sys/kernel/sysrq && echo c > /proc/sysrq-trigger',

    def __init__(self, command: str):
        self.command = command


class RebootHostError(tobiko.TobikoException):
    message = "host {hostname!r} not rebooted: {cause}"


class RebootHostTimeoutError(RebootHostError):
    message = "host {hostname!r} not rebooted after {timeout!s} seconds"


def reboot_host(ssh_client: ssh.SSHClientFixture,
                wait: bool = True,
                timeout: tobiko.Seconds = None,
                method: RebootHostMethod = RebootHostMethod.SOFT):
    reboot = RebootHostOperation(ssh_client=ssh_client,
                                 timeout=timeout,
                                 method=method)
    tobiko.setup_fixture(reboot)
    if wait:
        try:
            # when pings are not replied, the reboot operation starts
            # in some cases the reboot is fast enough and no pings are
            # unreplied - do not fail in such a case and check uptime instead
            ping.wait_for_ping_hosts([ssh_client.host],
                                     check_unreachable=True,
                                     retry_timeout=30.)
        except ping.ReachableHostsException:
            LOG.exception("no unreplied pings were found - let's check uptime")
        reboot.wait_for_operation()
    return reboot


class RebootHostOperation(tobiko.Operation):

    default_wait_timeout = 300.
    default_wait_interval = 5.
    default_wait_count = 60

    def __init__(self,
                 ssh_client: ssh.SSHClientFixture,
                 timeout: tobiko.Seconds = None,
                 method: RebootHostMethod = RebootHostMethod.SOFT):
        super(RebootHostOperation, self).__init__()
        tobiko.check_valid_type(ssh_client, ssh.SSHClientFixture)
        tobiko.check_valid_type(method, RebootHostMethod)
        self.is_rebooted = False
        self.method = method
        self.ssh_client = ssh_client
        self.start_time: tobiko.Seconds = None
        self.timeout = tobiko.to_seconds(timeout)

    def run_operation(self):
        self.is_rebooted = False
        self.start_time = None
        for attempt in tobiko.retry(
                timeout=self.timeout,
                default_timeout=self.default_wait_timeout,
                default_count=self.default_wait_count,
                default_interval=self.default_wait_interval):
            try:
                channel = self.ssh_client.connect(
                    connection_timeout=attempt.time_left,
                    retry_count=1)
                LOG.info("Executing reboot command on host "
                         f"'{self.hostname}' (command='{self.command}')... ")
                self.start_time = tobiko.time()
                channel.exec_command(str(self.command))
            except Exception as ex:
                if attempt.time_left > 0.:
                    LOG.debug(f"Unable to reboot remote host "
                              f"(time_left={attempt.time_left}): {ex}")
                else:
                    LOG.exception(f"Unable to reboot remote host: {ex}")
                    raise RebootHostTimeoutError(
                        hostname=self.hostname or self.ssh_client.host,
                        timeout=attempt.timeout) from ex
            else:
                LOG.info(f"Host '{self.hostname}' is rebooting "
                         f"(command='{self.command}').")
                break
            finally:
                # Ensure we close connection after rebooting command
                self.ssh_client.close()

    def cleanup_fixture(self):
        self.is_rebooted = False
        self.start_time = None

    @property
    def command(self) -> _command.ShellCommand:
        return _command.shell_command(
            ['sudo', '/bin/sh', '-c', self.method.command])

    @property
    def hostname(self) -> str:
        return self.ssh_client.hostname

    @property
    def elapsed_time(self) -> tobiko.Seconds:
        if self.start_time is None:
            return None
        else:
            return tobiko.time() - self.start_time

    @property
    def time_left(self) -> tobiko.Seconds:
        if self.timeout is None or self.elapsed_time is None:
            return None
        else:
            return self.timeout - self.elapsed_time

    def wait_for_operation(self, timeout: tobiko.Seconds = None):
        if self.is_rebooted:
            return
        try:
            for attempt in tobiko.retry(
                    timeout=tobiko.min_seconds(timeout, self.time_left),
                    default_timeout=self.default_wait_timeout,
                    default_count=self.default_wait_count,
                    default_interval=self.default_wait_interval):
                # ensure SSH connection is closed before retrying connecting
                tobiko.cleanup_fixture(self.ssh_client)
                assert self.ssh_client.client is None
                LOG.debug(f"Getting uptime after reboot '{self.hostname}' "
                          "after reboot... ")
                try:
                    up_time = _uptime.get_uptime(ssh_client=self.ssh_client,
                                                 timeout=30.)

                except Exception:
                    # if disconnected while getting up time we assume the VM is
                    # just rebooting. These are good news!
                    LOG.debug("Unable to get uptime from host "
                              f"'{self.hostname}'", exc_info=1)
                    attempt.check_limits()
                else:
                    # verify that reboot actually happened by comparing elapsed
                    # time with up_time
                    elapsed_time = self.elapsed_time
                    if up_time < elapsed_time:
                        assert self.ssh_client.client is not None
                        self.is_rebooted = True
                        LOG.debug(f"Host '{self.hostname}' restarted "
                                  f"{elapsed_time} seconds after "
                                  f"reboot operation (up_time={up_time})")
                        break
                    else:
                        LOG.debug(f"Host '{self.hostname}' still not "
                                  f"restarted {elapsed_time} seconds after "
                                  f"reboot operation (up_time={up_time!r})")
                        attempt.check_limits()
        finally:
            if not self.is_rebooted:
                self.ssh_client.close()
