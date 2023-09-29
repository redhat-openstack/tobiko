# Copyright (c) 2023 Red Hat, Inc.
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

import testtools

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import neutron
from tobiko.openstack.stacks._neutron import SubnetPoolFixture

PREFIX = "10.211.{i}.0/24"
DEFAULT_PREFIXLEN = 29


@keystone.skip_unless_has_keystone_credentials()
class SubnetPoolTest(testtools.TestCase):
    """Tests subnet pool creation"""

    stack = tobiko.required_fixture(SubnetPoolFixture,
                                    fixture_id="thistest",
                                    prefixes=[PREFIX.format(i=0)],
                                    default_prefixlen=DEFAULT_PREFIXLEN)

    @classmethod
    def tearDownClass(cls):
        # NOTE: the skip at class level does not affect tearDownClass, so
        # the following workaround is needed to avoid errors
        if keystone.has_keystone_credentials():
            tobiko.cleanup_fixture(cls.stack.fixture)

    def test_subnet_pool_find(self):
        snp = neutron.list_subnet_pools(name=self.stack.name).unique
        self.assertEqual(snp, self.stack.subnet_pool)

    def test_subnet_pool_parameters(self):
        self.assertEqual([PREFIX.format(i=0)],
                         self.stack.subnet_pool['prefixes'])
        self.assertEqual(str(DEFAULT_PREFIXLEN),
                         self.stack.subnet_pool['default_prefixlen'])


NUM_SUBNET_POOLS = 10


@keystone.skip_unless_has_keystone_credentials()
class SubnetPoolListTest(testtools.TestCase):
    """Tests creation of a list of subnet pools"""

    stack_list = [tobiko.required_fixture(SubnetPoolFixture,
                                          fixture_id=str(i),
                                          prefixes=[PREFIX.format(i=i)],
                                          default_prefixlen=DEFAULT_PREFIXLEN)
                  for i in range(NUM_SUBNET_POOLS)]
    snp_fixture_list: list = []

    @classmethod
    def tearDownClass(cls):
        for stack in cls.stack_list:
            tobiko.cleanup_fixture(stack.fixture)

    @classmethod
    def setUpClass(cls):
        for stack in cls.stack_list:
            cls.snp_fixture_list.append(tobiko.use_fixture(stack.fixture))

    def test_subnet_pool_list_find(self):
        self.assertEqual(NUM_SUBNET_POOLS, len(self.snp_fixture_list))
        for i, snp_fixture in enumerate(self.snp_fixture_list):
            snp_name = (f"{SubnetPoolFixture.__module__}."
                        f"{SubnetPoolFixture.__qualname__}-{i}")
            self.assertEqual(snp_name, snp_fixture.name)
            snp = neutron.list_subnet_pools(name=snp_name).unique
            self.assertEqual(snp, snp_fixture.subnet_pool)

    def test_subnet_pool_list_parameters(self):
        for i, snp_fixture in enumerate(self.snp_fixture_list):
            self.assertEqual([PREFIX.format(i=i)],
                             snp_fixture.subnet_pool['prefixes'])
            self.assertEqual(str(DEFAULT_PREFIXLEN),
                             snp_fixture.subnet_pool['default_prefixlen'])
