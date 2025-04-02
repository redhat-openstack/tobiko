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

import typing

import netaddr

from tobiko.tripleo import overcloud
from tobiko.shell import iperf3
from tobiko.shell import ping
from tobiko.shell import sh
from tobiko.shell import ssh


# Test is inteded for D/S env
@overcloud.skip_if_missing_overcloud
def check_or_start_background_vm_ping(
        server_ip: typing.Union[str, netaddr.IPAddress],
        ssh_client: ssh.SSHClientType = None):
    """Check if process exists, if so stop and check ping health
    if not : start a new separate ping process.
    Executes a Background ping to a vm floating_ip,
    this test is intended to be run and picked up again
    by the next tobiko run. Ping results are parsed
    and a failure is raised if ping failure is above a certain amount"""
    if ssh_client is None:
        sh.check_or_start_background_process(
            bg_function=ping.write_ping_to_file,
            bg_process_name='tobiko_background_ping',
            check_function=ping.check_ping_statistics,
            ping_ip=server_ip)
    else:
        sh.check_or_start_external_process(
            start_function=ping.execute_ping_in_background,
            check_function=ping.check_ping_results,
            liveness_function=ping.ping_alive,
            stop_function=ping.stop_ping,
            address=server_ip,
            ssh_client=ssh_client)


# Test is inteded for D/S env
@overcloud.skip_if_missing_overcloud
def check_or_start_background_iperf_connection(
        server_ip: typing.Union[str, netaddr.IPAddress],
        port: int,
        protocol: str,
        ssh_client: ssh.SSHClientType = None,
        iperf3_server_ssh_client: ssh.SSHClientType = None):
    """Check if process exists, if so stop and check ping health
    if not : start a new separate iperf client process.
    Iperf server runs on the vm which is behind IP address given
    as the 'server_ip'.
    If `iperf3_server_ssh_client` is given, Tobiko will make sure
    that iperf3 server is running on the server behind this ssh_client
    """
    sh.check_or_start_external_process(
        start_function=iperf3.execute_iperf3_client_in_background,
        check_function=iperf3.check_iperf3_client_results,
        liveness_function=iperf3.iperf3_client_alive,
        stop_function=iperf3.stop_iperf3_client,
        address=server_ip,
        port=port,
        protocol=protocol,
        ssh_client=ssh_client,
        iperf3_server_ssh_client=iperf3_server_ssh_client)
