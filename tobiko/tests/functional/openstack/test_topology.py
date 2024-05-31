# Copyright (c) 2019 Red Hat, Inc.
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

import typing
from collections import abc
import random
import re

import testtools

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import neutron
from tobiko.openstack import nova
from tobiko.openstack import topology as osp_topology
from tobiko.shell import ping
from tobiko.shell import sh


PatternType = type(re.compile(r''))


@keystone.skip_unless_has_keystone_credentials()
class OpenStackTopologyTest(testtools.TestCase):

    expected_group: osp_topology.OpenstackGroupNamesType = None

    @property
    def topology(self) -> osp_topology.OpenStackTopology:
        return osp_topology.get_openstack_topology()

    def test_get_openstack_topology(self):
        topology_class = type(self.topology)
        topo = osp_topology.get_openstack_topology(
            topology_class=topology_class)
        self.assertIs(topo, self.topology)
        self.assertIsInstance(topo, osp_topology.OpenStackTopology)

    def test_ping_node(self):
        for node in self.topology.nodes:
            ping.ping(node.public_ip, count=1, timeout=5.).assert_replied()

    def test_ssh_client(self):
        for node in self.topology.nodes:
            self.assertIsNotNone(node.ssh_client)
            hostname = sh.ssh_hostname(
                ssh_client=node.ssh_client).split('.')[0]
            self.assertEqual(node.name, hostname)

    def test_controller_group(self):
        nodes = list(self.topology.get_group('controller'))
        self.assertNotEqual([], nodes)
        for node in nodes:
            self.assertIn('controller', node.groups)

    def test_compute_group(self):
        nodes = list(self.topology.get_group('compute'))
        self.assertNotEqual([], nodes)
        for node in nodes:
            self.assertIn('compute', node.groups)
        hypervisors = {
            hypervisor.hypervisor_hostname.split('.', 1)[0].lower(): hypervisor
            for hypervisor in nova.list_hypervisors()}
        for name, hypervisor in hypervisors.items():
            node = self.topology.get_node(name)
            self.assertEqual(name, node.name)
            self.assertIn(node, nodes)

    def test_list_openstack_topology(self, group=None, hostnames=None):
        nodes = osp_topology.list_openstack_nodes(
            topology=self.topology, group=group, hostnames=hostnames)
        self.assertTrue(set(nodes).issubset(set(self.topology.nodes)))
        self.assertEqual(len(set(nodes)), len(nodes),
                         f"Repeated node found: {nodes}")
        for node in nodes:
            if isinstance(group, str):
                self.assertIn(group, node.groups)
            elif isinstance(group, PatternType):
                for actual_group in node.groups:
                    if group.match(actual_group):
                        break
                else:
                    self.fail(f"Any node {node.name} group matches "
                              f"'{group}': {node.groups}")
            elif isinstance(group, abc.Iterable):
                matching_groups = set(group) & set(node.groups)
                self.assertNotEqual(set(), matching_groups,
                                    f"Any group of node {node.name} "
                                    f"matches '{group}': {node.groups}")
            if hostnames:
                hostnames = [node_name_from_hostname(h)
                             for h in hostnames]
                self.assertIn(node.name, hostnames)
        return nodes

    def test_list_openstack_topology_with_group(self):
        group = self.topology.groups[0]
        expected_nodes = set(self.topology.get_group(group))
        actual_nodes = set(self.test_list_openstack_topology(group=group))
        self.assertEqual(expected_nodes, actual_nodes)

    def test_list_openstack_topology_with_group_pattern(self):
        groups = list(self.topology.groups)[:2]
        pattern = re.compile('|'.join(groups))
        expected_nodes = set()
        for group in groups:
            expected_nodes.update(self.topology.get_group(group))
        actual_nodes = set(self.test_list_openstack_topology(group=pattern))
        self.assertEqual(expected_nodes, actual_nodes)

    def test_list_openstack_topology_with_groups(self):
        groups = list(self.topology.groups)[:2]
        expected_nodes = set()
        for group in groups:
            expected_nodes.update(self.topology.get_group(group))
        actual_nodes = set(self.test_list_openstack_topology(group=groups))
        self.assertEqual(expected_nodes, actual_nodes)

    def test_list_openstack_topology_with_hostnames(self):
        expected_nodes = self.topology.nodes[0::2]
        actual_nodes = self.test_list_openstack_topology(
            hostnames=[node.name for node in expected_nodes])
        self.assertEqual(expected_nodes, actual_nodes)

    def test_list_nodes_processes(self):
        node = random.choice(osp_topology.list_openstack_nodes(
            group=self.expected_group))
        filename = sh.execute(
            'mktemp', ssh_client=node.ssh_client).stdout.strip()
        self.addCleanup(sh.execute, f"rm -f '{filename}'",
                        ssh_client=node.ssh_client)
        command_line = sh.shell_command(f"tail -F '{filename}'")
        process = sh.process(command_line,
                             ssh_client=node.ssh_client)

        # Process isn't listed before creation
        processes = osp_topology.list_nodes_processes(
            command_line=command_line,
            hostnames=[node.hostname])
        self.assertEqual([], processes,
                         'Process listed before executing it')

        # Process is listed after creation
        process.execute()
        self.addCleanup(process.kill)
        processes = osp_topology.list_nodes_processes(
            command_line=command_line,
            hostnames=[node.hostname])
        self.assertEqual(command_line, processes.unique.command_line)
        self.assertIs(node.ssh_client, processes.unique.ssh_client)

        # Process isn't listed after kill
        processes.unique.kill()
        for attempt in tobiko.retry(timeout=30., interval=5.):
            processes = osp_topology.list_nodes_processes(
                command_line=command_line,
                hostnames=[node.hostname])
            if not processes:
                break
            if attempt.is_last:
                self.fail("Process listed after killing it")

    @neutron.skip_unless_is_ovs()
    def test_l3_agent_mode(self):
        for node in osp_topology.list_openstack_nodes(
                group=['controller', 'compute', 'overcloud']):
            assert isinstance(node, osp_topology.OpenStackTopologyNode)
            self.assertEqual(
                neutron.get_l3_agent_mode(
                    l3_agent_conf_path=node.l3_agent_conf_path,
                    connection=node.connection),
                node.l3_agent_mode)
            self.assertIs(node.l3_agent_mode, node.l3_agent_mode)


