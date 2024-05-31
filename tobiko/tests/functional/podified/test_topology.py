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

import tobiko
from tobiko.openstack import topology as osp_topology
from tobiko.shell import ping
from tobiko.shell import sh
from tobiko.tests.functional.openstack import test_topology
from tobiko import podified


@podified.skip_if_not_podified
class PodifiedTopologyTest(test_topology.OpenStackTopologyTest):

    expected_group: osp_topology.OpenstackGroupNamesType = 'compute'

    @property
    def topology(self) -> podified.PodifiedTopology:
        return tobiko.setup_fixture(podified.PodifiedTopology)

    def test_ping_node(self):
        # NOTE(slaweq): in podified topology we expect connectivity only to the
        # edpm nodes, not to the OCP workers
        for node in self.topology.get_group("compute"):
            ping.ping(node.public_ip, count=1, timeout=5.).assert_replied()

    def test_ssh_client(self):
        # NOTE(slaweq): in podified topology we expect connectivity only to the
        # edpm nodes, not to the OCP workers
        for node in self.topology.get_group("compute"):
            self.assertIsNotNone(node.ssh_client)
            hostname = sh.ssh_hostname(
                ssh_client=node.ssh_client).split('.')[0]
            self.assertEqual(node.name, hostname)
