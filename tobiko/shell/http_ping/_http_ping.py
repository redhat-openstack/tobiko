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
import os
import typing

import netaddr
from oslo_log import log as logging
from oslo_serialization import jsonutils
import requests

import tobiko
from tobiko import config
from tobiko.shell import sh
from tobiko.shell import ssh

TIMEOUT = 2  # seconds

RESULT_OK = "OK"
RESULT_FAILED = "FAILED"

CONF = config.CONF
LOG = logging.getLogger(__name__)


def get_log_dir():
    log_dir = f"{sh.get_user_home_dir()}/tobiko_http_ping_results"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
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
        except FileNotFoundError as err:
            message = f'Failed to download http ping log file. Error {err}'
            if attempt.is_last:
                tobiko.fail(message)
            else:
                LOG.debug(message)
                LOG.debug('Retrying to download http ping log file...')
                continue
        if attempt.is_last:
            tobiko.fail('Failed to download http ping log file.')


def get_logfile_name(
        server_ip: typing.Union[str, netaddr.IPAddress]):
    return f"http_ping_{server_ip}.log"


def check_http_ping_results(**kwargs):
    ssh_client = kwargs.get('ssh_client')
    server_ip = kwargs.get('server_ip')
    if ssh_client:
        if not server_ip:
            tobiko.fail("Server IP is required to check http ping log file.")
        logfile_name = get_logfile_name(server_ip)
        src_logfile = f"{get_log_dir()}/{logfile_name}"
        dest_logfile = f"{get_log_dir()}/{logfile_name}"
        _get_http_ping_log_file(src_logfile, dest_logfile, ssh_client)

    failure_limit = CONF.tobiko.rhosp.max_ping_loss_allowed
    logfile_name = get_logfile_name(server_ip)
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
