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

from tobiko.shell.ping import _interface
from tobiko.shell.ping import _parameters
from tobiko.tests import unit


def _make_parameters(**kwargs):
    defaults = dict(
        host='192.168.0.1',
        count=1,
        deadline=5,
        fragmentation=None,
        interval=1,
        ip_version=None,
        packet_size=None,
        source=None,
        timeout=300,
        network_namespace=None,
        timestamps=True,
    )
    defaults.update(kwargs)
    return _parameters.PingParameters(**defaults)


class IpUtilsIntervalOptionTest(unit.TobikoUnitTest):

    def test_interval_option_with_sub_second(self):
        interface = _interface.IpUtilsPingInterface()
        params = _make_parameters(interval=0.2)
        options = interface.get_ping_options(params)
        self.assertIn('-i', options)
        self.assertIn(0.2, options)

    def test_interval_option_skipped_at_default(self):
        interface = _interface.IpUtilsPingInterface()
        params = _make_parameters(interval=1)
        options = interface.get_ping_options(params)
        self.assertNotIn('-i', options)

    def test_interval_option_with_value_above_one(self):
        interface = _interface.IpUtilsPingInterface()
        params = _make_parameters(interval=5)
        options = interface.get_ping_options(params)
        self.assertIn('-i', options)
        self.assertIn(5, options)

    def test_interval_option_whole_float_becomes_int(self):
        interface = _interface.IpUtilsPingInterface()
        params = _make_parameters(interval=10.0)
        options = interface.get_ping_options(params)
        idx = options.index('-i')
        self.assertIsInstance(options[idx + 1], int)
        self.assertEqual(10, options[idx + 1])


class IpUtilsTimestampOptionTest(unit.TobikoUnitTest):

    def test_timestamp_option_present(self):
        interface = _interface.IpUtilsPingInterface()
        params = _make_parameters(timestamps=True)
        options = interface.get_ping_options(params)
        self.assertIn('-D', options)

    def test_timestamp_option_absent_when_disabled(self):
        interface = _interface.IpUtilsPingInterface()
        params = _make_parameters(timestamps=False)
        options = interface.get_ping_options(params)
        self.assertNotIn('-D', options)

    def test_timestamp_option_absent_when_none(self):
        interface = _interface.IpUtilsPingInterface()
        params = _make_parameters(timestamps=None)
        options = interface.get_ping_options(params)
        self.assertNotIn('-D', options)


class IpUtilsIpVersionTimestampOptionTest(unit.TobikoUnitTest):

    def test_timestamp_option_present(self):
        interface = _interface.IpUtilsIpVersionPingInterface()
        params = _make_parameters(timestamps=True)
        options = interface.get_ping_options(params)
        self.assertIn('-D', options)


class BusyBoxTimestampOptionTest(unit.TobikoUnitTest):

    def test_timestamp_option_not_supported(self):
        interface = _interface.BusyBoxPingInterface()
        params = _make_parameters(timestamps=True)
        options = interface.get_ping_options(params)
        self.assertNotIn('-D', options)


class InetToolsTimestampOptionTest(unit.TobikoUnitTest):

    def test_timestamp_option_not_supported(self):
        interface = _interface.InetToolsPingInterface()
        params = _make_parameters(timestamps=True)
        options = interface.get_ping_options(params)
        self.assertNotIn('-D', options)


class BsdTimestampOptionTest(unit.TobikoUnitTest):

    def test_timestamp_option_not_supported(self):
        interface = _interface.BsdPingInterface()
        params = _make_parameters(timestamps=True)
        options = interface.get_ping_options(params)
        self.assertNotIn('-D', options)
