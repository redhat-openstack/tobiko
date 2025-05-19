#!/usr/bin/env python3
# Copyright 2018 Red Hat
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

import os
import psutil
import resource
import signal
import sys
import subprocess


TOP_DIR = os.path.dirname(os.path.dirname(__file__))
if TOP_DIR not in sys.path:
    sys.path.insert(0, TOP_DIR)

from tools import common

LOG = common.get_logger(__name__)

# Root tests dir
TEST_PATH = common.normalize_path(
    os.environ.get('TOBIKO_TEST_PATH') or
    os.environ.get('OS_TEST_PATH') or
    os.path.join(TOP_DIR, 'tobiko', 'tests', 'unit'))

# Output dirs
REPORT_DIR = common.normalize_path(
    os.environ.get('TOBIKO_REPORT_DIR') or
    os.environ.get('TOX_REPORT_DIR') or
    os.getcwd())

REPORT_NAME = (
    os.environ.get('TOBIKO_REPORT_NAME') or
    os.environ.get('TOX_REPORT_NAME') or
    'tobiko_results')

REPORT_PREFIX = os.path.join(REPORT_DIR, REPORT_NAME)

REPORT_LOG = (
    os.environ.get('TOBIKO_REPORT_LOG') or
    os.environ.get('TOX_REPORT_LOG') or
    REPORT_PREFIX + '.log')

REPORT_HTML = (
    os.environ.get('TOBIKO_REPORT_HTML') or
    os.environ.get('TOX_REPORT_HTML') or
    REPORT_PREFIX + '.html')

REPORT_XML = (
    os.environ.get('TOBIKO_REPORT_XML') or
    os.environ.get('TOX_REPORT_XML') or
    REPORT_PREFIX + '.xml')

MAX_PROCESSES = (
    os.environ.get('TOBIKO_NUM_PROCESSES') or
    os.environ.get('TOX_NUM_PROCESSES') or
    'auto')

RUN_TESTS_TIMEOUT = float(
    os.environ.get('TOBIKO_RUN_TESTS_TIMEOUT') or
    os.environ.get('TOX_RUN_TESTS_TIMEOUT') or
    0.)

RERUNS = int(
    os.environ.get('TOBIKO_RERUNS') or
    os.environ.get('TOX_RERUNS') or
    0)

RERUNS_DELAY = int(
    os.environ.get('TOBIKO_RERUNS_DELAY') or
    os.environ.get('TOX_RERUNS_DELAY') or
    5)

COVER = (
    os.environ.get('TOBIKO_COVER') or
    os.environ.get('TOX_COVER') or
    'false') in ['1', 'yes', 'true']


def main():
    common.setup_logging()
    try:
        succeeded = run_tests()
        if succeeded:
            LOG.info('SUCCEEDED')
            sys.exit(0)
        else:
            LOG.info('FAILED')
            sys.exit(1)

    except Exception:
        LOG.exception('ERROR')
        sys.exit(2)


def run_tests():
    setup_ulimits()
    setup_timeout()
    cleanup_report_dir()
    log_environ()

    succeeded = True
    try:
        run_test_cases()
    except (subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            ProcessLookupError) as ex:
        LOG.error(f"Error while running test cases.\n{ex}")
        succeeded = False

    return succeeded


def setup_ulimits():
    try:
        hard_nofile_limit = resource.getrlimit(resource.RLIMIT_NOFILE)[1]
        resource.setrlimit(
            resource.RLIMIT_NOFILE,
            (hard_nofile_limit, hard_nofile_limit))
    except ValueError:
        pass


def setup_timeout():

    if RUN_TESTS_TIMEOUT > 0.:

        def handle_timeout(_signum, _frame):
            LOG.error(
                f"run_tests.py timeout out after {RUN_TESTS_TIMEOUT} "
                "seconds")
            terminate_childs()
            raise subprocess.TimeoutExpired("run_tests.py",
                                            RUN_TESTS_TIMEOUT)

        signal.setitimer(signal.ITIMER_REAL, RUN_TESTS_TIMEOUT)
        signal.signal(signal.SIGALRM, handle_timeout)
        LOG.debug(f'Run tests timeout set as {RUN_TESTS_TIMEOUT} seconds')


def terminate_childs():
    current_process = psutil.Process()
    children = current_process.children(recursive=False)
    for child in children:
        LOG.debug(f"Interrupt child process execution (pid={child.pid})")
        os.kill(child.pid, signal.SIGINT)
    for child in children:
        LOG.debug("Wait for top-child process termination "
                  f"(pid={child.pid})...")
        os.waitpid(child.pid, 0)


def cleanup_report_dir():
    for report_file in [REPORT_LOG, REPORT_HTML, REPORT_XML]:
        if not common.make_dir(os.path.dirname(report_file)):
            common.remove_file(report_file)


def log_environ():
    common.execute('env | sort >> "{log_file}"',
                   log_file=REPORT_LOG,
                   capture_stdout=False)


def run_test_cases():
    # numprocesses always set to "auto" to detect how many CPUs are available
    xdist_options = "--numprocesses 'auto' --dist loadscope"
    if MAX_PROCESSES != 'auto':
        # the max num of processes can be limitted: only makes sense if it's
        # lower than the actual number of processes
        xdist_options += f" --maxprocesses '{MAX_PROCESSES}'"
    rerun_options = ''
    if RERUNS:
        rerun_options = f"--reruns '{RERUNS}' --reruns-delay '{RERUNS_DELAY}'"
    cover_options = ''
    if COVER:
        cover_options = f"--cov=tobiko"

    # Pass environment variables to pytest command
    environ = dict(os.environ, TOBIKO_REPORT_NAME=REPORT_NAME)
    common.execute("pytest -v "
                   f"{xdist_options} "
                   f"{rerun_options} "
                   f"{cover_options} "
                   f"--log-file={REPORT_LOG} "
                   f"--junitxml={REPORT_XML} "
                   f"--html={REPORT_HTML} --self-contained-html "
                   f"{common.get_posargs()}",
                   environ=environ,
                   capture_stdout=False)


if __name__ == '__main__':
    main()
