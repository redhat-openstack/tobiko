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
from __future__ import absolute_import

import typing

from oslo_log import log

import tobiko
from tobiko.openstack import octavia, openstacksdkclient
from tobiko.openstack.octavia import _constants
from tobiko import config

LOG = log.getLogger(__name__)

CONF = config.CONF


def wait_for_status(object_id: str,
                    status_key: str = _constants.PROVISIONING_STATUS,
                    status: str = _constants.ACTIVE,
                    get_client: typing.Callable = None,
                    interval: tobiko.Seconds = None,
                    timeout: tobiko.Seconds = None, **kwargs):
    """Waits for an object to reach a specific status.

    :param object_id: The id of the object to query.
    :param status_key: The key of the status field in the response.
                       Ex. provisioning_status
    :param status: The status to wait for. Ex. "ACTIVE"
    :param get_client: The tobiko client get method.
                        Ex. _client.get_loadbalancer
    :param interval: How often to check the status, in seconds.
    :param timeout: The maximum time, in seconds, to check the status.
    :raises TimeoutException: The object did not achieve the status or ERROR in
                              the check_timeout period.
    :raises UnexpectedStatusException: The request returned an unexpected
                                       response code.
    """

    if not get_client:
        os_sdk_client = openstacksdkclient.openstacksdk_client()
        get_client = os_sdk_client.load_balancer.get_load_balancer

    for attempt in tobiko.retry(timeout=timeout,
                                interval=interval,
                                default_timeout=(
                                        CONF.tobiko.octavia.check_timeout),
                                default_interval=(
                                        CONF.tobiko.octavia.check_interval)):
        response = get_client(object_id, **kwargs)
        if response[status_key] == status:
            return response

        # it will raise tobiko.RetryTimeLimitError in case of timeout
        attempt.check_limits()

        LOG.debug(f"Waiting for {get_client.__name__} {status_key} to get "
                  f"from '{response[status_key]}' to '{status}'...")


def wait_for_octavia_service(interval: tobiko.Seconds = None,
                             timeout: tobiko.Seconds = None):
    for attempt in tobiko.retry(timeout=timeout,
                                interval=interval,
                                default_timeout=180.,
                                default_interval=3.):
        try:  # Call any Octavia API
            octavia.list_amphorae()
        except octavia.OctaviaClientException as ex:
            LOG.debug(f"Error listing amphorae: {ex}")
            if attempt.is_last:
                raise
            LOG.info('Waiting for the LB to become functional again...')
        else:
            LOG.info('Octavia service is available!')
            break
