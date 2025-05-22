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

import glob
import json
import io
import os
import time
import typing


import netaddr
from oslo_log import log

import tobiko
from tobiko import config
from tobiko.shell import files
from tobiko.shell import sh
from tobiko.shell import ssh
from tobiko.shell.ping import _interface
from tobiko.shell.ping import _exception
from tobiko.shell.ping import _parameters
from tobiko.shell.ping import _statistics


CONF = config.CONF
LOG = log.getLogger(__name__)


TRANSMITTED = 'transmitted'
DELIVERED = 'delivered'
UNDELIVERED = 'undelivered'
RECEIVED = 'received'
UNRECEIVED = 'unreceived'


PingHostType = typing.Union['str', netaddr.IPAddress]


def list_reachable_hosts(hosts: typing.Iterable[PingHostType],
                         **params) -> tobiko.Selection[PingHostType]:
    reachable_host, _ = ping_hosts(hosts, **params)
    return reachable_host


def list_unreachable_hosts(hosts: typing.Iterable[PingHostType],
                           **params) -> tobiko.Selection[PingHostType]:
    _, unreachable_host = ping_hosts(hosts, **params)
    return unreachable_host


PingHostsResultType = typing.Tuple[tobiko.Selection[PingHostType],
                                   tobiko.Selection[PingHostType]]


def wait_for_ping_hosts(hosts: typing.Iterable[PingHostType],
                        check_unreachable=False,
                        retry_count: int = None,
                        retry_timeout: tobiko.Seconds = None,
                        retry_interval: tobiko.Seconds = None,
                        **params) \
        -> None:
    if retry_timeout is None:
        retry_timeout = params.get('timeout')
    LOG.debug("Wait for ping hosts:\n"
              f"  hosts: {hosts}\n"
              f"  check_unreachable: {check_unreachable}\n"
              f"  retry_count: {retry_count}\n"
              f"  retry_timeout: {retry_timeout}\n"
              f"  retry_interval: {retry_interval}\n"
              f"  **params: {params}\n")
    for attempt in tobiko.retry(count=retry_count,
                                timeout=retry_timeout,
                                interval=retry_interval,
                                default_timeout=300.,
                                default_interval=5.):
        reachable, unreachable = ping_hosts(hosts, **params)
        if check_unreachable:
            hosts = reachable
        else:
            hosts = unreachable
        if hosts:
            if attempt.is_last:
                if check_unreachable:
                    raise _exception.ReachableHostsException(
                        hosts=hosts,
                        timeout=attempt.timeout,
                        elapsed_time=attempt.elapsed_time) from None
                else:
                    raise _exception.UnreachableHostsException(
                        hosts=hosts,
                        timeout=attempt.timeout,
                        elapsed_time=attempt.elapsed_time) from None
        else:
            break

    else:
        raise RuntimeError('Broken retry loop')  # This is a bug


def ping_hosts(hosts: typing.Iterable[PingHostType],
               count: typing.Optional[int] = None,
               **params) -> PingHostsResultType:
    if count is None:
        count = 1
    else:
        count = int(count)
    reachable = tobiko.Selection[PingHostType]()
    unreachable = tobiko.Selection[PingHostType]()
    for host in hosts:
        try:
            result = ping(host, count=count, **params)
        except _exception.PingError:
            LOG.exception('Error pinging host: %r', host)
            unreachable.append(host)
        else:
            if result.received:
                reachable.append(host)
            else:
                unreachable.append(host)
    return reachable, unreachable


def ping(host: PingHostType, until=TRANSMITTED, check: bool = True,
         **ping_params) -> _statistics.PingStatistics:
    """Send ICMP messages to host address until timeout

    :param host: destination host address
    :param ping_params: parameters to be forwarded to :mod:`get_statistics`
        function
    :returns: PingStatistics
    """
    return get_statistics(host=host, until=until, check=check, **ping_params)


def ping_until_delivered(host, **ping_params):
    """Send 'count' ICMP messages

    Send 'count' ICMP messages

    ICMP messages are considered delivered when they have been
    transmitted without being counted as errors.

    :param host: destination host address
    :param ping_params: parameters to be forwarded to :mod:`get_statistics`
        function
    :returns: PingStatistics
    :raises: PingFailed in case timeout expires before delivering all
        expected count messages
    """
    return ping(host=host, until=DELIVERED, **ping_params)


