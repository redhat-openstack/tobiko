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
from tobiko.shell.iperf3 import _interface
from tobiko.shell.iperf3 import _parameters
from tobiko.shell import sh
from tobiko.shell import ssh


CONF = config.CONF
LOG = log.getLogger(__name__)


def _get_filepath(address: typing.Union[str, netaddr.IPAddress],
                  path: str,
                  ssh_client: ssh.SSHClientType = None) -> str:
    if ssh_client:
        final_dir = _get_remote_filepath(path, ssh_client)
    else:
        final_dir = _get_local_filepath(path)
    filename = f'iperf_{address}.log'
    return os.path.join(final_dir, filename)


def _get_local_filepath(path: str) -> str:
    final_dir_path = f'{sh.get_user_home_dir()}/{path}'
    if not os.path.exists(final_dir_path):
        os.makedirs(final_dir_path)
    return final_dir_path


def _get_remote_filepath(path: str,
                         ssh_client: ssh.SSHClientType) -> str:
    homedir = sh.execute('echo ~', ssh_client=ssh_client).stdout.rstrip()
    final_dir_path = f'{homedir}/{path}'
    sh.execute(f'/usr/bin/mkdir -p {final_dir_path}',
               ssh_client=ssh_client)
    return final_dir_path


def _truncate_iperf3_client_logfile(
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


def _remove_old_logfile(logfile: str,
                        ssh_client: ssh.SSHClientType = None):
    if ssh_client:
        sh.execute(f'/usr/bin/rm -f {logfile}',
                   ssh_client=ssh_client)
    else:
        try:
            os.remove(logfile)
        except FileNotFoundError:
            pass


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
    output_path = _get_filepath(address, output_dir, ssh_client)
    LOG.info(f'starting iperf3 client process to > {address} , '
             f'output file is : {output_path}')
    # just in case there is some leftover file from previous run,
    # it needs to be removed, otherwise iperf will append new log
    # to the end of the existing file and this will make json output
    # file to be malformed
    _remove_old_logfile(output_path, ssh_client=ssh_client)
    # If there is ssh client for the server where iperf3 server is going
    # to run, lets make sure it is started fresh as e.g. in case of
    # failure in the previous run, it may report that is still "busy" thus
    # iperf3 client will not start properly
    if iperf3_server_ssh_client:
        _stop_iperf3_server(
            port=port, protocol=protocol,
            ssh_client=iperf3_server_ssh_client)
        _start_iperf3_server(
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
    try:
        iperf_pids = sh.execute(
            'pidof iperf3', ssh_client=ssh_client).stdout.rstrip().split(" ")
    except sh.ShellCommandFailed:
        return None
    for iperf_pid in iperf_pids:
        proc_cmdline = sh.get_command_line(
            iperf_pid,
            ssh_client=ssh_client)
        if address and str(address) in proc_cmdline:
            # This is looking for the iperf client instance
            return int(iperf_pid)
        elif port and protocol:
            # By looking for port and protocol we are looking
            # for the iperf3 server's PID
            if "-s" in proc_cmdline and f"-p {port}" in proc_cmdline:
                if ((protocol.lower() == 'udp' and "-u" in proc_cmdline) or
                        (protocol.lower() == 'tcp' and
                         '-u' not in proc_cmdline)):
                    return int(iperf_pid)
    return None


def check_iperf3_client_results(address: typing.Union[str, netaddr.IPAddress],
                                output_dir: str = 'tobiko_iperf_results',
                                ssh_client: ssh.SSHClientType = None,
                                **kwargs):  # noqa; pylint: disable=W0613
    # This function expects that the result file is available locally already
    #
    logfile = _get_filepath(address, output_dir, ssh_client)
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

    _truncate_iperf3_client_logfile(logfile, ssh_client)

    testcase = tobiko.get_test_case()
    testcase.assertLessEqual(longest_break,
                             CONF.tobiko.rhosp.max_traffic_break_allowed)
    testcase.assertLessEqual(breaks_total,
                             CONF.tobiko.rhosp.max_total_breaks_allowed)


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
        sh.execute(f'sudo kill {pid}', ssh_client=ssh_client)


def _start_iperf3_server(
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
