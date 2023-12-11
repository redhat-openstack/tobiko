# Copyright 2019 Red Hat
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

from tobiko import config
from tobiko.tests import unit


CONF = config.CONF
TRIPLEO_CONF = CONF.tobiko.tripleo
RHOSP_CONF = CONF.tobiko.rhosp


class TripleoConfigTest(unit.TobikoUnitTest):

    def test_ssh_key_filename(self):
        value = TRIPLEO_CONF.undercloud_ssh_key_filename
        if value is not None:
            self.assertIsInstance(value, str)


class UndercloudConfigTest(unit.TobikoUnitTest):

    def test_undercloud_ssh_hostname(self):
        value = TRIPLEO_CONF.undercloud_ssh_hostname
        if value is not None:
            self.assertIsInstance(value, str)

    def test_undercloud_ssh_port(self):
        value = TRIPLEO_CONF.undercloud_ssh_port
        if value is not None:
            self.assertIsInstance(value, int)
            self.assertGreater(value, 0)
            self.assertLess(value, 2 ** 16)

    def test_undercloud_ssh_username(self):
        self.assertIsInstance(TRIPLEO_CONF.undercloud_ssh_username, str)

    def test_undercloud_rcfile(self):
        for rcfile in TRIPLEO_CONF.undercloud_rcfile:
            self.assertIsInstance(rcfile, str)


class OvercloudConfigTest(unit.TobikoUnitTest):

    def test_overcloud_rcfile(self):
        for rcfile in TRIPLEO_CONF.overcloud_rcfile:
            self.assertIsInstance(rcfile, str)


class RhospConfigTest(unit.TobikoUnitTest):

    def test_ssh_port(self):
        value = RHOSP_CONF.ssh_port
        if value is not None:
            self.assertIsInstance(value, int)
            self.assertGreater(value, 0)
            self.assertLess(value, 2 ** 16)

    def test_ssh_username(self):
        value = RHOSP_CONF.ssh_username
        if value is not None:
            self.assertIsInstance(value, str)
