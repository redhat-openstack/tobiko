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
                          interval: int = None,
                          logfile: str = None,
                          run_in_background: bool = False) \
        -> typing.Dict:
    params_timeout: typing.Optional[int] = None
    if run_in_background:
        params_timeout = 0
    elif timeout is not None:
        params_timeout = int(timeout - 0.5)

    # json_stream option should be set when:
    # - tests are run_in_background
    # - tests are executed from a VM instance
    # This way we avoid using that option from the test machine (undercloud,
    # test pod, devstack, ...) where it is not supported
    # iperf3 support this option from version 3.17
    json_stream = run_in_background and (ssh_client is not None)

    parameters = _parameters.iperf3_client_parameters(
        address=address, bitrate=bitrate,
        download=download, port=port, protocol=protocol,
        timeout=params_timeout, interval=interval,
        json_stream=json_stream, logfile=logfile)
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


def _get_iperf3_log_raw(logfile: str,
                        ssh_client: ssh.SSHClientType = None):
    for attempt in tobiko.retry(timeout=60, interval=5):
        # download the iperf results file to local
        if ssh_client is not None:
            local_tmp_file = sh.local_shell_connection().make_temp_file()
            try:
                sh.get_file(logfile, local_tmp_file, ssh_client)
            except FileNotFoundError as err:
                message = f'Failed to download iperf log file. Error {err}'
                if attempt.is_last:
                    tobiko.fail(message)
                else:
                    LOG.debug(message)
                    LOG.debug('Retrying to download iperf log file...')
                    continue
            local_logfile = local_tmp_file
        else:
            local_logfile = logfile

        # this command has to be run locally
        iperf_log_raw = sh.execute(f"cat {local_logfile}").stdout

        iperf_log_raw = remove_log_lines_end_json_str(iperf_log_raw)
        LOG.debug(f'iperf log raw: {iperf_log_raw} ')

        # return if iperf_log_raw is not empty or if this is
        # called after the creation of the iperf background process
        if iperf_log_raw:
            return iperf_log_raw
        if not config.is_prevent_create():
            LOG.debug('iperf log file empty, which is normal after background '
                      'process creation')
            return  # return None

        if attempt.is_last:
            tobiko.fail('Failed empty iperf file.')


def parse_json_stream_output(iperf_log_raw):
    # Logs are printed by iperf3 client to the stdout or file in json
    # format, but the format is different than what is stored
    # without "--json-stream" option
    # So to be able to validate them in the same way, logs
    # need to be converted
    iperf3_results_data: dict = {
        "intervals": []
    }
    for log_line in iperf_log_raw.splitlines():
        log_line_json = json.loads(log_line)
        if log_line_json.get('event') != 'interval':
            continue
        iperf3_results_data["intervals"].append(
            log_line_json["data"])

    return iperf3_results_data


def check_iperf3_client_results(address: typing.Union[str, netaddr.IPAddress],
                                output_dir: str = 'tobiko_iperf_results',
                                ssh_client: ssh.SSHClientType = None,
                                **kwargs):  # noqa; pylint: disable=W0613
    logfile = get_iperf3_logs_filepath(address, output_dir, ssh_client)
    iperf_log_raw = _get_iperf3_log_raw(logfile, ssh_client)
    if not iperf_log_raw and not config.is_prevent_create():
        LOG.debug('empty iperf log file is ok when TOBIKO_PREVENT_CREATE is '
                  'disabled')
        return

    try:
        iperf_log = json.loads(iperf_log_raw)
    except json.JSONDecodeError:
        iperf_log = parse_json_stream_output(iperf_log_raw)
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
        last_line = lines[-1].strip()
        if len(last_line) > 0 and last_line[-1] == "}":
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
        # wait until iperf client process disappears
        sh.wait_for_processes(timeout=120,
                              sleep_interval=5,
                              ssh_client=ssh_client,
                              pid=pid)


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
        # wait until iperf server process disappears
        sh.wait_for_processes(timeout=120,
                              sleep_interval=5,
                              ssh_client=ssh_client,
                              pid=pid)
