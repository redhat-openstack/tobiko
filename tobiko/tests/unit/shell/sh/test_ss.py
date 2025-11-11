# Copyright (c) 2025 Red Hat, Inc.
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

from tobiko.shell import ss
from tobiko.tests import unit


class SockHeaderTest(unit.TobikoUnitTest):

    def test_parse_header_basic(self):
        header_str = 'Recv-Q Send-Q Local Address:Port Peer Address:Port'
        header = ss.SockHeader(header_str)
        self.assertEqual(['recv_q', 'send_q', 'local', 'remote'],
                         list(header))

    def test_parse_header_with_netid(self):
        header_str = 'Netid Recv-Q Send-Q Local Address:Port Peer Address:Port'
        header = ss.SockHeader(header_str)
        self.assertEqual(['protocol', 'recv_q', 'send_q', 'local', 'remote'],
                         list(header))

    def test_parse_header_with_state(self):
        header_str = 'State Recv-Q Send-Q Local Address:Port Peer Address:Port'
        header = ss.SockHeader(header_str)
        self.assertEqual(['state', 'recv_q', 'send_q', 'local', 'remote'],
                         list(header))

    def test_parse_header_with_process(self):
        header_str = ('Recv-Q Send-Q Local Address:Port '
                      'Peer Address:Port Process')
        header = ss.SockHeader(header_str)
        self.assertEqual(['recv_q', 'send_q', 'local', 'remote', 'process'],
                         list(header))

    def test_extend_ports(self):
        header_str = 'Recv-Q Send-Q Local Address:Port Peer Address:Port'
        header = ss.SockHeader(header_str)
        header.extend_ports()
        self.assertEqual(['recv_q', 'send_q', 'local_addr', 'local_port',
                          'remote_addr', 'remote_port'],
                         list(header))


class GetProcessesTest(unit.TobikoUnitTest):

    def test_single_process(self):
        processes_str = 'users:(("httpd",pid=735448,fd=11))'
        result = ss.get_processes(processes_str)
        self.assertEqual(['httpd'], result)

    def test_multiple_processes(self):
        """Test parsing multiple processes

        Note: The current implementation of get_processes only returns the
        first process name from the list. This appears to be a limitation
        of the current implementation.
        """
        processes_str = ('users:(("httpd",pid=4969,fd=53),'
                         '("httpd",pid=3328,fd=53))')
        result = ss.get_processes(processes_str)
        # Current behavior returns only first process
        self.assertEqual(['httpd'], result)

    def test_different_process_names(self):
        """Test parsing different process names

        Note: The current implementation of get_processes only returns the
        first process name from the list. This appears to be a limitation
        of the current implementation.
        """
        processes_str = ('users:(("nginx",pid=1234,fd=10),'
                         '("worker",pid=5678,fd=20))')
        result = ss.get_processes(processes_str)
        # Current behavior returns only first process
        self.assertEqual(['nginx'], result)


