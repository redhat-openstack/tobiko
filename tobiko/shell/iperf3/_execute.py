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
from __future__ import division

import json
import os
import typing

import netaddr
from oslo_log import log

import tobiko
from tobiko import config
from tobiko.shell import files
from tobiko.shell.iperf3 import _interface
from tobiko.shell.iperf3 import _parameters
from tobiko.shell import sh
from tobiko.shell import ssh


CONF = config.CONF
LOG = log.getLogger(__name__)


def get_iperf3_logs_filepath(address: typing.Union[str, netaddr.IPAddress],
                             path: str,
                             ssh_client: ssh.SSHClientType = None) -> str:
    final_dir = files.get_home_absolute_filepath(path, ssh_client)
    filename = f'iperf_{address}.log'
    return os.path.join(final_dir, filename)


def get_bandwidth(address: typing.Union[str, netaddr.IPAddress],
                  bitrate: int = None,
                  download: bool = None,
                  port: int = None,
                  protocol: str = None,
                  ssh_client: ssh.SSHClientType = None,
                  timeout: tobiko.Seconds = None) -> float:
    iperf_measures = execute_iperf3_client(address=address,
                                           bitrate=bitrate,
                                           download=download,
                                           port=port,
                                           protocol=protocol,
                                           ssh_client=ssh_client,
                                           timeout=timeout)
    return calculate_bandwith(iperf_measures)


def calculate_bandwith(iperf_measures) -> float:
    # first interval is removed because BW measured during it is not
    # limited - it takes ~ 1 second to traffic shaping algorithm to apply
    # bw limit properly (buffer is empty when traffic starts being sent)
    intervals = iperf_measures['intervals'][1:]
    bits_received = sum([interval['sum']['bytes'] * 8
                         for interval in intervals])
    elapsed_time = sum([interval['sum']['seconds']
                        for interval in intervals])
    # bw in bits per second
    return bits_received / elapsed_time


def execute_iperf3_client(address: typing.Union[str, netaddr.IPAddress],
                          bitrate: int = None,
                          download: bool = None,
                          port: int = None,
                          protocol: str = None,
                          ssh_client: ssh.SSHClientType = None,
                          timeout: tobiko.Seconds = None,
                          logfile: str = None,
                          run_in_background: bool = False) \
        -> typing.Dict:
    params_timeout: typing.Optional[int] = None
    if run_in_background:
        params_timeout = 0
    elif timeout is not None:
        params_timeout = int(timeout - 0.5)
    parameters = _parameters.iperf3_client_parameters(
        address=address, bitrate=bitrate,
        download=download, port=port, protocol=protocol,
        timeout=params_timeout, logfile=logfile)
    command = _interface.get_iperf3_client_command(parameters)

    # output is a dictionary
    if run_in_background:
        process = sh.process(command, ssh_client=ssh_client)
        process.execute()
        return {}
    output = sh.execute(command,
                        ssh_client=ssh_client,
                        timeout=timeout).stdout
    return json.loads(output)


def execute_iperf3_client_in_background(
        address: typing.Union[str, netaddr.IPAddress],  # noqa; pylint: disable=W0613
        bitrate: int = None,
        download: bool = None,
        port: int = None,
        protocol: str = None,
        ssh_client: ssh.SSHClientType = None,
        iperf3_server_ssh_client: ssh.SSHClientType = None,
        output_dir: str = 'tobiko_iperf_results',
        **kwargs) -> None:
    output_path = get_iperf3_logs_filepath(address, output_dir, ssh_client)
    LOG.info(f'starting iperf3 client process to > {address} , '
             f'output file is : {output_path}')
    # just in case there is some leftover file from previous run,
    # it needs to be removed, otherwise iperf will append new log
    # to the end of the existing file and this will make json output
    # file to be malformed
    files.remove_old_logfile(output_path, ssh_client=ssh_client)
    # If there is ssh client for the server where iperf3 server is going
    # to run, lets make sure it is started fresh as e.g. in case of
    # failure in the previous run, it may report that is still "busy" thus
    # iperf3 client will not start properly
    if iperf3_server_ssh_client:
        _stop_iperf3_server(
            port=port, protocol=protocol,
            ssh_client=iperf3_server_ssh_client)
        start_iperf3_server(
            port=port, protocol=protocol,
            ssh_client=iperf3_server_ssh_client)

        if not _iperf3_server_alive(
                port=port, protocol=protocol,
                ssh_client=iperf3_server_ssh_client):
            testcase = tobiko.get_test_case()
            testcase.fail('iperf3 server did not start properly '
                          f'on the server {iperf3_server_ssh_client}')

    # Now, finally iperf3 client should be ready to start
    execute_iperf3_client(
        address=address,
        bitrate=bitrate,
        download=download,
        port=port,
        protocol=protocol,
        ssh_client=ssh_client,
        logfile=output_path,
        run_in_background=True)


