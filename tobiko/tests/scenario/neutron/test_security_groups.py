# Copyright (c) 2023 Red Hat
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

import json
import re
import typing

from oslo_log import log
import pytest
import testtools

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import neutron
from tobiko.openstack import octavia
from tobiko.openstack import stacks
from tobiko.openstack import topology
from tobiko import podified
from tobiko.shell import sh
from tobiko import tripleo

LOG = log.getLogger(__name__)


class BaseSecurityGroupTest(testtools.TestCase):

    _ovn_nb_db = None
    _host_ssh_client = None
    _container_runtime_name = None
    _container_name = None

    def setUp(self):
        super(BaseSecurityGroupTest, self).setUp()
        self.ovn_controller_agents = neutron.list_networking_agents(
            binary=neutron.OVN_CONTROLLER)
        if len(self.ovn_controller_agents) < 1:
            self.skip(f"No running {neutron.OVN_CONTROLLER} agents found. "
                      f"Stateless Security Group tests requires ML2/OVN "
                      f"deployment.")

    @property
    def ovn_nb_db(self):

        def get_podified_ovn_nb_db():
            nb_db = podified.get_ovndbcluter(
                'ovndbcluster-nb')['status']['dbAddress']
            ssl_params = ''
            if 'ssl' in nb_db:
                # SSL options obtained from the container under test
                command = ""
                if topology.get_openstack_topology().has_containers:
                    command += (f"{self.container_runtime_name} exec "
                                f"{self.container_name} ")
                command += "ps -o command -C ovn-controller --no-headers -ww"
                command_result = sh.execute(command,
                                            ssh_client=self.host_ssh_client,
                                            sudo=True).stdout.strip()
                for param in ('p', 'c', 'C'):
                    # the matched strings start with a space
                    ssl_params += re.search(r' -{} [^\s]+'.format(param),
                                            command_result).group()
            return nb_db + ssl_params

        def get_ovn_nb_db():
            command_result = sh.execute(
                "ovs-vsctl get open . external_ids:ovn-remote | "
                "sed -e 's/\"//g' | sed 's/6642/6641/g'",
                ssh_client=self.host_ssh_client,
                sudo=True)
            if 'ovsdbserver-sb' in command_result.stdout:
                nb_db = command_result.stdout.replace('ovsdbserver-sb',
                                                      'ovsdbserver-nb')
            else:
                nb_db = command_result.stdout
            ssl_params = ''
            if 'ssl' in command_result.stdout:
                ssl_params = ' -p {} -c {} -C {} '.format(
                    '/etc/pki/tls/private/ovn_controller.key',
                    '/etc/pki/tls/certs/ovn_controller.crt',
                    '/etc/ipa/ca.crt')
            return nb_db + ssl_params

        if not self._ovn_nb_db:
            if podified.has_podified_cp():
                self._ovn_nb_db = get_podified_ovn_nb_db()
            else:
                self._ovn_nb_db = get_ovn_nb_db()
        return self._ovn_nb_db

    @property
    def host_ssh_client(self):
        if not self._host_ssh_client:
            for ovn_controller_agent in self.ovn_controller_agents:
                candidate_ssh_client = topology.get_openstack_node(
                        hostname=ovn_controller_agent['host']).ssh_client
                # some of the ovn-controller hosts may be not ssh'able
                # (specifically, this happens with Podified Controlplane hosts)
                if candidate_ssh_client is not None:
                    self._host_ssh_client = candidate_ssh_client
                    break
        return self._host_ssh_client

    @property
    def container_runtime_name(self):
        if not self._container_runtime_name:
            if tripleo.has_overcloud():
                self._container_runtime_name = (
                    tripleo.get_container_runtime_name())
            elif podified.has_podified_cp():
                self._container_runtime_name = (
                    podified.get_container_runtime_name())
            else:
                self._container_runtime_name = 'docker'
        return self._container_runtime_name

    @property
    def container_name(self):
        if self._container_name is None:
            os_topology = topology.get_openstack_topology()
            if os_topology.has_containers:
                self._container_name = topology.get_agent_container_name(
                    neutron.OVN_CONTROLLER
                )
            else:
                self._container_name = ""
        return self._container_name

    def _check_sg_rule_in_ovn_nb_db(self, rule_id: str, expected_action: str):
        os_topology = topology.get_openstack_topology()
        command = ""
        if os_topology.has_containers:
            command += (
                f"{self.container_runtime_name} exec {self.container_name} ")
        command += (
            f"ovn-nbctl --format json --no-leader-only --db={self.ovn_nb_db} "
            f"find ACL external_ids:\"neutron\\:security_group_rule_id\"="
            f"\"{rule_id}\""
        )
        command_result = sh.execute(
            command, ssh_client=self.host_ssh_client, sudo=True)
        acl_rule = json.loads(command_result.stdout)
        self._assert_acl_action(acl_rule, expected_action)

    def _assert_acl_action(self, acl: dict, expected_action: str):
        action_column = acl['headings'].index('action')
        self.assertEqual(
            expected_action,
            acl['data'][0][action_column])

    def _check_sg_rules_in_ovn_nb_db(self, sg: dict, expected_action: str):
        sg_rules_ids = [
            rule['id'] for rule in sg['security_group_rules']]
        for sg_rule_id in sg_rules_ids:
            self._check_sg_rule_in_ovn_nb_db(sg_rule_id, expected_action)


