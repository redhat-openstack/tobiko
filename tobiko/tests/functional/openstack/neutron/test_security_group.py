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
from tobiko.openstack.stacks._neutron import StatelessSecurityGroupFixture

DESCRIPTION = "Amazing Stateless Sec Group number {i}"
NUM_SEC_GROUPS = 10


@keystone.skip_unless_has_keystone_credentials()
class StatelessSecurityGroupTest(testtools.TestCase):
    """Tests Stateless Security Group creation"""

    stack_list = [tobiko.required_fixture(
                      StatelessSecurityGroupFixture,
                      fixture_id=str(i),
                      description=DESCRIPTION.format(i=i))
                  for i in range(NUM_SEC_GROUPS)]
    ssg_fixture_list: list = []

    @classmethod
    def tearDownClass(cls):
        for stack in cls.stack_list:
            tobiko.cleanup_fixture(stack.fixture)

    @classmethod
    def setUpClass(cls):
        for stack in cls.stack_list:
            cls.ssg_fixture_list.append(tobiko.use_fixture(stack.fixture))

    def test_stateless_sec_group_list_find(self):
        self.assertEqual(NUM_SEC_GROUPS, len(self.ssg_fixture_list))
        for i, ssg_fixture in enumerate(self.ssg_fixture_list):
            ssg_name = (f"{StatelessSecurityGroupFixture.__module__}."
                        f"{StatelessSecurityGroupFixture.__qualname__}-{i}")
            self.assertEqual(ssg_name, ssg_fixture.name)
            ssg = neutron.list_security_groups(name=ssg_name).unique
            self.assertCountEqual(ssg.keys(),
                                  ssg_fixture.security_group.keys())
            for k in ssg.keys():
                if k != 'security_group_rules':
                    self.assertEqual(ssg[k], ssg_fixture.security_group[k])
                else:
                    # the elements from the lists ssg['security_group_rules']
                    # and ssg_fixture.security_group['security_group_rules']
                    # are equal, but they could be ordered in a different way
                    self.assertCountEqual(ssg[k],
                                          ssg_fixture.security_group[k])

    def test_stateless_sec_group_list_parameters(self):
        for i, ssg_fixture in enumerate(self.ssg_fixture_list):
            self.assertEqual(DESCRIPTION.format(i=i),
                             ssg_fixture.security_group['description'])
