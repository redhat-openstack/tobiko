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

import typing
import time

from oslo_log import log
from manilaclient import exceptions

import tobiko
from tobiko.openstack.manila import _client
from tobiko.openstack.manila import _constants
from tobiko.openstack.manila import _exceptions

LOG = log.getLogger(__name__)


def wait_for_status(object_id: str,
                    status_key: str = _constants.RESOURCE_STATUS,
                    status: str = _constants.STATUS_AVAILABLE,
                    get_client: typing.Callable = None,
                    interval: tobiko.Seconds = None,
                    timeout: tobiko.Seconds = None,
                    **kwargs):
    """Waits for an object to reach a specific status.

    :param status_key: The key of the status field in the response.
                       Ex. status
    :param status: The status to wait for. Ex. "ACTIVE"
    :param get_client: The tobiko client get method.
                        Ex. _client.get_zone
    :param object_id: The id of the object to query.
    :param interval: How often to check the status, in seconds.
    :param timeout: The maximum time, in seconds, to check the status.
    :raises TimeoutException: The object did not achieve the status or ERROR in
                              the check_timeout period.
    :raises UnexpectedStatusException: The request returned an unexpected
                                       response code.
    """

    get_client = get_client or _client.get_share

    for attempt in tobiko.retry(timeout=timeout,
                                interval=interval,
                                default_timeout=300.,
                                default_interval=5.):
        response = get_client(object_id, **kwargs)
        if response[status_key] == status:
            return response

        attempt.check_limits()

        LOG.debug(f"Waiting for {get_client.__name__} {status_key} to get "
                  f"from '{response[status_key]}' to '{status}'...")


def wait_for_share_status(share_id):
    wait_for_status(object_id=share_id)


def _is_share_deleted(share_id):
    try:
        res = _client.get_share(share_id)
    except _exceptions.ShareNotFound:
        return True
    if res.get(_constants.RESOURCE_STATUS) in [
            _constants.STATUS_ERROR, _constants.STATUS_ERROR_DELETING]:
        # Share has "error_deleting" status and can not be deleted.
        raise _exceptions.ShareReleaseFailed(id=share_id)
    return False


def wait_for_resource_deletion(share_id, build_interval=1, build_timeout=60):
    """Waits for a resource to be deleted."""
    start_time = int(time.time())
    while True:
        if _is_share_deleted(share_id):
            return
        if int(time.time()) - start_time >= build_timeout:
            raise exceptions.TimeoutException
        time.sleep(build_interval)