@pytest.mark.skip_during_ovn_migration
@neutron.skip_if_missing_networking_extensions('stateful-security-group')
class StatelessSecurityGroupTest(BaseSecurityGroupTest):

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(
        stacks.CirrosServerWithDefaultSecurityGroupStackFixture)

    def test_default_security_group_is_stateful(self):
        """Test that default security group is always stateful.

        This test checks if default SG created for the project is stateful
        and if OVN's ACLs corresponding to the SG's rules have correct
        action which is "allow-related".

        Steps:
        1. Get default SG for the project (it's always created automatically),
        2. Check if ACLs corresponding to the rules from that SG have
           "action-related" action,
        3. Add new SG rule in the default SG,
        4. Check action of the ACL corresponding to the newly created SG rule.
        """

        default_sg = neutron.get_default_security_group(
            project_id=self.stack.project)
        self.assertTrue(default_sg['stateful'])
        self._check_sg_rules_in_ovn_nb_db(default_sg,
                                          neutron.STATEFUL_OVN_ACTION)
        new_rule = neutron.create_security_group_rule(
            default_sg['id'],
            port_range_min=1111,
            port_range_max=1111,
            ethertype="IPv4",
            protocol="tcp",
            description="test_default_security_group_is_stateful rule",
            direction="ingress"
        )
        self._check_sg_rule_in_ovn_nb_db(new_rule['id'],
                                         neutron.STATEFUL_OVN_ACTION)

    def test_security_group_stateful_to_stateless_switch(self):
        """Test that security group can be switched from stateful to stateless.

        This test initially checks if newly created SG is stateful by default
        and if OVN's ACLs corresponding to the SG's rules have correct
        action which is "allow-related".
        Later it also checks if SG can be updated to be stateless and if OVN's
        ACLs corresponding to the SG's rules are properly updated too.

        Steps:
        1. Create SG for the project,
        2. Check if ACLs corresponding to the rules from that SG have
           "action-related" action,
        3. Add new SG rule in the SG,
        4. Check action of the ACL corresponding to the newly created SG rule,
        5. Update SG to be stateless,
        6. Check if ACLs corresponding to the rules from that SG have
           "action-stateless" action,
        7. Add new SG rule in the SG,
        8. Check action of the ACL corresponding to the newly created SG rule,
        9. Update SG to be stateful again,
        10. Add new SG rule in the SG,
        11. Check action of the ACL corresponding to the newly created SG rule,
        """
        sg = neutron.create_security_group(
            name="test_new_security_group_is_statefull_SG",
        )
        self.assertTrue(sg['stateful'])
        self._check_sg_rules_in_ovn_nb_db(sg, neutron.STATEFUL_OVN_ACTION)
        new_rule = neutron.create_security_group_rule(
            sg['id'],
            port_range_min=1111,
            port_range_max=1111,
            ethertype="IPv4",
            protocol="tcp",
            description="stateful SG rule 1",
            direction="ingress"
        )
        self._check_sg_rule_in_ovn_nb_db(new_rule['id'],
                                         neutron.STATEFUL_OVN_ACTION)

        # Update to stateless
        neutron.update_security_group(sg['id'], stateful=False)
        sg = neutron.get_security_group(sg['id'])
        self.assertFalse(sg['stateful'])
        self._check_sg_rules_in_ovn_nb_db(sg, neutron.STATELESS_OVN_ACTION)
        new_rule = neutron.create_security_group_rule(
            sg['id'],
            port_range_min=2222,
            port_range_max=2222,
            ethertype="IPv4",
            protocol="tcp",
            description="stateless SG rule",
            direction="ingress"
        )
        self._check_sg_rule_in_ovn_nb_db(new_rule['id'],
                                         neutron.STATELESS_OVN_ACTION)

        # And get back to stateful
        neutron.update_security_group(sg['id'], stateful=True)
        sg = neutron.get_security_group(sg['id'])
        self.assertTrue(sg['stateful'])
        self._check_sg_rules_in_ovn_nb_db(sg, neutron.STATEFUL_OVN_ACTION)
        new_rule = neutron.create_security_group_rule(
            sg['id'],
            port_range_min=3333,
            port_range_max=3333,
            ethertype="IPv4",
            protocol="tcp",
            description="stateful SG rule 2",
            direction="ingress"
        )
        self._check_sg_rule_in_ovn_nb_db(new_rule['id'],
                                         neutron.STATEFUL_OVN_ACTION)

    def test_create_stateless_security_group(self):
        """Test that stateless security group can be created.

        This test checks if creation of the stateless SG is working fine
        and if OVN's ACLs corresponding to the SG's rules have correct
        action which is "allow-stateless".

        Steps:
        1. Create stateless security group,
        2. Check if ACLs corresponding to the rules from that SG have
           "action-stateless" action,
        3. Add new SG rule in the SG,
        4. Check action of the ACL corresponding to the newly created SG rule.
        """
        sg = neutron.create_security_group(
            name="test_stateless_SG",
            stateful=False
        )
        self.assertFalse(sg['stateful'])
        self._check_sg_rules_in_ovn_nb_db(sg, neutron.STATELESS_OVN_ACTION)
        new_rule = neutron.create_security_group_rule(
            sg['id'],
            port_range_min=1111,
            port_range_max=1111,
            ethertype="IPv4",
            protocol="tcp",
            description="test_new_security_group_is_statefull_SG rule",
            direction="ingress"
        )
        self._check_sg_rule_in_ovn_nb_db(new_rule['id'],
                                         neutron.STATELESS_OVN_ACTION)


