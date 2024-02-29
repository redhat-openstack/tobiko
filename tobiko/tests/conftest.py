# Copyright (c) 2020 Red Hat
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
import os
import re
import subprocess

from oslo_log import log
import pytest
from pytest_metadata.plugin import metadata_key

import tobiko

LOG = log.getLogger(__name__)

REPORT_NAME = (
    os.environ.get('TOBIKO_REPORT_NAME') or
    os.environ.get('TOX_REPORT_NAME') or
    'tobiko_results')


@pytest.hookimpl
def pytest_configure(config):
    configure_metadata(config)
    configure_caplog(config)
    configure_timeout(config)
    configure_junitxml(config)


def configure_metadata(config):
    metadata = config.stash[metadata_key]
    # pylint: disable=protected-access
    from tobiko import version
    metadata["Tobiko Version"] = version.release
    git_commit = subprocess.check_output(
        ['git', 'log', '-n', '1'],
        universal_newlines=True).replace('\n', '<br>')
    metadata["Tobiko Git Commit"] = git_commit
    git_release = subprocess.check_output(
        ['git', 'describe', '--tags'],
        universal_newlines=True).replace('\n', '<br>')
    metadata["Tobiko Git Release"] = git_release


def configure_caplog(config):
    tobiko_config = tobiko.tobiko_config()

    if tobiko_config.logging.capture_log:
        if tobiko_config.debug:
            level = 'DEBUG'
        else:
            level = 'INFO'
    else:
        level = 'FATAL'
    for key in ['log_level',
                'log_file_level',
                'log_cli_level']:
        set_default_inicfg(config, key, level)

    line_format: str = tobiko_config.logging.line_format
    if line_format:
        # instance and color are not supported by pytest
        line_format = line_format.replace('%(instance)s', '')
        line_format = line_format.replace('%(color)s', '')
        if line_format:
            for key in ['log_format',
                        'log_file_format',
                        'log_cli_format']:
                set_default_inicfg(config, key, line_format)

    date_format = tobiko_config.logging.date_format
    if date_format:
        for key in ['log_date_format',
                    'log_file_date_format',
                    'log_cli_date_format']:
            set_default_inicfg(config, key, date_format)


def configure_junitxml(config):
    config.inicfg['junit_suite_name'] = REPORT_NAME


def set_default_inicfg(config, key, default):
    value = config.inicfg.setdefault(key, default)
    if value == default:
        LOG.debug(f"Set default inicfg: {key} = {value!r}")


class TestRunnerTimeoutManager(tobiko.SharedFixture):
    timeout: tobiko.Seconds = None
    deadline: tobiko.Seconds = None

    def setup_fixture(self):
        tobiko_config = tobiko.tobiko_config()
        self.timeout = tobiko_config.testcase.test_runner_timeout
        if self.timeout is None:
            LOG.info('Test runner timeout is disabled')
        else:
            LOG.info('Test runner timeout is enabled: '
                     f'timeout is {self.timeout} seconds')
            self.deadline = tobiko.time() + self.timeout

    @classmethod
    def check_test_runner_timeout(cls):
        self = tobiko.setup_fixture(cls)
        if self.deadline is not None:
            time_left = self.deadline - tobiko.time()
            if time_left <= 0.:
                pytest.skip(
                    f"Test runner execution timed out after {self.timeout} "
                    f"seconds",
                    allow_module_level=True)
            else:
                LOG.debug('Test runner timeout is enabled: '
                          f'{time_left} seconds left')


def check_test_runner_timeout():
    TestRunnerTimeoutManager.check_test_runner_timeout()


def configure_timeout(config):
    tobiko_config = tobiko.tobiko_config()
    default = tobiko_config.testcase.timeout
    if default is not None and default > 0.:
        set_default_inicfg(config, 'timeout', default)


def pytest_html_results_table_header(cells):
    cells.insert(2, '<th>Description</th>')
    cells.insert(
        1, '<th class="sortable time" data-column-type="time">Time</th>')
    cells.pop()


def pytest_html_results_table_row(report, cells):
    cells.insert(2, f'<td>{getattr(report, "description", "")}</td>')
    cells.insert(1, f'<td class="col-time">{datetime.utcnow()}</td>')
    cells.pop()


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    # pylint: disable=unused-argument
    outcome = yield
    report = outcome.get_result()
    report.description = getattr(item.function, '__doc__', '')


def pytest_html_report_title(report):
    report.title = f"Tobiko test results ({REPORT_NAME})"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_call(item):
    # pylint: disable=unused-argument
    check_test_runner_timeout()
    yield


@pytest.fixture(scope="session", autouse=True)
def cleanup_shelves():
    tobiko.initialize_shelves()


def pytest_addoption(parser):
    parser.addoption("--skipregex", action="store",
                     default="", help="skip tests matching the provided regex")


def pytest_collection_modifyitems(config, items):
    skipregex = config.getoption("--skipregex")
    if not skipregex:
        # --skipregex not given in cli, therefore move on
        return
    skip_listed = pytest.mark.skip(reason="matches --skipregex")
    for item in items:
        fully_qualified_test_name = '.'.join([item.obj.__module__,
                                              item.getmodpath()])
        if re.search(skipregex, fully_qualified_test_name):
            item.add_marker(skip_listed)
