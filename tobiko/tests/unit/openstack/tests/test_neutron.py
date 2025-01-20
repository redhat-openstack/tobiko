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

from unittest import mock

from tobiko.openstack import tests
from tobiko.tests.unit import openstack


class NeutronAgentTest(openstack.OpenstackTest):

    def setUp(self):
        super(NeutronAgentTest, self).setUp()
        get_neutron_client = self.patch_get_neutron_client()
        self.neutron_client = get_neutron_client.return_value
        self.patch_time()

    def patch_list_agents(self, *args, **kwargs):
        self.neutron_client.list_agents = mock.MagicMock(*args, **kwargs)

    def test_neutron_agents_are_alive_when_healthy(self):
        self.patch_list_agents(return_value=[{'alive': True}])
        agents = tests.test_neutron_agents_are_alive()
        self.assertEqual([{'alive': True}], agents)

    def test_neutron_agents_are_alive_when_no_agents(self):
        self.patch_list_agents(return_value=[])
        ex = self.assertRaises(self.failureException,
                               tests.test_neutron_agents_are_alive)
        self.assertEqual("neutron returned 0 agents, which is not valid",
                         str(ex))

    def test_neutron_agents_are_alive_when_unhealthy(self):
        self.patch_list_agents(return_value=[{'alive': False}])
        ex = self.assertRaises(self.failureException,
                               tests.test_neutron_agents_are_alive)
        self.assertEqual("Unhealthy agent(s) found:\n"
                         "[\n"
                         "    {\n"
                         '        "alive": false\n'
                         "    }\n"
                         "]\n", str(ex))