@neutron.skip_if_missing_networking_extensions('port-security',
                                               'stateful-security-group')
class CirrosServerWithStatelessSecurityGroupFixture(
        stacks.CirrosServerStackFixture):
    """Heat stack for testing a floating IP instance with port security"""

    #: Resources stack with security group to allow ping Nova servers
    security_groups_stack: tobiko.RequiredFixture = \
        tobiko.required_fixture(stacks.StatelessSecurityGroupFixture)

    @property
    def security_groups(self) -> typing.List[str]:
        """List with Stateless security group"""
        return [self.security_groups_stack.security_group_id]


@pytest.mark.skip_during_ovn_migration
@neutron.skip_if_missing_networking_extensions('stateful-security-group')
class StatelessSecurityGroupInstanceTest(BaseSecurityGroupTest):

    #: Resources stack with Nova server to send messages to
    vm = tobiko.required_fixture(
        CirrosServerWithStatelessSecurityGroupFixture)

    lb_member_server = tobiko.required_fixture(
        stacks.OctaviaServerStackFixture)

    def test_no_conntrack_entries_related_to_stateless_sg(self):
        """ Test that there is no conntrack entry related to stateless SG.

        This test ensures that there is no conntrack entry for connection
        that passes stateless security group.

        Steps:
        1. Create server with stateless SG,
        2. Allow SSH to that instance
        3. Make SSH connection to the instance,
        4. Ensure on compute node that there are no conntrack entries
           related to that connection there,
        """
        host_ssh_client = topology.get_openstack_node(
            hostname=self.vm.hypervisor_hostname).ssh_client
        vm_ip_address = self.vm.find_fixed_ip(ip_version=4)

        # Now lets make ssh connection to the vm and then check in conntrack if
        # entry is there or not (it shouldn't be)
        sh.execute('hostname', ssh_client=self.vm.ssh_client)
        conntrack_list_result = sh.execute(
            "conntrack -L --proto tcp --dport 22 --dst %s" % vm_ip_address,
            ssh_client=host_ssh_client, sudo=True)
        # And ensure that there is no entry found in conntrack
        self.assertEqual("", conntrack_list_result.stdout)
        self.assertTrue(
            "0 flow entries have been shown" in conntrack_list_result.stderr)

    @neutron.skip_unless_is_ovn()
    @keystone.skip_if_missing_service(name='octavia')
    def test_sg_and_loadbalancer_together(self):
        """Test that stateless SG will work fine together with Octavia LB.

        This test ensures that stateless SG works fine even when Octavia
        Loadbalancer is connected to the same network as VM using stateless SG.
        This test is coverage for the issue found in the past and reported in
        https://bugs.launchpad.net/neutron/+bug/2024502

        Steps:
        1. Create LB, listener, pool and member connected to that pool,
        2. Create VM connected to the same network as pool's member. This VM
           uses Stateless SG,
        3. Check SSH connectivity to the VM created in step 2.
        """

        octavia.deploy_ipv4_ovn_lb(
            servers_stacks=[self.lb_member_server]
        )
        # Ensure that ssh connection to the vm works as expected
        sh.execute('hostname', ssh_client=self.vm.ssh_client)
