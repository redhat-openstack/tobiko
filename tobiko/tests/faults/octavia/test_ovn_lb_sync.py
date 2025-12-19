# Copyright (c) 2025 Red Hat
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
"""Test OVN Load Balancer Database Synchronization

This test verifies that the octavia-ovn-db-sync-util can properly restore
OVN load balancers after they are deleted from the OVN Northbound database.
"""
from __future__ import absolute_import

import testtools
from oslo_log import log

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import neutron
from tobiko.openstack import octavia
from tobiko.openstack import stacks
from tobiko.openstack import topology
from tobiko import podified
from tobiko import tripleo
from tobiko.shell import sh
from tobiko.tripleo import containers


LOG = log.getLogger(__name__)


@neutron.skip_unless_is_ovn()
@keystone.skip_if_missing_service(name='octavia')
@tripleo.skip_if_overcloud
@podified.skip_if_podified  # TODO: Remove this skip when ready for Podified
class OVNLoadBalancerSyncTest(testtools.TestCase):
    """OVN Load Balancer Database Synchronization Test

    This test creates an OVN provider load balancer, deletes it from the
    OVN Northbound database, and then runs octavia-ovn-db-sync-util to
    restore it. Finally, it verifies that the load balancer functionality
    is working correctly.

    NOTE: This test is currently designed for DevStack only.
    It is skipped on TripleO and Podified/Kubernetes deployments.

    TODO: Enable for Podified environments once fully tested.
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
        super(OVNLoadBalancerSyncTest, self).setUp()

        LOG.info("Setting up OVN Load Balancer test")

        # Deploy a complete OVN load balancer
        self.lb, self.listener, self.pool = octavia.deploy_ipv4_ovn_lb(
            servers_stacks=[self.server_stack, self.other_server_stack]
        )

        # List pool members
        members = list(octavia.list_members(pool_id=self.pool.id))
        LOG.info(f"  Members: {len(members)} members in pool")
        if len(members) == 0:
            LOG.error("ERROR: No members were created in the pool!")
            LOG.error("This may indicate a problem with server stack "
                      "deployment")
        for idx, member in enumerate(members):
            LOG.info(f"    Member {idx+1}: {member.name} (ID: {member.id}, "
                     f"Address: {member.address})")

        # Wait for the load balancer to be fully operational
        octavia.wait_for_status(
            object_id=self.lb.id,
            status_key=octavia.OPERATING_STATUS,
            status=octavia.ONLINE,
            get_client=octavia.get_load_balancer
        )
        LOG.info(f"Load balancer {self.lb.name} is ONLINE")

        # Verify initial traffic works
        LOG.info("Verifying initial load balancer traffic")
        octavia.verify_lb_traffic(
            pool_id=self.pool.id,
            ip_address=self.lb.vip_address,
            lb_algorithm=self.pool.lb_algorithm,
            protocol=self.listener.protocol,
            port=self.listener.protocol_port,
            timeout=300.)
        LOG.info("Load balancer traffic verified successfully")

    def _get_ovn_controller_node(self):
        """Get a controller node for executing OVN commands"""
        controllers = topology.list_openstack_nodes(group='controller')
        if not controllers:
            self.skipTest("No controller nodes found")
        return controllers[0]

    def _get_ovn_nb_connection(self):
        """Get OVN Northbound database connection string

        Tries multiple methods to obtain the connection:
        1. From octavia.conf [ovn] section using topology infrastructure
        2. From ovs-vsctl as fallback (for environments without config file)
        """
        controller = self._get_ovn_controller_node()

        # Method 1: Try to get from octavia.conf using topology
        try:
            nb_connection = topology.get_config_setting(
                file_name='octavia.conf',
                ssh_client=controller.ssh_client,
                param='ovn_nb_connection',
                section='ovn')
            if nb_connection:
                LOG.info("Found OVN NB connection from octavia.conf")
                return nb_connection
        except Exception as e:
            LOG.warning(f"Could not read from octavia.conf: {e}")

        # Method 2: Try ovs-vsctl as fallback
        try:
            LOG.info("Trying ovs-vsctl to get OVN NB connection")
            cmd = ("ovs-vsctl get open . external_ids:ovn-remote | "
                   "sed 's/\"//g' | "
                   "sed 's/6642/6641/g'")
            output = sh.execute(cmd, ssh_client=controller.ssh_client,
                                sudo=True)
            connection = output.stdout.strip()
            if connection:
                LOG.info("Found connection using ovs-vsctl")
                return connection
        except sh.ShellCommandFailed:
            pass

        self.fail("Could not determine OVN NB connection string")

    def _wrap_ovn_nbctl_command(self, ovn_nbctl_cmd):
        current_topology = topology.get_openstack_topology()
        if current_topology.has_containers:
            runtime_name = containers.get_container_runtime_name()
            cmd = f'{runtime_name} exec ovn_controller {ovn_nbctl_cmd}'
            LOG.debug("Using containerized ovn-nbctl command")
        else:
            # Direct command for non-containerized environments (DevStack)
            cmd = ovn_nbctl_cmd
            LOG.debug("Using direct ovn-nbctl command")
        return cmd

    def _get_ovn_lb_uuid(self):
        """Get the OVN Load Balancer UUID from OVN NB database"""
        controller = self._get_ovn_controller_node()
        nb_connection = self._get_ovn_nb_connection()

        # Build the ovn-nbctl command
        ovn_nbctl_cmd = (f'ovn-nbctl --db={nb_connection} --bare '
                         f'--columns=_uuid find load_balancer '
                         f'name={self.lb.id}')

        cmd = self._wrap_ovn_nbctl_command(ovn_nbctl_cmd)
        LOG.info(f"Getting OVN LB UUID with command: {cmd}")
        output = sh.execute(cmd, ssh_client=controller.ssh_client, sudo=True)
        ovn_lb_uuid = output.stdout.strip()

        if not ovn_lb_uuid:
            self.fail(f"OVN Load Balancer UUID not found for {self.lb.id}")

        LOG.info(f"Found OVN LB UUID: {ovn_lb_uuid}")
        return ovn_lb_uuid

    def _delete_ovn_lb_from_db(self, ovn_lb_uuid):
        """Delete the OVN Load Balancer from the OVN NB database"""
        controller = self._get_ovn_controller_node()
        nb_connection = self._get_ovn_nb_connection()

        # Build the ovn-nbctl command
        ovn_nbctl_cmd = f'ovn-nbctl --db={nb_connection} lb-del {ovn_lb_uuid}'

        cmd = self._wrap_ovn_nbctl_command(ovn_nbctl_cmd)
        LOG.warning(f"Deleting OVN LB from database with command: {cmd}")
        sh.execute(cmd, ssh_client=controller.ssh_client, sudo=True)
        LOG.info(f"Successfully deleted OVN LB {ovn_lb_uuid} from OVN NB DB")

    def _run_ovn_octavia_sync_tool(self):
        """Execute octavia-ovn-db-sync-util to restore the load balancer

        This method delegates to the topology class which knows how to run
        the sync tool in its environment (DevStack, Podified, TripleO, etc.)
        """
        LOG.info("Step 5: Running octavia-ovn-db-sync-tool")
        controller = self._get_ovn_controller_node()

        # Get the current topology and call its sync method
        current_topology = topology.get_openstack_topology()
        current_topology.run_octavia_ovn_db_sync(
            ssh_client=controller.ssh_client)

    def test_ovn_lb_sync_after_db_deletion(self):
        """Test OVN LB restoration after deletion from OVN NB database

        This test:
        1. Creates an OVN load balancer (done in setUp)
        2. Verifies initial functionality
        3. Gets the OVN LB UUID from OVN NB database
        4. Deletes the OVN LB from OVN NB database
        5. Runs octavia-ovn-db-sync-util to restore it
        6. Verifies the load balancer is restored and functional
        """

        # Step 1: Get OVN LB UUID
        LOG.info("Step 1: Getting OVN Load Balancer UUID")
        ovn_lb_uuid = self._get_ovn_lb_uuid()

        # Step 2: Delete OVN LB from OVN NB database
        LOG.info("Step 2: Deleting OVN LB from OVN Northbound database")
        self._delete_ovn_lb_from_db(ovn_lb_uuid)

        # Step 3: Verify LB is missing from OVN but still exists in Octavia
        LOG.info("Step 3: Verifying LB is deleted from OVN but exists in "
                 "Octavia")
        lb_in_octavia = octavia.get_load_balancer(self.lb.id)
        self.assertIsNotNone(lb_in_octavia,
                             "Load balancer should still exist in Octavia")
        LOG.info(f"Confirmed: LB {self.lb.id} still exists in Octavia DB")

        # Step 4: Run sync tool to restore the OVN LB
        LOG.info("Step 4: Running octavia-ovn-db-sync-util")
        self._run_ovn_octavia_sync_tool()

        # Step 5: Wait for LB to be restored
        LOG.info("Step 5: Waiting for load balancer to be restored")
        octavia.wait_for_status(
            object_id=self.lb.id,
            status_key=octavia.OPERATING_STATUS,
            status=octavia.ONLINE,
            get_client=octavia.get_load_balancer,
            timeout=180
        )
        LOG.info(f"Load balancer {self.lb.name} is ONLINE after sync")

        # Step 6: Verify OVN LB is back in OVN NB database
        LOG.info("Step 6: Verifying OVN LB is restored in OVN NB database")
        restored_ovn_lb_uuid = self._get_ovn_lb_uuid()
        self.assertIsNotNone(restored_ovn_lb_uuid,
                             "OVN LB should be restored in OVN NB database")
        LOG.info(f"Confirmed: OVN LB restored with UUID: "
                 f"{restored_ovn_lb_uuid}")

        # Step 7: Verify traffic works again
        LOG.info("Step 7: Verifying load balancer traffic after restoration")
        octavia.verify_lb_traffic(
            pool_id=self.pool.id,
            ip_address=self.lb.vip_address,
            lb_algorithm=self.pool.lb_algorithm,
            protocol=self.listener.protocol,
            port=self.listener.protocol_port,
            timeout=300.)
        LOG.info("SUCCESS: Load balancer fully restored and functional")
