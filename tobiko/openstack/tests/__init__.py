# Copyright (c) 2020 Red Hat, Inc.
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


from tobiko.openstack.tests import _neutron
from tobiko.openstack.tests import _nova

test_neutron_agents_are_alive = _neutron.test_neutron_agents_are_alive
test_alive_agents_are_consistent_along_time = (
    _neutron.test_alive_agents_are_consistent_along_time)
test_ovn_dbs_validations = _neutron.test_ovn_dbs_validations
test_ovs_bridges_mac_table_size = _neutron.test_ovs_bridges_mac_table_size
test_ovs_namespaces_are_absent = _neutron.test_ovs_namespaces_are_absent
test_ovs_interfaces_are_absent = _neutron.test_ovs_interfaces_are_absent
test_raft_cluster = _neutron.test_raft_cluster
test_raft_clients_connected = _neutron.test_raft_clients_connected

test_evacuable_server_creation = _nova.test_evacuable_server_creation
test_server_creation = _nova.test_server_creation
test_servers_creation = _nova.test_servers_creation
test_server_creation_and_shutoff = _nova.test_server_creation_and_shutoff
test_server_creation_no_fip = _nova.test_server_creation_no_fip
TestServerCreationStack = _nova.TestServerCreationStack
TestEvacuableServerCreationStack = _nova.TestEvacuableServerCreationStack
test_ovsdb_transactions = _neutron.test_ovsdb_transactions