def ping_until_undelivered(host, **ping_params):
    """Send ICMP messages until it fails to deliver messages

    Send ICMP messages until it fails to deliver 'count' messages

    ICMP messages are considered undelivered when they have been
    transmitted and they have been counted as error in ping statistics (for
    example because of errors into the route to remote address).

    :param host: destination host address
    :param ping_params: parameters to be forwarded to :mod:`get_statistics`
        function
    :returns: PingStatistics
    :raises: PingFailed in case timeout expires before failing delivering
        expected 'count' of messages
    """
    return ping(host=host, until=UNDELIVERED, **ping_params)


def ping_until_received(host, **ping_params):
    """Send ICMP messages until it receives messages back

    Send ICMP messages until it receives 'count' messages back

    ICMP messages are considered received when they have been
    transmitted without any routing errors and they are received back

    :param host: destination host address
    :param ping_params: parameters to be forwarded to :mod:`get_statistics`
        function
    :returns: PingStatistics
    :raises: PingFailed in case timeout expires before receiving all
        expected 'count' of messages
    """
    return ping(host=host, until=RECEIVED, **ping_params)


def ping_until_unreceived(host, **ping_params):
    """Send ICMP messages until it fails to receive messages

    Send ICMP messages until it fails to receive 'count' messages back.

    ICMP messages are considered unreceived when they have been
    transmitted without any routing error but they failed to be received
    back (for example because of network filtering).

    :param host: destination host address
    :param ping_params: parameters to be forwarded to :mod:`get_statistics`
        function
    :returns: PingStatistics
    :raises: PingFailed in case timeout expires before failed receiving
        expected 'count' of messages
    """
    return ping(host=host, until=UNRECEIVED, **ping_params)


def get_statistics(parameters=None, ssh_client=None, until=None, check=True,
                   **ping_params) -> _statistics.PingStatistics:
    parameters = _parameters.get_ping_parameters(default=parameters,
                                                 **ping_params)
    statistics = _statistics.PingStatistics()
    for partial_statistics in iter_statistics(parameters=parameters,
                                              ssh_client=ssh_client,
                                              until=until, check=check):
        statistics += partial_statistics
        LOG.debug("%r", statistics)

    return statistics


def iter_statistics(parameters=None, ssh_client=None, until=None, check=True,
                    **ping_params):
    parameters = _parameters.get_ping_parameters(default=parameters,
                                                 **ping_params)
    now = time.time()
    end_of_time = now + parameters.timeout
    deadline = parameters.deadline
    transmitted = 0
    received = 0
    undelivered = 0
    count = 0
    enlapsed_time = None

    while deadline > 0. and count < parameters.count:
        if enlapsed_time is not None and enlapsed_time < deadline:
            # Avoid busy waiting when errors happens
            sleep_time = deadline - enlapsed_time
            LOG.debug('Waiting %s seconds before next ping execution',
                      sleep_time)
            time.sleep(sleep_time)

        start_time = time.time()

        # splitting total timeout interval into smaller deadline intervals will
        # cause ping command to be executed more times allowing to handle
        # temporary packets routing problems
        if until == RECEIVED:
            execute_parameters = _parameters.get_ping_parameters(
                default=parameters,
                deadline=deadline,
                count=(parameters.count - count),
                timeout=end_of_time - now)
        else:
            # Deadline ping parameter cause ping to be executed until count
            # messages are received or deadline is expired
            # Therefore to count messages not of received type we have to
            # simulate deadline parameter limiting the maximum number of
            # transmitted messages
            execute_parameters = _parameters.get_ping_parameters(
                default=parameters,
                deadline=deadline,
                count=min(parameters.count - count,
                          parameters.interval * deadline),
                timeout=end_of_time - now)

        # Command timeout would typically give ping command additional seconds
        # to safely reach deadline before shell command timeout expires, while
        # in the same time adding an extra verification to forbid using more
        # time than expected considering the time required to make SSH
        # connection and running a remote shell
        output = execute_ping(parameters=execute_parameters,
                              ssh_client=ssh_client,
                              check=check)

        if output:
            statistics = _statistics.parse_ping_statistics(
                output=output, begin_interval=now,
                end_interval=time.time())

            yield statistics

            transmitted += statistics.transmitted
            received += statistics.received
            undelivered += statistics.undelivered
        else:
            # Assume 1 transmitted undelivered package when unable to get
            # ping output
            transmitted += 1
            undelivered += 1

        count = {None: 0,
                 TRANSMITTED: transmitted,
                 DELIVERED: transmitted - undelivered,
                 UNDELIVERED: undelivered,
                 RECEIVED: received,
                 UNRECEIVED: transmitted - received}[until]

        now = time.time()
        deadline = min(int(end_of_time - now), parameters.deadline)
        enlapsed_time = now - start_time
        if enlapsed_time > 0.:
            LOG.debug('Ping execution took %s seconds', enlapsed_time)

    if until and count < parameters.count:
        raise _exception.PingFailed(count=count,
                                    expected_count=parameters.count,
                                    timeout=parameters.timeout,
                                    message_type=until)


