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

from datetime import datetime
import typing

import netaddr
from oslo_log import log as logging
import requests

import tobiko
from tobiko import config
from tobiko.shell import custom_script
from tobiko.shell import files
from tobiko.shell import ssh

TIMEOUT = 2  # seconds


CONF = config.CONF
LOG = logging.getLogger(__name__)

HTTP_PING_SCRIPT_NAME = "tobiko_http_ping.sh"
HTTP_PING_CURL_OUTPUT_FORMAT = "%{response_code}"
HTTP_PING_SCRIPT = """
url="http://$1";
output_file=$2;

rm $output_file

while true; do
    current_time=$(/usr/bin/date +"{time_format}");
    response_code=$(/usr/bin/curl -o /dev/null -s -I -w "{response_format}" $url);
    if [ "$response_code" -ge 200 ] && [ "$response_code" -lt 500 ]; then
            response="{result_ok}";
    else
            response="{result_failed}";
    fi;
    echo "{output_result_line}" >> $output_file;
    sleep {timeout};
done;
""".format(    # noqa: E501
    time_format=custom_script.LOG_TIME_FORMAT,
    response_format=HTTP_PING_CURL_OUTPUT_FORMAT,
    result_ok=custom_script.RESULT_OK,
    result_failed=custom_script.RESULT_FAILED,
    output_result_line=custom_script.LOG_RESULT_FORMAT,
    timeout=TIMEOUT,
)


def _ensure_http_ping_script_on_server(
        ssh_client: ssh.SSHClientType = None) -> None:
    custom_script.ensure_script_is_on_server(
        HTTP_PING_SCRIPT_NAME,
        HTTP_PING_SCRIPT,
        ssh_client=ssh_client)


def get_log_dir(
        ssh_client: ssh.SSHClientType = None) -> str:
    return custom_script.get_log_dir(
        "tobiko_http_ping_results", ssh_client)


def http_ping(
        server_ip: typing.Union[str, netaddr.IPAddress]) -> dict:
    headers = {"connection": "close"}
    result = {'time': str(datetime.now())}
    url = f"http://{server_ip}"
    try:
        response = requests.head(url, headers=headers, timeout=TIMEOUT)
        if (response.status_code >= requests.codes.ok and  # noqa; pylint: disable=no-member
                response.status_code < requests.codes.bad):  # noqa; pylint: disable=no-member
            result['response'] = custom_script.RESULT_OK
        else:
            result['response'] = custom_script.RESULT_FAILED
    except requests.exceptions.RequestException:
        result['response'] = custom_script.RESULT_FAILED
    return result


def _get_http_ping_script_command(
        server_ip: typing.Union[str, netaddr.IPAddress],
        ssh_client: ssh.SSHClientType = None):
    homedir = files.get_homedir(ssh_client)
    logfile = _get_logfile_path(server_ip, ssh_client)
    return f"bash {homedir}/{HTTP_PING_SCRIPT_NAME} {server_ip} {logfile}"


def _get_logfile_name(
        server_ip: typing.Union[str, netaddr.IPAddress]) -> str:
    return f"http_ping_{server_ip}.log"


def _get_logfile_path(
        server_ip: typing.Union[str, netaddr.IPAddress],
        ssh_client: ssh.SSHClientType = None):
    logdir_name = get_log_dir(ssh_client)
    logfile_name = _get_logfile_name(server_ip)
    return f"{logdir_name}/{logfile_name}"


def _get_http_ping_pid(
        server_ip: typing.Union[str, netaddr.IPAddress],
        ssh_client: ssh.SSHClientType = None):
    processes = custom_script.get_process_pid(
        command_line=_get_http_ping_script_command(
            server_ip, ssh_client),
        ssh_client=ssh_client)
    if not processes:
        LOG.debug(f'no http ping to server {server_ip} found.')
    return processes


def check_http_ping_results(**kwargs):
    ssh_client = kwargs.get('ssh_client')
    server_ip = kwargs.get('server_ip')
    if ssh_client:
        if not server_ip:
            tobiko.fail("Server IP is required to check http ping log file.")
        # Source log file is on the guest vm so ssh_client needs to be used
        # to get it
        src_logfile = _get_logfile_path(server_ip, ssh_client)
        dst_logfile_name = _get_logfile_name(server_ip)
        # Destination is local to where Tobiko is running so no need to pass
        # ssh_client to get_log_dir() function this time
        dest_logfile = f"{get_log_dir()}/{dst_logfile_name}"
        custom_script.copy_log_file(src_logfile, dest_logfile, ssh_client)

    logfile_name = _get_logfile_name(server_ip)
    logfiles = custom_script.get_log_files(
        glob_log_pattern=f"{get_log_dir()}/{logfile_name}")

    custom_script.check_results(logfiles)


def start_http_ping_process(
        server_ip: typing.Union[str, netaddr.IPAddress],
        ssh_client: ssh.SSHClientType = None):
    # ensure bash script is on host
    # run bash script
    _ensure_http_ping_script_on_server(ssh_client)
    if http_ping_process_alive(server_ip, ssh_client):
        return
    custom_script.start_script(
        _get_http_ping_script_command(
            server_ip, ssh_client),
        ssh_client=ssh_client)


def stop_http_ping_process(
        server_ip: typing.Union[str, netaddr.IPAddress],
        ssh_client: ssh.SSHClientType = None):
    pid = _get_http_ping_pid(server_ip, ssh_client)
    if pid:
        custom_script.stop_script(pid, ssh_client=ssh_client)


def http_ping_process_alive(
        server_ip: typing.Union[str, netaddr.IPAddress],
        ssh_client: ssh.SSHClientType = None):
    return bool(_get_http_ping_pid(server_ip, ssh_client))
