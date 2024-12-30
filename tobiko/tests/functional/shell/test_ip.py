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

import netaddr
import pytest
import testtools

import tobiko
from tobiko.openstack import stacks
from tobiko.shell import ip
from tobiko.shell import sh
from tobiko.shell import ssh
from tobiko.tests.functional.shell import _fixtures


class IpTest(testtools.TestCase):

    cirros_stack = tobiko.required_fixture(
        stacks.CirrosServerStackFixture)

    advanced_vm_stack = tobiko.required_fixture(
        stacks.AdvancedServerStackFixture)

    namespace = tobiko.required_fixture(
        _fixtures.NetworkNamespaceFixture)

    def test_list_ip_addresses(self,
                               ip_version=None,
                               scope=None,
                               ssh_client: ssh.SSHClientType = None,
                               **execute_params):
        sh.find_command('ip', ssh_client=ssh_client, skip=True)
        ips = ip.list_ip_addresses(ip_version=ip_version,
                                   scope=scope,
                                   ssh_client=ssh_client,
                                   **execute_params)
        self.assertIsInstance(ips, tobiko.Selection)
        for ip_address in ips:
            self.assertIsInstance(ip_address, netaddr.IPAddress)
        if ip_version:
            self.assertEqual(ips.with_attributes(version=ip_version), ips)
        if scope:
            if scope == 'link':
                self.assertEqual(ips.with_attributes(version=4), [])
                self.assertEqual(ips.with_attributes(version=6), ips)
            elif scope == 'host':
                for a in ips:
                    self.assertTrue(a.is_loopback())
            elif scope == 'global':
                self.assertNotIn(netaddr.IPAddress('127.0.0.1'), ips)
                self.assertNotIn(netaddr.IPAddress('::1'), ips)
        return ips

    def test_list_ip_addresses_with_host_scope(self, **execute_params):
        self.test_list_ip_addresses(scope='host', **execute_params)

    def test_list_ip_addresses_with_link_scope(self, **execute_params):
        self.test_list_ip_addresses(scope='link', **execute_params)

    def test_list_ip_addresses_with_global_scope(self, **execute_params):
        self.test_list_ip_addresses(scope='global', **execute_params)

    def test_list_ip_addresses_with_ipv4(self):
        self.test_list_ip_addresses(ip_version=4)

    def test_list_ip_addresses_with_ipv6(self):
        self.test_list_ip_addresses(ip_version=6)

    def test_list_ip_addresses_with_cirros_server(self):
        self.test_list_ip_addresses(ssh_client=self.cirros_stack.ssh_client)

    def test_list_ip_addresses_with_advanced_server(self):
        self.test_list_ip_addresses(
            ssh_client=self.advanced_vm_stack.ssh_client)

    def test_list_ip_addresses_with_proxy_ssh_client(self):
        ssh_client = ssh.ssh_proxy_client()
        if ssh_client is None:
            self.skipTest('SSH proxy server not configured')
        self.test_list_ip_addresses(ssh_client=ssh_client)

    def test_list_ip_addresses_with_proxy_ssh_client_and_host_scope(
                self, **execute_params):
        self.test_list_ip_addresses(scope='host', **execute_params)

    def test_list_ip_addresses_with_proxy_ssh_client_and_link_scope(
                self, **execute_params):
        self.test_list_ip_addresses(scope='link', **execute_params)

    def test_list_ip_addresses_with_proxy_ssh_client_and_global_scope(
                self, **execute_params):
        self.test_list_ip_addresses(scope='global', **execute_params)

    @pytest.mark.flaky(reruns=3, reruns_delay=5)
    def test_list_ip_addresses_with_namespace(self, **params):
        namespace_ips = ip.list_ip_addresses(
            ssh_client=self.namespace.ssh_client,
            network_namespace=self.namespace.network_namespace, **params)
        self.assertNotEqual([], namespace_ips)

        host_ips = ip.list_ip_addresses(ssh_client=self.namespace.ssh_client,
                                        **params)
        self.assertNotEqual(host_ips, namespace_ips)

    @pytest.mark.flaky(reruns=3, reruns_delay=5)
    def test_list_ip_addresses_with_namespace_and_scope(self):
        self.test_list_ip_addresses_with_namespace(scope='global')

    @pytest.mark.flaky(reruns=3, reruns_delay=5)
    def test_list_ip_addresses_with_failing_command(self):
        self.assertRaises(ip.IpError, ip.list_ip_addresses,
                          ip_command=['false'],
                          ssh_client=self.namespace.ssh_client)

    def test_list_ip_addresses_with_ignore_errors(self, **execute_params):
        self.test_list_ip_addresses(ignore_errors=True, ip_command='false',
                                    **execute_params)

    @pytest.mark.flaky(reruns=3, reruns_delay=5)
    def test_list_namespaces(self,
                             ignore_errors=False,
                             ssh_client: ssh.SSHClientType = None,
                             **execute_params):
        sh.find_command('ip', ssh_client=ssh_client, skip=True)
        namespaces = ip.list_network_namespaces(ignore_errors=ignore_errors,
                                                ssh_client=ssh_client,
                                                **execute_params)
        self.assertIsInstance(namespaces, list)
        for namespace in namespaces:
            self.assertIsInstance(namespace, str)
            self.test_list_ip_addresses(network_namespace=namespace)

    @pytest.mark.flaky(reruns=3, reruns_delay=5)
    def test_list_namespaces_with_advanced_server(self):
        self.test_list_namespaces(ssh_client=self.advanced_vm_stack.ssh_client)

    @pytest.mark.flaky(reruns=3, reruns_delay=5)
    def test_list_namespaces_with_proxy_ssh_client(self):
        ssh_client = ssh.ssh_proxy_client()
        if ssh_client is None:
            self.skipTest('SSH proxy server not configured')
        self.test_list_namespaces(ssh_client=ssh_client)

    @pytest.mark.flaky(reruns=3, reruns_delay=5)
    def test_list_namespaces_with_failing_command(self):
        self.assertRaises(ip.IpError, ip.list_network_namespaces,
                          ip_command=['false'],
                          ssh_client=self.namespace.ssh_client)

    @pytest.mark.flaky(reruns=3, reruns_delay=5)
    def test_list_namespaces_with_ignore_errors(self, **execute_params):
        self.test_list_namespaces(ignore_errors=True, ip_command='false',
                                  **execute_params)
