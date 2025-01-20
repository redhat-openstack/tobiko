# Copyright (c) 2019 Red Hat
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

import os
from unittest import mock

from tobiko.tests import unit
from tobiko import config


CONF = config.CONF


class HttpProxyFixtureTest(unit.TobikoUnitTest):

    MY_HTTP_PROXY = 'http://my-server:8080'
    MY_NO_PROXY = '127.0.0.1'

    def setUp(self):
        super(HttpProxyFixtureTest, self).setUp()
        self.patch(os, 'environ', {})
        self.patch(CONF.tobiko, 'http',
                   http_proxy=None, https_proxy=None, no_proxy=None)

    def test_init(self):
        fixture = config.HttpProxyFixture()
        self.assertIsNone(fixture.http_proxy)
        self.assertEqual({}, os.environ)

    def test_setup(self):
        fixture = config.HttpProxyFixture()

        fixture.setUp()

        self.assertIsNone(fixture.http_proxy)
        self.assertEqual({}, os.environ)

    def test_setup_from_environ_http_proxy(self):
        os.environ['http_proxy'] = self.MY_HTTP_PROXY
        fixture = config.HttpProxyFixture()

        fixture.setUp()

        self.assertEqual({'http_proxy': self.MY_HTTP_PROXY}, os.environ)
        self.assertEqual(self.MY_HTTP_PROXY, fixture.http_proxy)

    def test_setup_from_environ_https_proxy(self):
        os.environ['https_proxy'] = self.MY_HTTP_PROXY
        fixture = config.HttpProxyFixture()

        fixture.setUp()

        self.assertEqual({'https_proxy': self.MY_HTTP_PROXY}, os.environ)
        self.assertEqual(self.MY_HTTP_PROXY, fixture.https_proxy)

    def test_setup_from_environ_no_proxy(self):
        os.environ['no_proxy'] = self.MY_NO_PROXY
        fixture = config.HttpProxyFixture()

        fixture.setUp()

        self.assertEqual({'no_proxy': self.MY_NO_PROXY}, os.environ)
        self.assertEqual(self.MY_NO_PROXY, fixture.no_proxy)

    def test_setup_from_tobiko_conf_http_proxy(self):
        self.patch(CONF.tobiko.http, 'http_proxy', self.MY_HTTP_PROXY)
        fixture = config.HttpProxyFixture()

        fixture.setUp()

        self.assertEqual(self.MY_HTTP_PROXY, fixture.http_proxy)
        self.assertEqual({'http_proxy': self.MY_HTTP_PROXY}, os.environ)

    def test_setup_from_tobiko_conf_https_proxy(self):
        self.patch(CONF.tobiko.http, 'https_proxy', self.MY_HTTP_PROXY)
        fixture = config.HttpProxyFixture()

        fixture.setUp()

        self.assertEqual(self.MY_HTTP_PROXY, fixture.https_proxy)
        self.assertEqual({'https_proxy': self.MY_HTTP_PROXY}, os.environ)

    def test_setup_from_tobiko_conf_no_proxy(self):
        self.patch(CONF.tobiko.http, 'http_proxy', self.MY_HTTP_PROXY)
        self.patch(CONF.tobiko.http, 'no_proxy', self.MY_NO_PROXY)
        fixture = config.HttpProxyFixture()

        fixture.setUp()

        self.assertEqual(self.MY_NO_PROXY, fixture.no_proxy)
        self.assertEqual(self.MY_HTTP_PROXY, fixture.http_proxy)
        self.assertEqual({'no_proxy': self.MY_NO_PROXY,
                          'http_proxy': self.MY_HTTP_PROXY}, os.environ)

    def test_get_bool_env(self):
        env_option = "TEST_OPTION"

        true_values = ['True', 'true', 'TRUE', 'TrUe', '1']
        false_values = ['False', 'false', 'FALSE', 'FaLsE', '0']
        invalid_values = [None, 'something else', '']

        for value in true_values:
            with mock.patch.dict('os.environ', {env_option: value}):
                self.assertIs(True, config.get_bool_env(env_option))

        for value in false_values:
            with mock.patch.dict('os.environ', {env_option: value}):
                self.assertIs(False, config.get_bool_env(env_option))

        for value in invalid_values:
            with mock.patch.dict('os.environ', {env_option: value}):
                self.assertIsNone(config.get_bool_env(env_option))
