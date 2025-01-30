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

from tobiko.openstack.stacks import _cirros
from tobiko.openstack.stacks import _designate
from tobiko.openstack.stacks import _l3ha
from tobiko.openstack.stacks import _neutron
from tobiko.openstack.stacks import _nova
from tobiko.openstack.stacks import _octavia
from tobiko.openstack.stacks import _qos
from tobiko.openstack.stacks import _advanced_vm
from tobiko.openstack.stacks import _vlan


CirrosFlavorStackFixture = _cirros.CirrosFlavorStackFixture
CirrosImageFixture = _cirros.CirrosImageFixture
CirrosServerStackFixture = _cirros.CirrosServerStackFixture
CirrosNoFipServerStackFixture = _cirros.CirrosNoFipServerStackFixture
CirrosServerWithDefaultSecurityGroupStackFixture = (
    _cirros.CirrosServerWithDefaultSecurityGroupStackFixture)
CirrosShellConnection = _cirros.CirrosShellConnection
CirrosPeerServerStackFixture = _cirros.CirrosPeerServerStackFixture
CirrosDifferentHostServerStackFixture = (
    _cirros.CirrosDifferentHostServerStackFixture)
CirrosSameHostServerStackFixture = _cirros.CirrosSameHostServerStackFixture
RebootCirrosServerOperation = _cirros.RebootCirrosServerOperation
EvacuableCirrosImageFixture = _cirros.EvacuableCirrosImageFixture
EvacuableServerStackFixture = _cirros.EvacuableServerStackFixture
ExtraDhcpOptsCirrosServerStackFixture = (
    _cirros.ExtraDhcpOptsCirrosServerStackFixture)
MultiIPCirrosServerStackFixture = (
    _cirros.MultiIPCirrosServerStackFixture)

DesignateZoneStackFixture = _designate.DesignateZoneStackFixture

L3haNetworkStackFixture = _l3ha.L3haNetworkStackFixture
L3haServerStackFixture = _l3ha.L3haServerStackFixture
L3haPeerServerStackFixture = _l3ha.L3haPeerServerStackFixture
L3haDifferentHostServerStackFixture = _l3ha.L3haDifferentHostServerStackFixture
L3haSameHostServerStackFixture = _l3ha.L3haSameHostServerStackFixture

FloatingIpStackFixture = _neutron.FloatingIpStackFixture
NetworkBaseStackFixture = _neutron.NetworkBaseStackFixture
NetworkStackFixture = _neutron.NetworkStackFixture
NetworkWithNetMtuWriteStackFixture = (
    _neutron.NetworkWithNetMtuWriteStackFixture)
RouterInterfaceStackFixture = _neutron.RouterInterfaceStackFixture
RouterStackFixture = _neutron.RouterStackFixture
SecurityGroupsFixture = _neutron.SecurityGroupsFixture
StatelessSecurityGroupFixture = _neutron.StatelessSecurityGroupFixture
get_external_network = _neutron.get_external_network
has_external_network = _neutron.has_external_network
skip_unless_has_external_network = _neutron.skip_unless_has_external_network
get_floating_network_id = _neutron.get_floating_network_id
get_floating_network = _neutron.get_floating_network
ensure_router_interface = _neutron.ensure_router_interface
has_floating_network = _neutron.has_floating_network
skip_unless_has_floating_network = _neutron.skip_unless_has_floating_network
get_router_id = _neutron.get_router_id
get_router = _neutron.get_router
has_router = _neutron.has_router
skip_unless_has_router = _neutron.skip_unless_has_router


ServerStackFixture = _nova.ServerStackFixture
KeyPairStackFixture = _nova.KeyPairStackFixture
FlavorStackFixture = _nova.FlavorStackFixture
ServerGroupStackFixture = _nova.ServerGroupStackFixture
AffinityServerGroupStackFixture = _nova.AffinityServerGroupStackFixture
AntiAffinityServerGroupStackFixture = _nova.AntiAffinityServerGroupStackFixture
CloudInitServerStackFixture = _nova.CloudInitServerStackFixture

# Octavia resources: backend servers
OctaviaServerStackFixture = _octavia.OctaviaServerStackFixture
OctaviaOtherServerStackFixture = _octavia.OctaviaOtherServerStackFixture

QosNetworkStackFixture = _qos.QosNetworkStackFixture
QosPolicyStackFixture = _qos.QosPolicyStackFixture
QosServerStackFixture = _qos.QosServerStackFixture

AdvancedFlavorStackFixture = _advanced_vm.AdvancedFlavorStackFixture
AdvancedImageFixture = _advanced_vm.AdvancedImageFixture
AdvancedServerStackFixture = _advanced_vm.AdvancedServerStackFixture
AdvancedExternalServerStackFixture = \
    _advanced_vm.AdvancedExternalServerStackFixture

VlanNetworkStackFixture = _vlan.VlanNetworkStackFixture
VlanProxyServerStackFixture = _vlan.VlanProxyServerStackFixture
