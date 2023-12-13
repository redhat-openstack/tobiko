# Copyright 2020 Red Hat
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

from tobiko.tripleo import _ansible
from tobiko.tripleo import _overcloud as overcloud
from tobiko.tripleo import _topology as topology
from tobiko.tripleo import _undercloud as undercloud
from tobiko.tripleo import containers
from tobiko.tripleo import services


get_tripleo_ansible_inventory = _ansible.get_tripleo_ansible_inventory
get_tripleo_ansible_inventory_file = \
    _ansible.get_tripleo_ansible_inventory_file
has_tripleo_ansible_inventory = _ansible.has_tripleo_ansible_inventory
read_tripleo_ansible_inventory = _ansible.read_tripleo_ansible_inventory
fetch_tripleo_inventary_file = _ansible.fetch_tripleo_inventary_file
skip_if_missing_tripleo_ansible_inventory = \
    _ansible.skip_if_missing_tripleo_ansible_inventory
skip_unless_undercloud_has_ansible = \
    _ansible.skip_unless_undercloud_has_ansible
run_playbook_from_undercloud = _ansible.run_playbook_from_undercloud

OvercloudKeystoneCredentialsFixture = \
    overcloud.OvercloudKeystoneCredentialsFixture
OvercloudNotFound = overcloud.OvercloudNotFound
OvercloudVersionMismatch = overcloud.OvercloudVersionMismatch
check_overcloud = overcloud.check_overcloud
find_overcloud_node = overcloud.find_overcloud_node
has_overcloud = overcloud.has_overcloud
list_overcloud_nodes = overcloud.list_overcloud_nodes
load_overcloud_rcfile = overcloud.load_overcloud_rcfile
overcloud_host_config = overcloud.overcloud_host_config
overcloud_keystone_client = overcloud.overcloud_keystone_client
overcloud_keystone_credentials = overcloud.overcloud_keystone_credentials
overcloud_keystone_session = overcloud.overcloud_keystone_session
overcloud_node_ip_address = overcloud.overcloud_node_ip_address
overcloud_ssh_client = overcloud.overcloud_ssh_client
overcloud_version = overcloud.overcloud_version
skip_if_missing_overcloud = overcloud.skip_if_missing_overcloud
skip_unless_has_overcloud = overcloud.skip_unless_has_overcloud
get_overcloud_ssh_username = overcloud.get_overcloud_ssh_username
skip_if_ceph_rgw = containers.skip_if_ceph_rgw
get_container_runtime_name = containers.get_container_runtime_name

TripleoTopology = topology.TripleoTopology

UndercloudKeystoneCredentialsFixture = \
    undercloud.UndercloudKeystoneCredentialsFixture
UndercloudCloudsFileKeystoneCredentialsFixture = \
    undercloud.UndercloudCloudsFileKeystoneCredentialsFixture
fetch_os_env = undercloud.fetch_os_env
load_undercloud_rcfile = undercloud.load_undercloud_rcfile
has_undercloud = undercloud.has_undercloud
skip_unless_has_undercloud = undercloud.skip_unlsess_has_undercloud
skip_if_missing_undercloud = undercloud.skip_if_missing_undercloud
undercloud_host_config = undercloud.undercloud_host_config
undercloud_keystone_client = undercloud.undercloud_keystone_client
undercloud_keystone_credentials = undercloud.undercloud_keystone_credentials
undercloud_keystone_session = undercloud.undercloud_keystone_session
undercloud_ssh_client = undercloud.undercloud_ssh_client
undercloud_version = undercloud.undercloud_version

get_overcloud_nodes_running_service = \
    services.get_overcloud_nodes_running_service
