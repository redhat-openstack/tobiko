# Copyright 2019 Red Hat
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

from tobiko.openstack.octavia import _amphora
from tobiko.openstack.octavia import _deployers
from tobiko.openstack.octavia import _client
from tobiko.openstack.octavia import _constants
from tobiko.openstack.octavia import _exceptions
from tobiko.openstack.octavia import _validators
from tobiko.openstack.octavia import _waiters

AmphoraIdType = _amphora.AmphoraIdType
AmphoraType = _amphora.AmphoraType
get_amphora_compute_node = _amphora.get_amphora_compute_node
get_master_amphora = _amphora.get_master_amphora
list_amphorae = _amphora.list_amphorae
get_amphora_stats = _amphora.get_amphora_stats
get_amphora = _amphora.get_amphora
run_command_on_amphora = _amphora.run_command_on_amphora

OCTAVIA_CLIENT_CLASSSES = _client.OCTAVIA_CLIENT_CLASSSES
get_octavia_client = _client.get_octavia_client
octavia_client = _client.octavia_client
OctaviaClientFixture = _client.OctaviaClientFixture
OctaviaClientType = _client.OctaviaClientType
list_members = _client.list_members
list_load_balancers = _client.list_load_balancers
find_load_balancer = _client.find_load_balancer
get_load_balancer = _client.get_load_balancer
create_load_balancer = _client.create_load_balancer
find_listener = _client.find_listener
create_listener = _client.create_listener
find_pool = _client.find_pool
create_pool = _client.create_pool
find_member = _client.find_member
create_member = _client.create_member
create_health_monitor = _client.create_health_monitor
find_health_monitor = _client.find_health_monitor
get_health_monitor = _client.get_health_monitor

# Waiters
wait_for_status = _waiters.wait_for_status
wait_for_octavia_service = _waiters.wait_for_octavia_service

# Validators
check_members_balanced = _validators.check_members_balanced

# Exceptions
RequestException = _exceptions.RequestException
TimeoutException = _exceptions.TimeoutException
OctaviaClientException = _exceptions.OctaviaClientException
RoundRobinException = _exceptions.RoundRobinException
TrafficTimeoutError = _exceptions.TrafficTimeoutError
AmphoraMgmtPortNotFound = _exceptions.AmphoraMgmtPortNotFound

# Constants
PROVISIONING_STATUS = _constants.PROVISIONING_STATUS
OPERATING_STATUS = _constants.OPERATING_STATUS
ACTIVE = _constants.ACTIVE
ERROR = _constants.ERROR
PENDING_UPDATE = _constants.PENDING_UPDATE
ONLINE = _constants.ONLINE
DEGRADED = _constants.DEGRADED
PROTOCOL_HTTP = _constants.PROTOCOL_HTTP
PROTOCOL_TCP = _constants.PROTOCOL_TCP
LB_ALGORITHM_ROUND_ROBIN = _constants.LB_ALGORITHM_ROUND_ROBIN
LB_ALGORITHM_SOURCE_IP_PORT = _constants.LB_ALGORITHM_SOURCE_IP_PORT
AMPHORA_PROVIDER = _constants.AMPHORA_PROVIDER
OVN_PROVIDER = _constants.OVN_PROVIDER
OCTAVIA_PROVIDERS_NAMES = _constants.OCTAVIA_PROVIDERS_NAMES
WORKER_SERVICE = _constants.WORKER_SERVICE
HOUSEKEEPING_SERVICE = _constants.HOUSEKEEPING_SERVICE
HM_SERVICE = _constants.HM_SERVICE
API_SERVICE = _constants.API_SERVICE
WORKER_CONTAINER = _constants.WORKER_CONTAINER
HOUSEKEEPING_CONTAINER = _constants.HOUSEKEEPING_CONTAINER
HM_CONTAINER = _constants.HM_CONTAINER
API_CONTAINER = _constants.API_CONTAINER
OCTAVIA_SERVICES = [WORKER_SERVICE, HOUSEKEEPING_SERVICE, HM_SERVICE,
                    API_SERVICE]
OCTAVIA_CONTAINERS = [WORKER_CONTAINER, HOUSEKEEPING_CONTAINER, HM_CONTAINER,
                      API_CONTAINER]
LB_AMP_NAME = _constants.LB_AMP_NAME
LISTENER_AMP_NAME = _constants.LISTENER_AMP_NAME
POOL_AMP_NAME = _constants.POOL_AMP_NAME
MEMBER_AMP_NAME_PREFIX = _constants.MEMBER_AMP_NAME_PREFIX
HM_AMP_NAME = _constants.HM_AMP_NAME

LB_OVN_NAME = _constants.LB_OVN_NAME
LISTENER_OVN_NAME = _constants.LISTENER_OVN_NAME
POOL_OVN_NAME = _constants.POOL_OVN_NAME
MEMBER_OVN_NAME_PREFIX = _constants.MEMBER_OVN_NAME_PREFIX
HM_OVN_NAME = _constants.HM_OVN_NAME

# Deployers
deploy_ipv4_amphora_lb = _deployers.deploy_ipv4_amphora_lb
deploy_ipv4_ovn_lb = _deployers.deploy_ipv4_ovn_lb
deploy_hm = _deployers.deploy_hm
