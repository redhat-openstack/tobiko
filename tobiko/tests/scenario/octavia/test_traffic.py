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

import testtools
from oslo_log import log

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import neutron
from tobiko.openstack import octavia
from tobiko.openstack import stacks


LOG = log.getLogger(__name__)


@keystone.skip_if_missing_service(name='octavia')
class OctaviaBasicTrafficScenarioTest(testtools.TestCase):
    """Octavia traffic scenario test.

    Create a load balancer with 2 members that run a server application,
    Create a client that is connected to the load balancer VIP port,
    Generate network traffic from the client to the load balanacer.
    """
    lb = None
    listener = None
    pool = None
    server_stack = tobiko.required_fixture(
        stacks.OctaviaServerStackFixture)
    other_server_stack = tobiko.required_fixture(
        stacks.OctaviaOtherServerStackFixture)

    def setUp(self):
        # pylint: disable=no-member
        super(OctaviaBasicTrafficScenarioTest, self).setUp()

        self.lb, self.listener, self.pool = octavia.deploy_ipv4_amphora_lb(
            servers_stacks=[self.server_stack, self.other_server_stack]
        )

    def test_round_robin_traffic(self):
        # For 5 minutes we ignore specific exceptions as we know
        # that Octavia resources are being provisioned
        octavia.verify_lb_traffic(
            pool_id=self.pool.id,
            ip_address=self.lb.vip_address,
            lb_algorithm=self.pool.lb_algorithm,
            protocol=self.listener.protocol,
            port=self.listener.protocol_port,
            timeout=300.)


@neutron.skip_unless_is_ovn()
@keystone.skip_if_missing_service(name='octavia')
class OctaviaOVNProviderTrafficTest(testtools.TestCase):
    """Octavia OVN provider traffic test.

    Create an OVN provider load balancer with 2 members that run a server
    application,
    Create a client that is connected to the load balancer VIP port via FIP,
    Generate TCP network traffic from the client to the load balancer FIP.
    """
    lb = None
    listener = None
    pool = None
    server_stack = tobiko.required_fixture(
        stacks.OctaviaServerStackFixture)
    other_server_stack = tobiko.required_fixture(
        stacks.OctaviaOtherServerStackFixture)

    def setUp(self):
        # pylint: disable=no-member
        super(OctaviaOVNProviderTrafficTest, self).setUp()

        self.lb, self.listener, self.pool = octavia.deploy_ipv4_ovn_lb(
            servers_stacks=[self.server_stack, self.other_server_stack]
        )

    def test_source_ip_port_traffic(self):
        """Send traffic to the load balancer FIP to test source ip port
        """
        # For 5 minutes we ignore specific exceptions as we know
        # that Octavia resources are being provisioned
        octavia.verify_lb_traffic(
            pool_id=self.pool.id,
            ip_address=self.lb.vip_address,
            lb_algorithm=self.pool.lb_algorithm,
            protocol=self.listener.protocol,
            port=self.listener.protocol_port,
            timeout=300.)