def execute_ping(parameters, ssh_client=None, check=True):
    command = _interface.get_ping_command(parameters=parameters,
                                          ssh_client=ssh_client)

    try:
        result = sh.execute(command=command,
                            ssh_client=ssh_client,
                            timeout=parameters.deadline + 3.,
                            expect_exit_status=None,
                            network_namespace=parameters.network_namespace)
    except (sh.ShellError, tobiko.RetryLimitError) as ex:
        LOG.exception("Error executing ping command")
        stdout = ex.stdout if hasattr(ex, "stdout") else None
        stderr = ex.stderr if hasattr(ex, "stderr") else None
    else:
        stdout = result.stdout
        stderr = result.stderr

    if stdout:
        output = str(stdout)
    else:
        output = None

    if stderr:
        error = str(stderr)
        if check and result.exit_status:
            handle_ping_command_error(error=error)

    return output


def handle_ping_command_error(error):
    for error in error.splitlines():
        error = error.strip()
        if error:
            prefix = 'ping: '
            if error.startswith('ping: '):
                error = error[len(prefix):]
            handle_ping_bad_address_error(error)
            handle_ping_local_error(error)
            handle_ping_connect_error(error)
            handle_ping_send_to_error(error)
            handle_ping_unknow_host_error(error)
            raise _exception.PingError(details=error)


def handle_ping_bad_address_error(text):
    prefix = 'bad address '
    if text.startswith(prefix):
        address = text[len(prefix):].replace("'", '').strip()
        raise _exception.BadAddressPingError(address=address)


def handle_ping_local_error(text):
    prefix = 'local error: '
    if text.startswith(prefix):
        details = text[len(prefix):].strip()
        raise _exception.LocalPingError(details=details)


def handle_ping_connect_error(text):
    prefix = 'connect: '
    if text.startswith(prefix):
        details = text[len(prefix):].strip()
        raise _exception.ConnectPingError(details=details)


def handle_ping_send_to_error(text):
    prefix = 'sendto: '
    if text.startswith(prefix):
        details = text[len(prefix):].strip()
        raise _exception.SendToPingError(details=details)


def handle_ping_unknow_host_error(text):
    prefix = 'unknown host'
    if text.startswith(prefix):
        details = text[len(prefix):].strip()
        raise _exception.UnknowHostError(details=details)

    prefix = 'unreachable-host: '
    if text.startswith(prefix):
        details = text[len(prefix):].strip()
        raise _exception.UnknowHostError(details=details)

    suffix = ': Name or service not known'
    if text.endswith(suffix):
        details = text[:-len(suffix)].strip()
        raise _exception.UnknowHostError(details=details)

    suffix = ': No route to host'
    if text.endswith(suffix):
        details = text[:-len(suffix)].strip()
        raise _exception.UnknowHostError(details=details)

    suffix = ': Unknown host'
    if text.endswith(suffix):
        details = text[:-len(suffix)].strip().split()[-1]
        raise _exception.UnknowHostError(details=details)


def ping_to_json(ping_result: _statistics.PingStatistics) -> str:
    '''Transform an iter_statistics.statistics object
    into a json string with ping ip and result'''
    destination = str(ping_result.destination)
    transmitted = ping_result.transmitted
    received = ping_result.received
    timestamp = time.ctime(ping_result.begin_interval)
    ping_result_line_dict = {"destination": destination,
                             "transmitted": transmitted,
                             "received": received,
                             "timestamp": timestamp}
    return json.dumps(ping_result_line_dict)


