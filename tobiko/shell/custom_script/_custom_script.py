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

import glob
import io
import typing

from oslo_log import log as logging
from oslo_serialization import jsonutils

import tobiko
from tobiko import config
from tobiko.shell import files
from tobiko.shell import sh
from tobiko.shell import ssh
from tobiko.shell.custom_script import _constants


CONF = config.CONF
LOG = logging.getLogger(__name__)


def ensure_script_is_on_server(
        script_name: str,
        script: str,
        ssh_client: ssh.SSHClientType = None):
    homedir = files.get_homedir(ssh_client)
    sh.execute(
        f"echo '{script}' > {homedir}/{script_name}",
        ssh_client=ssh_client)


def get_log_dir(
        path: str,
        ssh_client: ssh.SSHClientType = None) -> str:
    return files.get_home_absolute_filepath(path, ssh_client)


def get_log_files(glob_log_pattern: str) -> typing.List[str]:
    """return a list of files matching : the pattern"""
    log_files = []
    for filename in glob.glob(glob_log_pattern):
        LOG.info(f'found following log file {filename}')
        log_files.append(filename)
    return log_files


def copy_log_file(
            src_logfile: str,
            dest_logfile: str,
            ssh_client: ssh.SSHClientType) -> None:
    for attempt in tobiko.retry(timeout=60, interval=5):
        # download the http ping results file to local
        try:
            sh.get_file(src_logfile, dest_logfile, ssh_client)
            # Remote log file can be now deleted so that logs from now will be
            # in the "clean" file if they will need to be checked later
            sh.execute(f'rm -f {src_logfile}', ssh_client=ssh_client)
            return
        except sh.ShellCommandFailed as err:
            message = f'Failed to download log file. Error {err}'
            if attempt.is_last:
                tobiko.fail(message)
            else:
                LOG.debug(message)
                LOG.debug('Retrying to download log file...')
                continue
        if attempt.is_last:
            tobiko.fail('Failed to download log file.')


def get_process_pid(
        command_line: str,
        ssh_client: ssh.SSHClientType = None
        ) -> typing.Union[int, None]:
    processes = sh.list_processes(
        command_line=command_line,
        ssh_client=ssh_client)
    if processes:
        return processes.first.pid
    return None


def get_process_pids(
        command_line: str,
        ssh_client: ssh.SSHClientType = None,
        ) -> list:
    processes = sh.list_processes(
        command_line=command_line,
        ssh_client=ssh_client)
    pids = []
    if processes:
        pids = [p.pid for p in processes]
    return pids


def check_results(
        log_filenames: typing.List[str]):

    failure_limit = CONF.tobiko.rhosp.max_ping_loss_allowed
    for filename in log_filenames:
        with io.open(filename, 'rt') as fd:
            LOG.info(f'checking custom script log file: {filename}, '
                     f'failure_limit is :{failure_limit}')
            failures_list = []
            for log_line in fd.readlines():
                log_line_json = jsonutils.loads(log_line.rstrip())
                if log_line_json['response'] != _constants.RESULT_OK:
                    # NOTE(salweq): Add file name to the failure line
                    #               just for the debugging purpose
                    log_line_json['filename'] = filename
                    failures_list.append(log_line_json)

            failures_len = len(failures_list)
            if failures_len > 0:
                failures_str = '\n'.join(
                    [str(failure) for failure in failures_list])
                LOG.warning(f'found custom script failures:\n{failures_str}')
            else:
                LOG.debug(f'no failures in custom script log file: {filename}')

            tobiko.truncate_logfile(filename)

            if failures_len >= failure_limit:
                tobiko.fail(f'{failures_len} failures found '
                            f'in file: {failures_list[-1]["filename"]}')


def start_script(
        command_line: str,
        ssh_client: ssh.SSHClientType = None):
    process = sh.process(
        command_line, ssh_client=ssh_client)
    process.execute()


def stop_script(
        pid: int,
        ssh_client: ssh.SSHClientType = None):
    # expect_exit_status=None -> will not fail if the kill command fails, maybe
    # the process had already died
    sh.execute(f'kill {pid}',
               ssh_client=ssh_client,
               sudo=True,
               expect_exit_status=None)
    # wait until http ping process disappears
    sh.wait_for_processes(timeout=120,
                          sleep_interval=5,
                          ssh_client=ssh_client,
                          pid=pid)
