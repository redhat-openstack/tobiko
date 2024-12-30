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

from tobiko.shell.ping import _assert
from tobiko.shell.ping import _exception
from tobiko.shell.ping import _interface
from tobiko.shell.ping import _parameters
from tobiko.shell.ping import _ping
from tobiko.shell.ping import _statistics


assert_reachable_hosts = _assert.assert_reachable_hosts
assert_unreachable_hosts = _assert.assert_unreachable_hosts

BadAddressPingError = _exception.BadAddressPingError
LocalPingError = _exception.LocalPingError
ConnectPingError = _exception.ConnectPingError
PingFailed = _exception.PingFailed
PingError = _exception.PingError
ReachableHostsException = _exception.ReachableHostsException
UnreachableHostsException = _exception.UnreachableHostsException
PingException = _exception.PingException
SendToPingError = _exception.SendToPingError
UnknowHostError = _exception.UnknowHostError

skip_if_missing_fragment_ping_option = (
    _interface.skip_if_missing_fragment_ping_option)
has_ping_fragment_option = _interface.has_fragment_ping_option

ping_parameters = _parameters.ping_parameters
get_ping_parameters = _parameters.get_ping_parameters
default_ping_parameters = _parameters.default_ping_parameters

list_reachable_hosts = _ping.list_reachable_hosts
list_unreachable_hosts = _ping.list_unreachable_hosts
ping = _ping.ping
ping_hosts = _ping.ping_hosts
ping_until_delivered = _ping.ping_until_delivered
ping_until_undelivered = _ping.ping_until_undelivered
ping_until_received = _ping.ping_until_received
ping_until_unreceived = _ping.ping_until_unreceived
wait_for_ping_hosts = _ping.wait_for_ping_hosts

TRANSMITTED = _ping.TRANSMITTED
UNDELIVERED = _ping.UNDELIVERED
DELIVERED = _ping.DELIVERED
RECEIVED = _ping.RECEIVED
UNRECEIVED = _ping.UNRECEIVED

PingStatistics = _statistics.PingStatistics
write_ping_to_file = _ping.write_ping_to_file
check_ping_statistics = _ping.check_ping_statistics
skip_check_ping_statistics = _ping.skip_check_ping_statistics
ping_alive = _ping.ping_alive
stop_ping = _ping.stop_ping
check_ping_results = _ping.check_ping_results
execute_ping_in_background = _ping.execute_ping_in_background
