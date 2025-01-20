# Copyright 2021 Red Hat
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

from unittest import mock

from oslo_log import log

import tobiko
from tobiko.tests import unit
from tobiko.tests import conftest


LOG = log.getLogger(__name__)


class CaplogTest(unit.TobikoUnitTest):

    def test_configure_caplog(self):
        pytest_config = mock.MagicMock(inicfg={
            'log_level': '<existing>',
            'log_format': '<existing>',
            'log_date_format': '<existing>'})
        conftest.configure_caplog(pytest_config)
        self.assertEqual('<existing>', pytest_config.inicfg['log_level'])
        self.assertEqual('<existing>', pytest_config.inicfg['log_format'])
        self.assertEqual('<existing>', pytest_config.inicfg['log_date_format'])

    def test_configure_caplog_debug(self):
        self.patch_caplog_config(capture_log=True, debug=True)
        pytest_config = mock.MagicMock(inicfg={})
        conftest.configure_caplog(pytest_config)
        self.assertEqual('DEBUG', pytest_config.inicfg['log_level'])

    def test_configure_caplog_info(self):
        self.patch_caplog_config(capture_log=True, debug=False)
        pytest_config = mock.MagicMock(inicfg={})
        conftest.configure_caplog(pytest_config)
        self.assertEqual('INFO', pytest_config.inicfg['log_level'])

    def test_configure_caplog_fatal(self):
        self.patch_caplog_config(capture_log=False)
        pytest_config = mock.MagicMock(inicfg={})
        conftest.configure_caplog(pytest_config)
        self.assertEqual('FATAL', pytest_config.inicfg['log_level'])

    def test_configure_caplog_log_format(self):
        self.patch_caplog_config(line_format='<some-format>')
        pytest_config = mock.MagicMock(inicfg={})
        conftest.configure_caplog(pytest_config)
        self.assertEqual('<some-format>', pytest_config.inicfg['log_format'])

    def test_configure_caplog_date_format(self):
        self.patch_caplog_config(date_format='<some-format>')
        pytest_config = mock.MagicMock(inicfg={})
        conftest.configure_caplog(pytest_config)
        self.assertEqual('<some-format>',
                         pytest_config.inicfg['log_date_format'])

    def patch_caplog_config(self,
                            capture_log: bool = None,
                            debug: bool = None,
                            line_format: str = None,
                            date_format: str = None):
        tobiko_config = self.patch(tobiko, 'tobiko_config').return_value
        if capture_log is not None:
            tobiko_config.logging.capture_log = capture_log
        if debug is not None:
            tobiko_config.debug = debug
        if line_format is not None:
            tobiko_config.logging.line_format = line_format
        if date_format is not None:
            tobiko_config.logging.date_format = date_format


class TimeoutTest(unit.TobikoUnitTest):

    def test_configure_timeout_existing(self):
        pytest_config = mock.MagicMock(inicfg={'timeout': '<existing>'})
        conftest.configure_timeout(pytest_config)
        self.assertEqual('<existing>', pytest_config.inicfg['timeout'])

    def test_configure_timeout_none(self):
        self.patch_timeout_config(timeout=None)
        pytest_config = mock.MagicMock(inicfg={})
        conftest.configure_timeout(pytest_config)
        self.assertNotIn('timeout', pytest_config.inicfg)

    def test_configure_timeout_zero(self):
        self.patch_timeout_config(timeout=0.)
        pytest_config = mock.MagicMock(inicfg={})
        conftest.configure_timeout(pytest_config)
        self.assertNotIn('timeout', pytest_config.inicfg)

    def test_configure_timeout_negative(self):
        self.patch_timeout_config(timeout=-1.)
        pytest_config = mock.MagicMock(inicfg={})
        conftest.configure_timeout(pytest_config)
        self.assertNotIn('timeout', pytest_config.inicfg)

    def test_configure_timeout_positive(self):
        self.patch_timeout_config(timeout=10.)
        pytest_config = mock.MagicMock(inicfg={})
        conftest.configure_timeout(pytest_config)
        self.assertEqual(10., pytest_config.inicfg['timeout'])

    def patch_timeout_config(self, timeout):
        tobiko_config = self.patch(tobiko, 'tobiko_config').return_value
        tobiko_config.testcase.timeout = timeout
