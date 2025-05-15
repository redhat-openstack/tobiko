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
import glob
import io
import typing

import netaddr
from oslo_log import log as logging
from oslo_serialization import jsonutils
import requests

import tobiko
from tobiko import config
from tobiko.shell import files
from tobiko.shell import sh
from tobiko.shell import ssh

TIMEOUT = 2  # seconds

RESULT_OK = "OK"
RESULT_FAILED = "FAILED"

CONF = config.CONF
LOG = logging.getLogger(__name__)

HTTP_PING_SCRIPT_NAME = "tobiko_http_ping.sh"
HTTP_PING_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%N"
HTTP_PING_CURL_OUTPUT_FORMAT = "%{response_code}"
HTTP_PING_RESULT_FORMAT = (
    '{\\"time\\": \\"$current_time\\", \\"response\\": \\"$response\\"}')
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
    time_format=HTTP_PING_TIME_FORMAT,
    response_format=HTTP_PING_CURL_OUTPUT_FORMAT,
    result_ok=RESULT_OK,
    result_failed=RESULT_FAILED,
    output_result_line=HTTP_PING_RESULT_FORMAT,
    timeout=TIMEOUT,
)


def _ensure_http_ping_script_on_server(
        ssh_client: ssh.SSHClientType = None):
    homedir = files.get_homedir(ssh_client)
    sh.execute(
        f"echo '{HTTP_PING_SCRIPT}' > {homedir}/{HTTP_PING_SCRIPT_NAME}",
        ssh_client=ssh_client)


def get_log_dir(
        ssh_client: ssh.SSHClientType = None):
    log_dir = files.get_home_absolute_filepath(
        "tobiko_http_ping_results", ssh_client)
    return log_dir


def _get_log_files(glob_log_pattern='http_ping_*.log'):
    """return a list of files matching : the pattern"""
    glob_path = f'{get_log_dir()}/{glob_log_pattern}'
    for filename in glob.glob(glob_path):
        LOG.info(f'found following log file {filename}')
        log_filename = filename
        yield log_filename


def http_ping(
        server_ip: typing.Union[str, netaddr.IPAddress]) -> dict:
    headers = {"connection": "close"}
    result = {'time': str(datetime.now())}
    url = f"http://{server_ip}"
    try:
        response = requests.head(url, headers=headers, timeout=TIMEOUT)
        if (response.status_code >= requests.codes.ok and  # noqa; pylint: disable=no-member
                response.status_code < requests.codes.bad):  # noqa; pylint: disable=no-member
            result['response'] = RESULT_OK
        else:
            result['response'] = RESULT_FAILED
    except requests.exceptions.RequestException:
        result['response'] = RESULT_FAILED
    return result


def _get_http_ping_log_file(
            src_logfile: str,
            dest_logfile: str,
            ssh_client: ssh.SSHClientType):
    for attempt in tobiko.retry(timeout=60, interval=5):
        # download the http ping results file to local
        try:
            sh.get_file(src_logfile, dest_logfile, ssh_client)
            # Remote log file can be now deleted so that logs from now will be
            # in the "clean" file if they will need to be checked later
            sh.execute(f'rm -f {src_logfile}', ssh_client=ssh_client)
            return
        except sh.ShellCommandFailed as err:
            message = f'Failed to download http ping log file. Error {err}'
            if attempt.is_last:
                tobiko.fail(message)
            else:
                LOG.debug(message)
                LOG.debug('Retrying to download http ping log file...')
                continue
        if attempt.is_last:
            tobiko.fail('Failed to download http ping log file.')


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
    processes = sh.list_processes(
        command_line=_get_http_ping_script_command(
            server_ip, ssh_client),
        ssh_client=ssh_client)
    if processes:
        return processes.unique.pid
    LOG.debug(f'no http ping to server {server_ip} found.')
    return None


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
        _get_http_ping_log_file(src_logfile, dest_logfile, ssh_client)

    failure_limit = CONF.tobiko.rhosp.max_ping_loss_allowed
    logfile_name = _get_logfile_name(server_ip)
    for filename in list(_get_log_files(glob_log_pattern=logfile_name)):
        with io.open(filename, 'rt') as fd:
            LOG.info(f'checking HTTP ping log file: {filename}, '
                     f'failure_limit is :{failure_limit}')
            failures_list = []
            for log_line in fd.readlines():
                log_line_json = jsonutils.loads(log_line.rstrip())
                if log_line_json['response'] != RESULT_OK:
                    # NOTE(salweq): Add file name to the failure line
                    #               just for the debugging purpose
                    log_line_json['filename'] = filename
                    failures_list.append(log_line_json)

            failures_len = len(failures_list)
            if failures_len > 0:
                failures_str = '\n'.join(
                    [str(failure) for failure in failures_list])
                LOG.warning(f'found HTTP ping failures:\n{failures_str}')
            else:
                LOG.debug(f'no failures in HTTP ping log file: {filename}')

            tobiko.truncate_logfile(filename)

            if failures_len >= failure_limit:
                tobiko.fail(f'{failures_len} HTTP pings failures found '
                            f'in file: {failures_list[-1]["filename"]}')


def start_http_ping_process(
        server_ip: typing.Union[str, netaddr.IPAddress],
        ssh_client: ssh.SSHClientType = None):
    # ensure bash script is on host
    # run bash script
    _ensure_http_ping_script_on_server(ssh_client)
    if http_ping_process_alive(server_ip, ssh_client):
        return
    process = sh.process(
        _get_http_ping_script_command(
            server_ip, ssh_client),
        ssh_client=ssh_client)
    process.execute()


def stop_http_ping_process(
        server_ip: typing.Union[str, netaddr.IPAddress],
        ssh_client: ssh.SSHClientType = None):
    pid = _get_http_ping_pid(server_ip, ssh_client)
    if pid:
        sh.execute(f'kill {pid}', ssh_client=ssh_client, sudo=True)
        # wait until http ping process disappears
        sh.wait_for_processes(timeout=120,
                              sleep_interval=5,
                              ssh_client=ssh_client,
                              pid=pid)


def http_ping_process_alive(
        server_ip: typing.Union[str, netaddr.IPAddress],
        ssh_client: ssh.SSHClientType = None):
    return bool(_get_http_ping_pid(server_ip, ssh_client))