def node_name_from_hostname(hostname):
    return hostname.split('.', 1)[0].lower()


@keystone.skip_unless_has_keystone_credentials()
class HostsNamespaceTest(testtools.TestCase):

    @property
    def all_hostnames(self) -> typing.List[str]:
        nodes = osp_topology.list_openstack_nodes()
        return sorted(node.hostname for node in nodes)

    def selected_hostames(self, hostnames: typing.Iterable[str] = None) -> \
            typing.Set[str]:
        if hostnames is None:
            return set(self.all_hostnames)
        else:
            return set(hostnames)

    def test_get_hosts_namespaces(self,
                                  hostnames: typing.Iterable[str] = None):
        namespaces = osp_topology.get_hosts_namespaces(hostnames=hostnames)
        self.assertIsInstance(namespaces, dict)
        for namespace, _hostnames in namespaces.items():
            self.assertIsInstance(namespace, str)
            self.assertIsInstance(_hostnames, list)
            self.assertEqual(
                set(_hostnames),
                self.selected_hostames(hostnames) & set(_hostnames))

    def test_get_hosts_namespaces_with_hostnames(self):
        self.test_get_hosts_namespaces(hostnames=self.all_hostnames[:1])

    def test_assert_namespace_in_hosts(self,
                                       hostnames: typing.Iterable[str] = None):
        namespaces = osp_topology.get_hosts_namespaces(hostnames=hostnames)
        for namespace, hostnames in namespaces.items():
            osp_topology.assert_namespace_in_hosts(namespace,
                                                   hostnames=hostnames)

    def test_assert_namespace_in_hosts_with_hostnames(self):
        self.test_assert_namespace_in_hosts(hostnames=self.all_hostnames[:1])

    def test_assert_namespaces_in_host_failure(self):
        self.assertRaises(self.failureException,
                          osp_topology.assert_namespace_in_hosts,
                          '<invalid>')

    def test_assert_namespace_not_in_hosts(
            self, hostnames: typing.Iterable[str] = None):
        osp_topology.assert_namespace_not_in_hosts('<invalid>',
                                                   hostnames=hostnames)

    def test_assert_namespace_not_in_hosts_with_hostnames(self):
        self.test_assert_namespace_not_in_hosts(
            hostnames=self.all_hostnames[:1])

    def test_assert_namespace_not_in_hosts_failure(self):
        namespaces = osp_topology.get_hosts_namespaces()
        for namespace in namespaces:
            self.assertRaises(self.failureException,
                              osp_topology.assert_namespace_not_in_hosts,
                              namespace)
