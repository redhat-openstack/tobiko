# Copyright 2023 Red Hat
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

from tobiko.openstack.manila import _client
from tobiko.openstack.manila import _constants
from tobiko.openstack.manila import _exceptions
from tobiko.openstack.manila import _waiters

manila_client = _client.manila_client
get_manila_client = _client.get_manila_client
ManilaClientFixture = _client.ManilaClientFixture
create_share = _client.create_share
get_share = _client.get_share
get_shares_by_name = _client.get_shares_by_name
delete_share = _client.delete_share
extend_share = _client.extend_share
list_shares = _client.list_shares
ensure_default_share_type_exists = _client.ensure_default_share_type_exists

# Waiters
wait_for_share_status = _waiters.wait_for_share_status
wait_for_resource_deletion = _waiters.wait_for_resource_deletion

# Exceptions
ShareNotFound = _exceptions.ShareNotFound
ShareReleaseFailed = _exceptions.ShareReleaseFailed

# Constants
RESOURCE_STATUS = _constants.RESOURCE_STATUS
STATUS_AVAILABLE = _constants.STATUS_AVAILABLE
STATUS_ERROR = _constants.STATUS_ERROR
STATUS_ERROR_DELETING = _constants.STATUS_ERROR_DELETING
SHARE_NAME = _constants.SHARE_NAME