def write_ping_to_file(ping_ip=None, output_dir='tobiko_ping_results',
                       interval=None):
    '''use iter_statistics to ping a host and record statistics
    put results in output_dir filenames correlate with vm fip'''
    output_dir_path = f'{sh.get_user_home_dir()}/{output_dir}'
    if not os.path.exists(output_dir_path):
        os.makedirs(output_dir_path)
    output_filename = f'ping_{ping_ip}.log'
    output_path = os.path.join(output_dir_path, output_filename)
    LOG.info(f'starting ping process to > {ping_ip} , '
             f'output file is : {output_path}')
    ping_result_statistics = iter_statistics(parameters=None,
                                             host=ping_ip, until=None,
                                             timeout=99999,
                                             interval=interval,
                                             check=True)
    for ping_result in ping_result_statistics:
        with open(output_path, "at") as ping_result_file:
            ping_result_file.write(ping_to_json(ping_result) + "\n")
            time.sleep(5)


def get_vm_ping_log_files(glob_ping_log_pattern='tobiko_ping_results/ping_'
                                                '*.log'):
    """return a list of files mathcing : the pattern"""
    glob_path = f'{sh.get_user_home_dir()}/{glob_ping_log_pattern}'
    for filename in glob.glob(glob_path):
        LOG.info(f'found following ping_vm_log files {filename}')
        vm_ping_log_filename = filename
        yield vm_ping_log_filename


def check_ping_statistics():
    """Gets a list of ping_vm_log files and
    iterates their lines, checks if max ping
    failures have been reached per fip=file"""
    failure_limit = CONF.tobiko.rhosp.max_ping_loss_allowed
    ping_files_found = False
    # iterate over ping_vm_log files:
    for filename in list(get_vm_ping_log_files()):
        ping_files_found = True
        with io.open(filename, 'rt') as fd:
            LOG.info(f'checking ping log file: {filename}, '
                     f'failure_limit is :{failure_limit}')
            ping_failures_list = []
            for ping_line in fd.readlines():
                ping_line = json.loads(ping_line.rstrip())
                if ping_line['transmitted'] != ping_line['received']:
                    ping_failures_list.append(ping_line)

            ping_failures_len = len(ping_failures_list)
            if ping_failures_len > 0:
                ping_failures_str = '\n'.join(
                    [str(ping_failure) for ping_failure in ping_failures_list])
                LOG.warning(f'found ping failures:\n{ping_failures_str}')
            else:
                LOG.info(f'no failures in ping log file: {filename}')

            tobiko.truncate_logfile(filename)

            if ping_failures_len >= failure_limit:
                tobiko.fail(f'{ping_failures_len} pings failure found '
                            f'to vm fip destination: '
                            f'{ping_failures_list[-1]["destination"]}')

    if not ping_files_found:
        tobiko.fail('No ping log files found')


def skip_check_ping_statistics():
    for filename in list(get_vm_ping_log_files()):
        tobiko.truncate_logfile(filename)
        LOG.info(f'skipping ping failures in ping log file: {filename}')


def _get_ping_pid(
        address: typing.Union[str, netaddr.IPAddress, None] = None,
        ssh_client: ssh.SSHClientType = None) -> typing.Union[int, None]:
    ping_command = 'ping'
    if address is not None:
        ping_command += f' .*{address}'
    ping_processes = sh.list_processes(command_line=ping_command,
                                       ssh_client=ssh_client)
    if not ping_processes:
        LOG.debug('no ping processes were found')
        return None
    else:
        return ping_processes.unique.pid


def ping_alive(address: typing.Union[str, netaddr.IPAddress],  # noqa; pylint: disable=W0613
               ssh_client: ssh.SSHClientType = None,
               **kwargs) -> bool:
    return bool(_get_ping_pid(address=address, ssh_client=ssh_client))


