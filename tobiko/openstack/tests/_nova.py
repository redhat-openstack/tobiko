# Copyright (c) 2020 Red Hat, Inc.
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

import os

import tobiko
from tobiko.shell import ping
from tobiko.shell import sh
from tobiko.openstack import nova
from tobiko.openstack.stacks import _cirros
from tobiko.openstack.stacks import _nova
from tobiko.openstack.stacks import _neutron


class TestServerCreationStack(_cirros.CirrosServerStackFixture):
    """Nova instance intended to be used for testing server creation"""


def test_server_creation(stack=TestServerCreationStack):
    """Test Nova server creation
    """
    return test_servers_creation(stack=stack,
                                 number_of_servers=0).first


class TestNetworkNoFipStackFixture(_neutron.NetworkNoFipStackFixture):
    """Neutron network where VMs will be created with no FIP"""


class TestServerNoFipCreationStack(_cirros.CirrosNoFipServerStackFixture):
    """Nova instance without FIP intended to be used for testing server
    creation"""
    network_stack = tobiko.required_fixture(TestNetworkNoFipStackFixture)


def test_server_creation_no_fip():
    """Test Nova server without FIP creation
    """
    return test_server_creation(stack=TestServerNoFipCreationStack)


class TestEvacuableServerCreationStack(_cirros.EvacuableServerStackFixture):
    """Nova instance intended to be used for testing server creation"""


def test_evacuable_server_creation():
    """Test evacuable Nova server creation
    """
    return test_server_creation(stack=TestEvacuableServerCreationStack)


def test_server_creation_and_shutoff(stack=TestServerCreationStack):
    result = test_server_creation(stack=stack)
    nova.shutoff_server(result.server_details)
    return result


def test_servers_creation(stack=TestServerCreationStack,
                          number_of_servers=2) -> \
        tobiko.Selection[_nova.ServerStackFixture]:

    initial_servers_ids = {server.id for server in nova.list_servers()}
    pid = os.getpid()
    fixture_obj = tobiko.get_fixture_class(stack)

    # Get list of server stack instances
    fixtures: tobiko.Selection[_nova.ServerStackFixture] = tobiko.select(
        tobiko.get_fixture(fixture_obj, fixture_id=f'{pid}-{i}')
        for i in range(number_of_servers or 1))

    test_case = tobiko.get_test_case()

    # Check fixtures types
    for fixture in fixtures:
        test_case.assertIsInstance(fixture, _nova.ServerStackFixture)

    # Delete all servers stacks
    for fixture in fixtures:
        tobiko.cleanup_fixture(fixture)

    # Create all servers stacks
    for fixture in fixtures:
        tobiko.use_fixture(fixture)

    # Check every server ID is unique and new
    server_ids = {fixture.server_id for fixture in fixtures}
    test_case.assertEqual(number_of_servers or 1, len(server_ids))
    test_case.assertFalse(server_ids & initial_servers_ids)

    for fixture in fixtures:
        # Test pinging to floating IP address (or fixed IP)
        if fixture.floating_ip_address is not None:
            pingable_ips = [fixture.floating_ip_address]
        else:
            pingable_ips = [fixed_ip['ip_address']
                            for fixed_ip in fixture.fixed_ips]
        ping.assert_reachable_hosts(pingable_ips)

        # Test SSH connectivity to floating IP address (or fixed IP)
        test_case.assertTrue(sh.get_hostname(ssh_client=fixture.ssh_client))

    return fixtures