class ParseTcpSocketTest(unit.TobikoUnitTest):

    def test_parse_ipv4_socket(self):
        """Test parsing IPv4 socket with specific addresses"""
        headers = ss.SockHeader(
            'Recv-Q Send-Q Local Address:Port Peer Address:Port Process')
        sock_info = ss.SockLine(
            '0      10     192.168.1.1:80 192.168.1.2:54321 '
            'users:(("httpd",pid=1234,fd=5))')

        result = ss.parse_tcp_socket(headers, sock_info)

        self.assertEqual('0', result['recv_q'])
        self.assertEqual('10', result['send_q'])
        self.assertEqual(netaddr.IPAddress('192.168.1.1'),
                         result['local_addr'])
        self.assertEqual('80', result['local_port'])
        self.assertEqual(netaddr.IPAddress('192.168.1.2'),
                         result['remote_addr'])
        self.assertEqual('54321', result['remote_port'])
        self.assertEqual(['httpd'], result['process'])

    def test_parse_ipv4_wildcard_both_addresses(self):
        """Test parsing IPv4 socket with wildcard 0.0.0.0 addresses"""
        headers = ss.SockHeader(
            'Recv-Q Send-Q Local Address:Port Peer Address:Port Process')
        sock_info = ss.SockLine(
            '0      10     0.0.0.0:6641 0.0.0.0:* '
            'users:(("ovsdb-server",pid=62494,fd=29))')

        result = ss.parse_tcp_socket(headers, sock_info)

        self.assertEqual(netaddr.IPAddress('0.0.0.0'), result['local_addr'])
        self.assertEqual('6641', result['local_port'])
        self.assertEqual(netaddr.IPAddress('0.0.0.0'), result['remote_addr'])
        self.assertEqual('*', result['remote_port'])
        self.assertEqual(['ovsdb-server'], result['process'])

    def test_parse_ipv4_wildcard_asterisk(self):
        """Test parsing IPv4 socket with asterisk wildcard (listening)

        This tests the fix for netaddr 1.3.0 compatibility where '*' should
        be converted to '0.0.0.0' for IPv4 sockets.
        """
        headers = ss.SockHeader(
            'Recv-Q Send-Q Local Address:Port Peer Address:Port Process')
        sock_info = ss.SockLine(
            '0      10     192.168.1.1:80 *:* '
            'users:(("httpd",pid=1234,fd=5))')

        result = ss.parse_tcp_socket(headers, sock_info)

        # When local is a specific IPv4, wildcard remote should be 0.0.0.0
        self.assertEqual(netaddr.IPAddress('192.168.1.1'),
                         result['local_addr'])
        self.assertEqual('80', result['local_port'])
        self.assertEqual(netaddr.IPAddress('0.0.0.0'), result['remote_addr'])
        self.assertEqual('*', result['remote_port'])

    def test_parse_ipv6_socket(self):
        """Test parsing IPv6 socket with specific addresses"""
        headers = ss.SockHeader(
            'Recv-Q Send-Q Local Address:Port Peer Address:Port Process')
        sock_info = ss.SockLine(
            '0      10     [fd00:192:170:1::166]:80 '
            '[fd00:192:170:1::167]:54321 users:(("httpd",pid=1234,fd=5))')

        result = ss.parse_tcp_socket(headers, sock_info)

        self.assertEqual(netaddr.IPAddress('fd00:192:170:1::166'),
                         result['local_addr'])
        self.assertEqual('80', result['local_port'])
        self.assertEqual(netaddr.IPAddress('fd00:192:170:1::167'),
                         result['remote_addr'])
        self.assertEqual('54321', result['remote_port'])

    def test_parse_ipv6_wildcard_asterisk(self):
        """Test parsing IPv6 socket with asterisk wildcard (listening)

        This tests the fix for netaddr 1.3.0 compatibility where '*' should
        be converted to '::' for IPv6 sockets. This is the actual case that
        was failing in IPv6 environments.
        """
        headers = ss.SockHeader(
            'Recv-Q Send-Q Local Address:Port Peer Address:Port Process')
        sock_info = ss.SockLine(
            '0      10     *:6641 *:* '
            'users:(("ovsdb-server",pid=61929,fd=29))')

        result = ss.parse_tcp_socket(headers, sock_info)

        # When both are wildcards and no IP version hint, defaults to IPv6
        self.assertEqual(netaddr.IPAddress('::'), result['local_addr'])
        self.assertEqual('6641', result['local_port'])
        self.assertEqual(netaddr.IPAddress('::'), result['remote_addr'])
        self.assertEqual('*', result['remote_port'])
        self.assertEqual(['ovsdb-server'], result['process'])

    def test_parse_ipv6_wildcard_with_specific_local(self):
        """Test parsing IPv6 socket with specific local and wildcard remote"""
        headers = ss.SockHeader(
            'Recv-Q Send-Q Local Address:Port Peer Address:Port Process')
        sock_info = ss.SockLine(
            '0      10     [fd00:192:170:1::166]:6641 *:* '
            'users:(("ovsdb-server",pid=61929,fd=29))')

        result = ss.parse_tcp_socket(headers, sock_info)

        # When local is IPv6, wildcard remote should be ::
        self.assertEqual(netaddr.IPAddress('fd00:192:170:1::166'),
                         result['local_addr'])
        self.assertEqual('6641', result['local_port'])
        self.assertEqual(netaddr.IPAddress('::'), result['remote_addr'])
        self.assertEqual('*', result['remote_port'])

    def test_parse_socket_with_state(self):
        """Test parsing socket with state field"""
        headers = ss.SockHeader(
            'State Recv-Q Send-Q Local Address:Port Peer Address:Port Process')
        sock_info = ss.SockLine(
            'ESTAB 0      0     192.168.1.1:22 192.168.1.2:54321 '
            'users:(("sshd",pid=1234,fd=5))')

        result = ss.parse_tcp_socket(headers, sock_info)

        self.assertEqual('ESTAB', result['state'])
        self.assertEqual('0', result['recv_q'])
        self.assertEqual('0', result['send_q'])

    def test_parse_socket_multiple_processes(self):
        """Test parsing socket with multiple processes

        Note: Due to current limitation of get_processes, only the first
        process name is captured.
        """
        headers = ss.SockHeader(
            'Recv-Q Send-Q Local Address:Port Peer Address:Port Process')
        sock_info = ss.SockLine(
            '0      10     192.168.1.1:80 192.168.1.2:54321 '
            'users:(("httpd",pid=4969,fd=53),("httpd",pid=3328,fd=53))')

        result = ss.parse_tcp_socket(headers, sock_info)

        # Current behavior captures only first process
        self.assertEqual(['httpd'], result['process'])

    def test_parse_socket_invalid_line(self):
        """Test parsing fails gracefully with invalid line"""
        headers = ss.SockHeader(
            'Recv-Q Send-Q Local Address:Port Peer Address:Port Process')
        sock_info = ss.SockLine('0 10 192.168.1.1:80')  # Missing fields

        ex = self.assertRaises(ValueError,
                               ss.parse_tcp_socket,
                               headers,
                               sock_info)
        self.assertIn('Unable to parse line', str(ex))


class ParseUnixSocketTest(unit.TobikoUnitTest):

    def test_parse_unix_socket(self):
        """Test parsing Unix domain socket"""
        headers = ss.SockHeader(
            'Netid Recv-Q Send-Q Local Address:Port Peer Address:Port Process')
        headers.extend_ports()
        sock_info = ss.SockLine(
            'u_str 0      0     /var/run/socket.sock * * * '
            'users:(("daemon",pid=1234,fd=5))')

        result = ss.parse_unix_socket(headers, sock_info)

        self.assertEqual('u_str', result['protocol'])
        self.assertEqual('0', result['recv_q'])
        self.assertEqual('0', result['send_q'])
        self.assertEqual('/var/run/socket.sock', result['local_addr'])
        self.assertEqual(['daemon'], result['process'])