def stop_ping(address: typing.Union[str, netaddr.IPAddress],
              ssh_client: ssh.SSHClientType = None,
              **kwargs):  # noqa; pylint: disable=W0613
    pid = _get_ping_pid(address=address, ssh_client=ssh_client)
    if pid:
        LOG.info(f'ping process to > {address} already running '
                 f'with PID: {pid}')
        # the SIGINT signal makes ping write the "ping statistics" block
        # before exiting
        sh.execute(f'kill -s SIGINT {pid}', ssh_client=ssh_client, sudo=True)


def _get_ping_logs_filepath(address: typing.Union[str, netaddr.IPAddress],
                            path: str,
                            ssh_client: ssh.SSHClientType = None) -> str:
    final_dir = files.get_home_absolute_filepath(path, ssh_client)
    filename = f'ping_{address}.log'
    return os.path.join(final_dir, filename)


# TODO(eolivare): replace check_ping_statistics with check_ping_results
def check_ping_results(address: typing.Union[str, netaddr.IPAddress],
                       output_dir: str = 'tobiko_ping_results',
                       ssh_client: ssh.SSHClientType = None,
                       **kwargs):  # noqa; pylint: disable=W0613
    testcase = tobiko.get_test_case()
    testcase.assertFalse(ping_alive(address, ssh_client))

    # This function expects that the result file is available locally already
    logfile = _get_ping_logs_filepath(address, output_dir, ssh_client)
    try:
        ping_log_raw = sh.execute(
            f"cat {logfile}", ssh_client=ssh_client).stdout
    except sh.ShellCommandFailed as err:
        if config.is_prevent_create():
            # Tobiko is not expected to create resources in this run
            # so ping should be already running and log file should
            # be already there, if it is not, it should fail
            tobiko.fail('Failed to read ping log from the file. '
                        f'Ping Destination IP address: {address}; '
                        f'Logfile: {logfile}')
        else:
            # Tobiko is creating resources so it is normal that file was not
            # there yet
            LOG.debug(f'Failed to read ping log from the file. '
                      f'Error: {err}')
            return

    LOG.debug(f'ping log raw: {ping_log_raw}')
    if not ping_log_raw:
        if config.is_prevent_create():
            # Tobiko is not expected to create resources in this run
            # so ping should be already running and log file should
            # be already there, if it is not, it should fail
            tobiko.fail('Failed empty ping file.')
        else:
            LOG.debug('Failed ping log file empty')
            return

    files.truncate_client_logfile(logfile, ssh_client)

    ping_stats = _statistics.parse_ping_statistics(ping_log_raw)

    testcase.assertGreater(ping_stats.transmitted, 0)
    testcase.assertGreater(ping_stats.received, 0)
    testcase.assertLessEqual(ping_stats.transmitted - ping_stats.received,
                             CONF.tobiko.rhosp.max_ping_loss_allowed)


def start_background_ping(address: typing.Union[str, netaddr.IPAddress],
                          output_path: str,
                          ssh_client: ssh.SSHClientType = None):
    parameters = _parameters.get_ping_parameters(host=address,
                                                 count=0,
                                                 deadline=0)
    command = _interface.get_ping_command(parameters, ssh_client)
    # both stdout and stderr need to be written to the provided log file
    command += '2>&1'
    command += f'> {output_path}'
    process = sh.process(command, ssh_client=ssh_client)
    process.execute()


# TODO(eolivare): replace write_ping_to_file with execute_ping_in_background
def execute_ping_in_background(address: typing.Union[str, netaddr.IPAddress],
                               output_dir: str = 'tobiko_ping_results',
                               ssh_client: ssh.SSHClientType = None,
                               **kwargs):  # noqa; pylint: disable=W0613
    output_path = _get_ping_logs_filepath(address, output_dir, ssh_client)
    LOG.info(f'starting ping process to > {address} , '
             f'output file is : {output_path}')
    # just in case there is some leftover file from previous run,
    # it needs to be removed, otherwise ping will append new log
    # to the end of the existing file and this will make output
    # file to be malformed
    files.remove_old_logfile(output_path, ssh_client=ssh_client)

    # Stop ping in case it is running
    stop_ping(address, ssh_client)

    # Start ping again
    start_background_ping(address, output_path, ssh_client)

    # if ping does not start properly, fail the test
    if not ping_alive(address, ssh_client):
        tobiko.fail('background ping process did not start')
