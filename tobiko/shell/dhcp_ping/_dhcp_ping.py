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

from oslo_log import log as logging

from tobiko.shell import custom_script
from tobiko.shell import files
from tobiko.shell import ssh


LOG = logging.getLogger(__name__)

TIMEOUT = 2  # seconds
LOG_FILE_NAME = "dhcp_ping.log"
DHCP_PING_SCRIPT_NAME = "tobiko_dhcp_ping.sh"
DHCP_PING_SCRIPT = """
#!/bin/bash

HOSTNAME_CMD=$(which hostname)
DATE_CMD=$(which date)
NMAP_CMD="sudo $(which nmap) --script broadcast-dhcp-discover 2>/dev/null"

output_file=$1;

rm $output_file;

# First get IP address(es) of the machine
server_ips=$($HOSTNAME_CMD --all-ip-addresses)

while true; do
    current_time=$(/usr/bin/date +"{time_format}");
    nmap_response=$($NMAP_CMD | grep -i "ip offered" | cut -d ":" -f 2 | tr -d " ")


    if [ -n "$nmap_response" ] && [[ $server_ips = *$nmap_response* ]]; then
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
        DHCP_PING_SCRIPT_NAME,
        DHCP_PING_SCRIPT,
        ssh_client=ssh_client)


def _get_script_command(ssh_client: ssh.SSHClientType) -> str:
    homedir = files.get_homedir(ssh_client)
    logfile_path = _get_logfile_path(ssh_client)
    return f"bash {homedir}/{DHCP_PING_SCRIPT_NAME} {logfile_path}"


def _get_log_dir(ssh_client: ssh.SSHClientType = None) -> str:
    return custom_script.get_log_dir(
        "tobiko_dhcp_ping_results", ssh_client)


def _get_logfile_path(ssh_client: ssh.SSHClientType) -> str:
    return f"{_get_log_dir(ssh_client)}/{LOG_FILE_NAME}"


def _get_dhcp_ping_pid(
        ssh_client: ssh.SSHClientType) -> typing.Union[int, None]:
    processes = custom_script.get_process_pid(
        command_line=_get_script_command(ssh_client),
        ssh_client=ssh_client)
    if not processes:
        LOG.debug('no DHCP ping script found.')
    return processes


def _get_dhcp_ping_pids(
        ssh_client: ssh.SSHClientType) -> list:
    pids = custom_script.get_process_pids(
        command_line=_get_script_command(ssh_client),
        ssh_client=ssh_client)
    if not pids:
        LOG.debug('no DHCP ping script found.')
    return pids


def start_dhcp_ping_process(ssh_client: ssh.SSHClientType) -> None:
    _ensure_script_is_on_server(ssh_client)
    if dhcp_ping_process_alive(ssh_client):
        return
    custom_script.start_script(
        _get_script_command(ssh_client),
        ssh_client=ssh_client)


def stop_dhcp_ping_process(ssh_client: ssh.SSHClientType) -> None:
    pids = _get_dhcp_ping_pids(ssh_client)
    for pid in pids:
        custom_script.stop_script(pid, ssh_client=ssh_client)


def dhcp_ping_process_alive(ssh_client: ssh.SSHClientType) -> bool:
    return bool(_get_dhcp_ping_pid(ssh_client))


def check_dhcp_ping_results(ssh_client: ssh.SSHClientType) -> None:
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