def _get_iperf3_pid(
        address: typing.Union[str, netaddr.IPAddress, None] = None,
        port: int = None,
        protocol: str = None,
        ssh_client: ssh.SSHClientType = None) -> typing.Union[int, None]:
    if address:
        iperf_commands = [f'iperf3 .*{address}']
    elif protocol and protocol.lower() == 'udp':
        iperf_commands = [f'iperf3 .*-s .*-u .*-p {port}',
                          f'iperf3 .*-s .*-p {port} .*-u']
    else:
        iperf_commands = [f'iperf3 .*-s .*-p {port}']

    for iperf_command in iperf_commands:
        iperf_processes = sh.list_processes(command_line=iperf_command,
                                            ssh_client=ssh_client)
        if iperf_processes:
            return iperf_processes.unique.pid
    LOG.debug('no iperf3 processes were found')
    return None


def check_iperf3_client_results(address: typing.Union[str, netaddr.IPAddress],
                                output_dir: str = 'tobiko_iperf_results',
                                ssh_client: ssh.SSHClientType = None,
                                **kwargs):  # noqa; pylint: disable=W0613
    # This function expects that the result file is available locally already
    #
    logfile = get_iperf3_logs_filepath(address, output_dir, ssh_client)
    try:
        iperf_log_raw = sh.execute(
            f"cat {logfile}", ssh_client=ssh_client).stdout
    except sh.ShellCommandFailed as err:
        if config.is_prevent_create():
            # Tobiko is not expected to create resources in this run
            # so iperf should be already running and log file should
            # be already there, if it is not, it should fail
            tobiko.fail('Failed to read iperf log from the file. '
                        f'Server IP address: {address}; Logfile: {logfile}')
        else:
            # Tobiko is creating resources so it is normal that file was not
            # there yet
            LOG.debug(f'Failed to read iperf log from the file. '
                      f'Error: {err}')
            return

    # avoid test failure is iperf advertise some error/warning
    iperf_log_raw = remove_log_lines_end_json_str(iperf_log_raw)

    LOG.debug(f'iperf log raw: {iperf_log_raw} ')
    if not iperf_log_raw:
        if config.is_prevent_create():
            # Tobiko is not expected to create resources in this run
            # so iperf should be already running and log file should
            # be already there and not empty. If it is not,
            # it should fail
            tobiko.fail('Failed empty iperf file.')
        else:
            LOG.debug('Failed client iperf log file empty')
            return

    iperf_log = json.loads(iperf_log_raw)
    longest_break = 0  # seconds
    breaks_total = 0  # seconds
    current_break = 0  # seconds
    intervals = iperf_log.get("intervals")
    if not intervals:
        tobiko.fail(f"No intervals data found in {logfile}")
    for interval in intervals:
        if interval["sum"]["bytes"] == 0:
            interval_duration = (
                interval["sum"]["end"] - interval["sum"]["start"])
            current_break += interval_duration
            if current_break > longest_break:
                longest_break = current_break
            breaks_total += interval_duration
        else:
            current_break = 0

    files.truncate_client_logfile(logfile, ssh_client)

    testcase = tobiko.get_test_case()
    testcase.assertLessEqual(longest_break,
                             CONF.tobiko.rhosp.max_traffic_break_allowed)
    testcase.assertLessEqual(breaks_total,
                             CONF.tobiko.rhosp.max_total_breaks_allowed)


def remove_log_lines_end_json_str(json_str: str) -> str:
    lines = json_str.splitlines()
    while lines:
        if lines[-1].strip() == "}":
            # Stop when we find }
            break
        # Remove last line, remove possible error logs
        lines.pop()
    return "\n".join(lines)


def iperf3_client_alive(address: typing.Union[str, netaddr.IPAddress],  # noqa; pylint: disable=W0613
                        ssh_client: ssh.SSHClientType = None,
                        **kwargs) -> bool:
    return bool(_get_iperf3_pid(address=address, ssh_client=ssh_client))


def stop_iperf3_client(address: typing.Union[str, netaddr.IPAddress],
                       ssh_client: ssh.SSHClientType = None,
                       **kwargs):  # noqa; pylint: disable=W0613
    pid = _get_iperf3_pid(address=address, ssh_client=ssh_client)
    if pid:
        LOG.info(f'iperf3 client process to > {address} already running '
                 f'with PID: {pid}')
        sh.execute(f'kill {pid}', ssh_client=ssh_client, sudo=True)


def start_iperf3_server(
        port: typing.Union[int, None],
        protocol: typing.Union[str, None],
        ssh_client: ssh.SSHClientType):
    parameters = _parameters.iperf3_server_parameters(
        port=port, protocol=protocol)
    command = _interface.get_iperf3_server_command(parameters)
    process = sh.process(command, ssh_client=ssh_client)
    process.execute()


def _iperf3_server_alive(
        port: typing.Union[int, None],
        protocol: typing.Union[str, None],
        ssh_client: ssh.SSHClientType = None) -> bool:
    return bool(
        _get_iperf3_pid(port=port, protocol=protocol,
                        ssh_client=ssh_client))


def _stop_iperf3_server(
        port: typing.Union[int, None],
        protocol: typing.Union[str, None],
        ssh_client: ssh.SSHClientType = None):
    pid = _get_iperf3_pid(port=port, protocol=protocol, ssh_client=ssh_client)
    if pid:
        LOG.info(f'iperf3 server listening on the {protocol} port: {port} '
                 f'is already running with PID: {pid}')
        sh.execute(f'sudo kill {pid}', ssh_client=ssh_client)
