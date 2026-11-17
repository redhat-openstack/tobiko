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

from oslo_log import log

from tobiko import config
from tobiko.openstack.stacks import _advanced_vm

CONF = config.CONF
LOG = log.getLogger(__name__)


class OctaviaServerStackFixture(_advanced_vm.AdvancedServerStackFixture):
    has_floating_ip = False


class OctaviaOtherServerStackFixture(OctaviaServerStackFixture):
    pass


class OctaviaClientServerStackFixture(
        _advanced_vm.AdvancedServerStackFixture):
    """Client server used to send traffic to Octavia VIPs from a tenant network

    It is attached to the same tenant network as the backend servers and,
    unlike them, it gets a floating IP so that tobiko can reach it over SSH.
    Traffic to the load balancer VIPs is sent from its fixed IPv4/IPv6
    addresses, so the VIPs do not need to be reachable from outside the
    cloud. It is not added as a pool member.
    """
