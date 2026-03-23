# Copyright (c) 2026 Red Hat, Inc.
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

from tobiko.shell.ping import _statistics
from tobiko.tests import unit


PING_OUTPUT = """\
PING 192.168.122.1 (192.168.122.1) 56(84) bytes of data.
64 bytes from 192.168.122.1: icmp_seq=1 ttl=63 time=1.0 ms
64 bytes from 192.168.122.1: icmp_seq=2 ttl=63 time=0.5 ms

--- 192.168.122.1 ping statistics ---
2694 packets transmitted, 1329 received, 50.6682% packet loss, time 2754208ms
rtt min/avg/max/mdev = 0.325/0.790/38.275/1.722 ms
"""


class ParsePingStatisticsTest(unit.TobikoUnitTest):

    def test_parse_ping_statistics_transmitted(self):
        stats = _statistics.parse_ping_statistics(PING_OUTPUT)
        self.assertEqual(2694, stats.transmitted)

    def test_parse_ping_statistics_received(self):
        stats = _statistics.parse_ping_statistics(PING_OUTPUT)
        self.assertEqual(1329, stats.received)

    def test_parse_ping_statistics_destination(self):
        stats = _statistics.parse_ping_statistics(PING_OUTPUT)
        self.assertEqual('192.168.122.1', str(stats.destination))

    def test_extract_integer_multi_digit(self):
        self.assertEqual(
            2694, _statistics.extract_integer('2694 packets transmitted'))
