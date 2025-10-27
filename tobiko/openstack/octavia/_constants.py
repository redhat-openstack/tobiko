# Copyright (c) 2021 Red Hat
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

# Octavia attributes
PROVISIONING_STATUS = 'provisioning_status'
OPERATING_STATUS = 'operating_status'

# Octavia provisioning and operating status
ACTIVE = 'ACTIVE'
ERROR = 'ERROR'
PENDING_UPDATE = 'PENDING_UPDATE'
ONLINE = 'ONLINE'
DEGRADED = 'DEGRADED'

# Octavia protocols
PROTOCOL_HTTP = 'HTTP'
PROTOCOL_TCP = 'TCP'

# Octavia lb algorithms
LB_ALGORITHM_ROUND_ROBIN = 'ROUND_ROBIN'
LB_ALGORITHM_SOURCE_IP_PORT = 'SOURCE_IP_PORT'

# Octavia providers
AMPHORA_PROVIDER = 'amphora'
OVN_PROVIDER = 'ovn'

# Octavia services
WORKER_SERVICE = 'tripleo_octavia_worker.service'
HOUSEKEEPING_SERVICE = 'tripleo_octavia_housekeeping.service'
HM_SERVICE = 'tripleo_octavia_health_manager.service'
API_SERVICE = 'tripleo_octavia_api.service'

# Octavia containers
WORKER_CONTAINER = 'octavia_worker'
HOUSEKEEPING_CONTAINER = 'octavia_housekeeping'
HM_CONTAINER = 'octavia_health_manager'
API_CONTAINER = 'octavia_api'

# Octavia amphora provider resources names
LB_AMP_NAME = 'tobiko_octavia_amphora_lb'
LISTENER_AMP_NAME = 'tobiko_octavia_http_listener'
POOL_AMP_NAME = 'tobiko_octavia_http_pool'
MEMBER_AMP_NAME_PREFIX = 'tobiko_octavia_http_member'
HM_AMP_NAME = 'tobiko_octavia_amphora_hm'

# Octavia ovn provider resources names
LB_OVN_NAME = 'tobiko_octavia_ovn_lb'
LISTENER_OVN_NAME = 'tobiko_octavia_tcp_listener'
POOL_OVN_NAME = 'tobiko_octavia_tcp_pool'
MEMBER_OVN_NAME_PREFIX = 'tobiko_octavia_tcp_member'
HM_OVN_NAME = 'tobiko_octavia_ovn_hm'

# Providers/lb-names dictionary
OCTAVIA_PROVIDERS_NAMES = {
    'lb': {
        AMPHORA_PROVIDER: LB_AMP_NAME,
        OVN_PROVIDER: LB_OVN_NAME,
    },
    'listener': {
        AMPHORA_PROVIDER: LISTENER_AMP_NAME,
        OVN_PROVIDER: LISTENER_OVN_NAME,
    },
    'pool': {
        AMPHORA_PROVIDER: POOL_AMP_NAME,
        OVN_PROVIDER: POOL_OVN_NAME,
    },
    'member': {
        AMPHORA_PROVIDER: MEMBER_AMP_NAME_PREFIX,
        OVN_PROVIDER: MEMBER_OVN_NAME_PREFIX,
    },
    'healthmonitor': {
        AMPHORA_PROVIDER: HM_AMP_NAME,
        OVN_PROVIDER: HM_OVN_NAME,
    }
}
