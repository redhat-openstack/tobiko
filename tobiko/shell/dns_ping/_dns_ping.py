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
from oslo_log import log as logging

from tobiko.shell import custom_script
from tobiko.shell import files
from tobiko.shell import ssh


LOG = logging.getLogger(__name__)

TIMEOUT = 2  # seconds
LOG_FILE_NAME = "dns_ping.log"
DNS_PING_SCRIPT_NAME = "tobiko_dns_ping.sh"
DNS_PING_SCRIPT = """
#!/bin/bash

HOSTNAME_CMD=$(which hostname)
DATE_CMD=$(which date)
RESOLVE_CMD="$(which resolvectl) query --cache=no --legend=no --stale-data=no"

ip_address=$1;
fqdn=$2
output_file=$3;

rm $output_file;

# First get IP address(es) of the machine
server_ips=$($HOSTNAME_CMD --all-ip-addresses)

while true; do
    current_time=$(/usr/bin/date +"{time_format}");
    $RESOLVE_CMD $fqdn | grep -q $ip_address

    if [ $? -eq 0 ]; then
            response="{result_ok}";
    else
            response="{result_failed}";
    fi;
    echo "{output_result_line}" >> $output_file;
    sleep {timeout};
done;
""".format(  # noqa: E501
    time_format=custom_script.LOG_TIME_FORMAT,
    result_ok=custom_script.RESULT_OK,
    result_failed=custom_script.RESULT_FAILED,
    output_result_line=custom_script.LOG_RESULT_FORMAT,
    timeout=TIMEOUT,
)


def _ensure_script_is_on_server(ssh_client: ssh.SSHClientType) -> None:
    custom_script.ensure_script_is_on_server(
        DNS_PING_SCRIPT_NAME,
        DNS_PING_SCRIPT,
        ssh_client=ssh_client)


def _get_script_command(
        ip_address: typing.Union[str, netaddr.IPAddress],
        fqdn: str,
        ssh_client: ssh.SSHClientType) -> str:
    homedir = files.get_homedir(ssh_client)
    logfile_path = _get_logfile_path(ssh_client)
    return (f"bash {homedir}/{DNS_PING_SCRIPT_NAME} "
            f"{ip_address} {fqdn} {logfile_path}")


def _get_log_dir(ssh_client: ssh.SSHClientType = None) -> str:
    return custom_script.get_log_dir(
        "tobiko_dns_ping_results", ssh_client)


def _get_logfile_path(ssh_client: ssh.SSHClientType) -> str:
    return f"{_get_log_dir(ssh_client)}/{LOG_FILE_NAME}"


def _get_dns_ping_pid(
        ip_address: typing.Union[str, netaddr.IPAddress],
        fqdn: str,
        ssh_client: ssh.SSHClientType) -> typing.Union[int, None]:
    processes = custom_script.get_process_pid(
        command_line=_get_script_command(ip_address, fqdn, ssh_client),
        ssh_client=ssh_client)
    if not processes:
        LOG.debug('no DNS ping script found.')
    return processes


def start_dns_ping_process(
        ip_address: typing.Union[str, netaddr.IPAddress],
        fqdn: str,
        ssh_client: ssh.SSHClientType) -> None:
    _ensure_script_is_on_server(ssh_client)
    if dns_ping_process_alive(ip_address, fqdn, ssh_client):
        return
    custom_script.start_script(
        _get_script_command(ip_address, fqdn, ssh_client),
        ssh_client=ssh_client)


def stop_dns_ping_process(
        ip_address: typing.Union[str, netaddr.IPAddress],
        fqdn: str,
        ssh_client: ssh.SSHClientType) -> None:
    pid = _get_dns_ping_pid(ip_address, fqdn, ssh_client)
    if pid:
        custom_script.stop_script(pid, ssh_client=ssh_client)


def dns_ping_process_alive(
        ip_address: typing.Union[str, netaddr.IPAddress],
        fqdn: str,
        ssh_client: ssh.SSHClientType) -> bool:
    return bool(_get_dns_ping_pid(ip_address, fqdn, ssh_client))


def check_dns_ping_results(
        ssh_client: ssh.SSHClientType,  # noqa; pylint: disable=W0613
        **kwargs) -> None:
    # Source log file is on the guest vm so ssh_client needs to be used
    # to get it
    src_logfile = _get_logfile_path(ssh_client)
    # Destination is local to where Tobiko is running so no need to pass
    # ssh_client to get_log_dir() function this time
    dest_logfile = f"{_get_log_dir()}/{LOG_FILE_NAME}"
    custom_script.copy_log_file(src_logfile, dest_logfile, ssh_client)

    # Looking for the files locally so no need to pass ssh_client to the
    # _get_log_dir function
    logfiles = custom_script.get_log_files(
        glob_log_pattern=f"{_get_log_dir()}/{LOG_FILE_NAME}")

    custom_script.check_results(logfiles)
