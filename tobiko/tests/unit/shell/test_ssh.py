# Copyright (c) 2019 Red Hat, Inc.
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

import io
import os
from unittest import mock

import paramiko

import tobiko
from tobiko import config
from tobiko.shell import ssh
from tobiko.tests import unit


CONF = config.CONF


class SSHClientFixtureTest(unit.TobikoUnitTest):

    fixture = tobiko.required_fixture(ssh.SSHClientFixture,
                                      setup=False)

    expected_host = None
    expected_proxy_client = None

    def setUp(self):
        super(SSHClientFixtureTest, self).setUp()
        tobiko.cleanup_fixture(self.fixture)
        self.ssh_client = mock.MagicMock(specs=paramiko.SSHClient)
        self.patch(paramiko, 'SSHClient', return_value=self.ssh_client)

    def test_init(self):
        fixture = self.fixture
        self.assertIs(self.expected_host, fixture.host)
        self.assertIs(self.expected_proxy_client, fixture.proxy_client)
        self.assertIsNone(fixture.host_config)
        self.assertIsNone(fixture.global_host_config)
        self.assertIsNone(fixture.connect_parameters)

    def test_setup(self):
        fixture = self.fixture
        if not self.expected_host:
            fixture.host = 'some-host'
        fixture.username = 'some-username'
        fixture.setUp()

        ssh_config = paramiko.SSHConfig()
        for ssh_config_file in CONF.tobiko.ssh.config_files:
            ssh_config_file = tobiko.tobiko_config_path(ssh_config_file)
            if os.path.exists(ssh_config_file):
                with io.open(ssh_config_file, 'rt',
                             encoding="utf-8") as f:
                    ssh_config.parse(f)
        expected_host_config = ssh_config.lookup(fixture.host)
        expected_host_config.pop('include', None)
        self.assertEqual(fixture.host, fixture.global_host_config.host)
        self.assertEqual(expected_host_config,
                         fixture.global_host_config.host_config)
