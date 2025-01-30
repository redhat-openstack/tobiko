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

import netaddr
import pytest
import testtools

import tobiko
from tobiko import config
from tobiko.openstack import stacks
from tobiko.shell import ip
from tobiko.shell import ping
from tobiko.shell import sh
from tobiko.shell import ssh
from tobiko.tests.functional.shell import _fixtures


CONF = config.CONF

SshClientType = typing.Union[bool, None, ssh.SSHClientFixture]


class PingTest(testtools.TestCase):

    ssh_client: SshClientType = False

    @property
    def execute_params(self):
        return dict(ssh_client=self.ssh_client)

    def test_ping_reachable_address(self):
        result = ping.ping('127.0.0.1', count=3,
                           **self.execute_params)
        self.assertIsNone(result.source)
        self.assertEqual(netaddr.IPAddress('127.0.0.1'), result.destination)
        result.assert_transmitted()
        result.assert_replied()

    def test_ping_reachable_hostname(self):
        result = ping.ping('localhost', count=3, **self.execute_params)
        self.assertIsNone(result.source)
        self.assertIsNotNone(result.destination)
        result.assert_transmitted()
        result.assert_replied()

    def test_ping_unreachable_address(self):
        result = ping.ping('1.2.3.4', count=3, check=False,
                           **self.execute_params)
        self.assertIsNone(result.source)
        self.assertIn(result.destination, [netaddr.IPAddress('1.2.3.4'),
                                           None])
        if result.destination is not None:
            result.assert_transmitted()
        result.assert_not_replied()

    def test_ping_invalid_ip(self):
        try:
            result = ping.ping('0.1.2.3', count=1,
                               **self.execute_params)
        except ping.PingError as ex:
            self.assertIn(ex, [
                ping.ConnectPingError(details='Invalid argument'),
                ping.ConnectPingError(details='Network is unreachable'),
                ping.SendToPingError(details='No route to host'),
            ])
        else:
            self.assertIsNone(result.source)
            self.assertEqual(netaddr.IPAddress('0.1.2.3'),
                             result.destination)
            result.assert_transmitted()
            result.assert_not_replied()

    def test_ping_unreachable_hostname(self):
        ex = self.assertRaises(ping.PingError, ping.ping,
                               'unreachable-host', count=3,
                               **self.execute_params)
        self.assertIn(ex, [
            ping.UnknowHostError(details=''),
            ping.UnknowHostError(details='unreachable-host'),
            ping.UnknowHostError(
                details='Temporary failure in name resolution'),
            ping.BadAddressPingError(address='unreachable-host'),
            ping.UnknowHostError(
                details='Name or service not known')
        ])

    def test_ping_until_received(self):
        result = ping.ping_until_received('127.0.0.1', count=3,
                                          **self.execute_params)
        self.assertIsNone(result.source)
        self.assertEqual(netaddr.IPAddress('127.0.0.1'), result.destination)
        result.assert_transmitted()
        result.assert_replied()

    def test_ping_until_received_unreachable(self):
        ex = self.assertRaises(ping.PingError, ping.ping_until_received,
                               '1.2.3.4', count=3, timeout=6,
                               **self.execute_params)
        self.assertIn(ex, [
            ping.PingFailed(timeout=6, count=0, expected_count=3,
                            message_type='received'),
            ping.ConnectPingError(details='Network is unreachable')])

    def test_ping_until_unreceived_reachable(self):
        ex = self.assertRaises(ping.PingFailed, ping.ping_until_unreceived,
                               '127.0.0.1', count=3, timeout=6,
                               **self.execute_params)
        self.assertEqual(6, ex.timeout)
        self.assertEqual(0, ex.count)
        self.assertEqual(3, ex.expected_count)
        self.assertEqual('unreceived', ex.message_type)

    def test_ping_until_unreceived_unreachable(self):
        result = ping.ping_until_unreceived('1.2.3.4', count=3, check=False,
                                            **self.execute_params)
        self.assertIsNone(result.source)
        if result.destination is None:
            result.assert_not_transmitted()
        else:
            self.assertEqual(result.destination, netaddr.IPAddress('1.2.3.4'))
            result.assert_transmitted()
        result.assert_not_replied()

    def test_ping_reachable_with_timeout(self):
        ex = self.assertRaises(ping.PingFailed, ping.ping, '127.0.0.1',
                               count=20, timeout=1.,
                               **self.execute_params)
        self.assertEqual(1., ex.timeout)
        self.assertEqual(20, ex.expected_count)
        self.assertEqual('transmitted', ex.message_type)

    def test_ping_hosts(self):
        sh.find_command('ip', ssh_client=self.ssh_client, skip=True)
        ips = ip.list_ip_addresses(**self.execute_params)
        reachable_ips, unreachable_ips = ping.ping_hosts(
            ips, **self.execute_params)

        expected_reachable = [i for i in ips if i in reachable_ips]
        self.assertEqual(expected_reachable, reachable_ips)
        expected_unreachable = [i for i in ips if i not in reachable_ips]
        self.assertEqual(expected_unreachable, unreachable_ips)

    def test_assert_reachable_hosts(self):
        ping.assert_reachable_hosts(['127.0.0.1'], count=3,
                                    **self.execute_params)

    def test_assert_unreachable_hosts(self):
        ping.assert_unreachable_hosts(['0.1.2.3'], count=3,
                                      **self.execute_params)

    def test_assert_reachable_hosts_failure(self):
        ex = self.assertRaises(
            ping.UnreachableHostsException,
            ping.assert_reachable_hosts,
            ['0.1.2.3'], count=3,
            retry_count=1,
            retry_timeout=1.,
            **self.execute_params)
        self.assertEqual(['0.1.2.3'], ex.hosts)
        self.assertEqual(1., ex.timeout)

    def test_assert_unreachable_hosts_failure(self):
        ex = self.assertRaises(
            ping.ReachableHostsException,
            ping.assert_unreachable_hosts,
            ['127.0.0.1'], count=3,
            retry_count=1,
            retry_timeout=1.,
            **self.execute_params)
        self.assertEqual(['127.0.0.1'], ex.hosts)
        self.assertEqual(1., ex.timeout)


@ssh.skip_unless_has_ssh_proxy_jump
class ProxyPingTest(PingTest):
    ssh_client = None


@pytest.mark.flaky(reruns=3, reruns_delay=5)
class NamespacePingTest(PingTest):

    namespace = tobiko.required_fixture(_fixtures.NetworkNamespaceFixture)

    @property
    def ssh_client(self):
        return self.namespace.ssh_client

    @property
    def network_namespace(self):
        return self.namespace.network_namespace

    @property
    def execute_params(self):
        return dict(ssh_client=self.ssh_client,
                    network_namespace=self.network_namespace)


class CirrosPingTest(PingTest):

    stack = tobiko.required_fixture(stacks.CirrosServerStackFixture)

    @property
    def ssh_client(self):
        return self.stack.ssh_client


class AdvancedPingTest(CirrosPingTest):

    stack = tobiko.required_fixture(stacks.AdvancedServerStackFixture)
