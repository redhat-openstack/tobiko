# Copyright (c) 2021 Red Hat, Inc.
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

import tobiko
from tobiko import config
from tobiko.openstack import heat
from tobiko.openstack import neutron
from tobiko.openstack.stacks import _neutron
from tobiko.openstack.stacks import _hot
from tobiko.openstack.stacks import _ubuntu


CONF = config.CONF


@neutron.skip_if_missing_networking_extensions('qos')
class QosPolicyStackFixture(heat.HeatStackFixture):
    """Heat stack with a QoS Policy and some QoS Policy Rules
    """
    has_qos_policy = True
    has_bwlimit = True
    has_dscp_marking = True
    bwlimit_kbps = CONF.tobiko.neutron.bwlimit_kbps
    bwlimit_burst_kbps = int(0.8 * bwlimit_kbps)
    direction = CONF.tobiko.neutron.direction
    dscp_mark = CONF.tobiko.neutron.dscp_mark

    #: Heat template file
    template = _hot.heat_template_file('neutron/qos.yaml')


@neutron.skip_if_missing_networking_extensions('qos')
class QosNetworkStackFixture(_neutron.NetworkBaseStackFixture):

    #: stack with the qos policy for the network
    qos_stack = tobiko.required_fixture(QosPolicyStackFixture)

    has_qos_policy = True

    @property
    def network_value_specs(self):
        value_specs = super().network_value_specs
        return dict(value_specs, qos_policy_id=self.qos_stack.qos_policy_id)

    @tobiko.interworker_synched('create_qos_network_stack')
    def setup_stack(self):
        super().setup_stack()


class QosServerStackFixture(_ubuntu.UbuntuServerStackFixture):
    #: stack with the network with a qos policy
    network_stack = tobiko.required_fixture(QosNetworkStackFixture)

    @property
    def has_vlan(self) -> bool:
        # Trunk ports are not supported with QoS when ml2/ovs is used
        return False
