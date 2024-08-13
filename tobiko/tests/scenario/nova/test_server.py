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

import contextlib
import random

from oslo_log import log
import pytest
import testtools

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import nova
from tobiko.openstack import stacks
from tobiko.openstack.base import _fixture as base_fixture
from tobiko.shell import ping


LOG = log.getLogger(__name__)


@keystone.skip_unless_has_keystone_credentials()
class BaseServerTest(testtools.TestCase):
    __test__ = False  # forbid this test for being recollected
    stack: tobiko.RequiredFixture[stacks.ServerStackFixture]
    peer_stack = tobiko.required_fixture(stacks.CirrosServerStackFixture)

    def test_1_server_name(self):
        server = self.ensure_server()
        self.assertEqual(self.stack.server_name, server.name)

    @pytest.mark.server_shutoff
    def test_2_shutoff_server(self):
        # ensure boot is finished before turning VM down
        self.ensure_server(status='ACTIVE')
        self.assert_is_reachable()

        self.ensure_server(status='SHUTOFF')
        self.assert_is_unreachable()

    @pytest.mark.server_active
    def test_3_activate_server(self):
        # ensure server is down before activating it
        self.ensure_server(status='SHUTOFF')
        self.assert_is_unreachable()

        self.ensure_server(status='ACTIVE')
        self.stack.wait_for_guest_os_ready()
        self.assert_is_reachable()

    @pytest.mark.server_migrate
    @nova.skip_if_missing_hypervisors(count=2)
    def test_4_migrate_server(self):
        self._test_migrate_server(live=False)

    @pytest.mark.server_migrate
    @nova.skip_if_missing_hypervisors(count=2)
    def test_5_live_migrate_server(self):
        self._test_migrate_server(live=True)

    @pytest.mark.server_migrate
    @nova.skip_if_missing_hypervisors(count=3)
    def test_6_migrate_server_with_host(self):
        """Tests cold migration actually ends on target hypervisor
        """
        self._test_migrate_server_with_host(live=False)

    @pytest.mark.server_migrate
    @nova.skip_if_missing_hypervisors(count=3)
    def test_7_live_migrate_server_with_host(self):
        self._test_migrate_server_with_host(live=True)

    def _test_migrate_server(self,
                             live: bool,
                             block_migration: bool = None):
        """Tests cold migration actually changes hypervisor
        """
        server = self.ensure_server(status='ACTIVE')
        initial_hypervisor = nova.get_server_hypervisor(server)

        server = self.migrate_server(live=live,
                                     block_migration=block_migration)
        final_hypervisor = nova.get_server_hypervisor(server)
        self.assertNotEqual(initial_hypervisor, final_hypervisor)

    def _test_migrate_server_with_host(self,
                                       live: bool):
        """Tests cold migration actually ends on target hypervisor
        """
        server = self.ensure_server(status='ACTIVE')
        initial_hypervisor = nova.get_server_hypervisor(server)

        hypervisors = nova.list_hypervisors(
            status='enabled', state='up').select(
            lambda h: h.hypervisor_hostname != initial_hypervisor)
        if not hypervisors:
            tobiko.skip_test("Cannot find a valid hypervisor host to migrate "
                             "server to")
        target_hypervisor = random.choice(hypervisors).hypervisor_hostname

        server = self.migrate_server(host=target_hypervisor,
                                     live=live)
        final_hypervisor = nova.get_server_hypervisor(server)
        self.assertNotEqual(initial_hypervisor, final_hypervisor)
        self.assertEqual(target_hypervisor, final_hypervisor)

    def ensure_server(self, status: str = None):
        server = self.stack.server_details
        if status not in [None, server.status]:
            LOG.debug(f"Ensuring server '{server.id}' status changes:\
                      '{server.status}' -> '{status}'")
            assert isinstance(status, str)
            server = self.stack.ensure_server_status(status)
            self.assertEqual(status, server.status)
        return server

    def migrate_server(self,
                       live=False,
                       host: str = None,
                       block_migration: bool = None) \
            -> nova.NovaServer:
        self.assert_is_reachable()
        with self.handle_migration_errors():
            server = self.stack.migrate_server(live=live,
                                               host=host,
                                               block_migration=block_migration)
        self.assert_is_reachable()
        return server

    @contextlib.contextmanager
    def handle_migration_errors(self):
        try:
            yield
        except (nova.PreCheckMigrateServerError,
                nova.NoValidHostFoundMigrateServerError,
                nova.NotInLocalStorageMigrateServerError,
                nova.NotInSharedStorageMigrateServerError) as ex:
            self.skipTest(str(ex))

    def assert_is_reachable(self):
        self.stack.assert_is_reachable()
        ping.assert_reachable_hosts(self.stack.list_fixed_ips(),
                                    timeout=300.,
                                    ssh_client=self.peer_stack.ssh_client)
        if self.stack.has_vlan:
            self.stack.assert_vlan_is_reachable()

    def assert_is_unreachable(self):
        self.stack.assert_is_unreachable()
        ping.assert_unreachable_hosts(self.stack.list_fixed_ips(),
                                      timeout=300.,
                                      ssh_client=self.peer_stack.ssh_client)
        if self.stack.has_vlan:
            self.stack.assert_vlan_is_unreachable()


class CirrosServerStackFixture(stacks.CirrosServerStackFixture):

    def validate_created_stack(self):
        stack = super().validate_created_stack()
        server = nova.get_server(self.server_id)
        if server.status != 'SHUTOFF':
            if server.status != 'ACTIVE':
                try:
                    nova.activate_server(server)
                except nova.WaitForServerStatusTimeout as ex:
                    raise base_fixture.InvalidFixtureError(
                        name=self.stack_name) from ex
        return stack


@pytest.mark.minimal
class CirrosServerTest(BaseServerTest):
    __test__ = True
    stack = tobiko.required_fixture(CirrosServerStackFixture)


class UbuntuServerStackFixture(stacks.UbuntuServerStackFixture):
    pass


class UbuntuServerTest(BaseServerTest):
    __test__ = True
    stack = tobiko.required_fixture(UbuntuServerStackFixture)
