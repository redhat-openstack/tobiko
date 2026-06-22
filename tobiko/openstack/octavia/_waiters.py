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
from tobiko import config
from tobiko.openstack import octavia, openstacksdkclient, topology
from tobiko.openstack.octavia import _client
from tobiko.openstack.octavia import _constants
from tobiko.shell import sh
from tobiko.tripleo import containers

get_load_balancer = _client.get_load_balancer

LOG = log.getLogger(__name__)

CONF = config.CONF


def _has_ipv6_vip(lb: typing.Any) -> bool:
    return _client.find_ipv6_vip_on_load_balancer(lb) is not None


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


def wait_for_load_balancer(
        lb_id: str,
        ready: typing.Callable[[typing.Any], bool],
        get_client: typing.Callable = None,
        interval: tobiko.Seconds = None,
        timeout: tobiko.Seconds = None,
        waiting_log: typing.Callable[[], str] = None) -> typing.Any:
    """Wait until ``ready(load_balancer)`` returns True.

    Uses the same retry defaults as :func:`wait_for_status`.
    """
    get_client = get_client or get_load_balancer
    for attempt in tobiko.retry(timeout=timeout,
                                interval=interval,
                                default_timeout=(
                                        CONF.tobiko.octavia.check_timeout),
                                default_interval=(
                                        CONF.tobiko.octavia.check_interval)):
        lb = get_client(lb_id)
        if ready(lb):
            return lb
        if waiting_log:
            LOG.debug(waiting_log())
        else:
            LOG.debug('Waiting for load balancer %s...', lb_id)
        attempt.check_limits()


def wait_for_ipv6_additional_vip(lb_id: str) -> typing.Optional[typing.Any]:
    """Wait until the load balancer has an allocated IPv6 additional VIP.

    :returns: Load balancer when an IPv6 ``additional_vips`` address exists,
        or ``None`` if the timeout is reached (caller should fail the test).
    """
    try:
        return wait_for_load_balancer(
            lb_id,
            ready=_has_ipv6_vip,
            waiting_log=lambda: (
                'Waiting for IPv6 additional VIP on load balancer %s...'
                % lb_id),
        )
    except tobiko.RetryTimeLimitError:
        timeout = CONF.tobiko.octavia.check_timeout
        lb = get_load_balancer(lb_id)
        LOG.warning(
            'IPv6 additional VIP not allocated on load balancer %s after %ss; '
            'additional_vips=%r provisioning_status=%s vip_address=%s',
            lb_id,
            timeout,
            getattr(lb, 'additional_vips', None),
            getattr(lb, 'provisioning_status', None),
            getattr(lb, 'vip_address', None),
        )
        return None


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


def _get_ovn_sb_connection(controller_ssh_client):
    """Get OVN Southbound database connection string

    Tries multiple methods to obtain the connection:
    1. From octavia.conf [ovn] section using topology infrastructure
    2. From ovs-vsctl as fallback (for environments without config file)

    :param controller_ssh_client: SSH client to controller node
    :return: OVN SB connection string or None if cannot be determined
    """
    # Method 1: Try to get from octavia.conf using topology
    try:
        sb_connection = topology.get_config_setting(
            file_name='octavia.conf',
            ssh_client=controller_ssh_client,
            param='ovn_sb_connection',
            section='ovn')
        if sb_connection:
            LOG.debug("Found OVN SB connection from octavia.conf")
            return sb_connection
    except Exception as e:
        LOG.debug(f"Could not read from octavia.conf: {e}")

    # Method 2: Try ovs-vsctl as fallback
    try:
        LOG.debug("Trying ovs-vsctl to get OVN SB connection")
        cmd = ("ovs-vsctl get open . external_ids:ovn-remote | "
               "sed 's/\"//g'")
        output = sh.execute(cmd, ssh_client=controller_ssh_client, sudo=True)
        connection = output.stdout.strip()
        if connection:
            LOG.debug("Found OVN SB connection using ovs-vsctl")
            return connection
    except sh.ShellCommandFailed as e:
        LOG.debug(f"ovs-vsctl method failed: {e}")

    LOG.debug("Could not determine OVN SB connection string")
    return None


def wait_for_ovn_service_monitor_status(
        member_ip: str,
        expected_status: str = 'online',
        protocol_port: int = 80,
        interval: tobiko.Seconds = None,
        timeout: tobiko.Seconds = None):
    """Wait for a specific OVN Service_Monitor to reach expected status

    This function queries the OVN Southbound database to check the status
    of a Service_Monitor entry for a specific member IP and port. It waits
    until that specific entry reaches the expected status.

    If OVN DB connection cannot be obtained, this function returns without
    verification (graceful degradation).

    :param member_ip: The IP address of the load balancer member
    :param expected_status: Expected status (online, offline, error, etc.)
    :param protocol_port: The protocol port of the load balancer member
    :param interval: How often to check the status, in seconds
    :param timeout: The maximum time to wait, in seconds
    :raises TimeoutException: If status doesn't match within timeout
    """
    try:
        current_topology = topology.get_openstack_topology()
        controller = topology.list_openstack_nodes(group='controller')[0]
    except Exception as ex:
        LOG.warning(
            f"Cannot get controller node to verify Service_Monitor status "
            f"for {member_ip}: {ex}. Skipping verification.")
        return

    # Get OVN SB connection string using multiple methods
    sb_connection = _get_ovn_sb_connection(controller.ssh_client)
    if sb_connection is None:
        LOG.warning(
            f"Cannot get OVN SB connection string to verify Service_Monitor "
            f"status for {member_ip}. Skipping verification.")
        return

    # Build the ovn-sbctl command to query the specific Service_Monitor
    # Filter by ip=member_ip AND port=protocol_port
    # TODO(froyo): When OVN schema 26.x is the minimum supported version,
    # add type=load-balancer to the filter for more precise matching:
    # find Service_Monitor type=load-balancer ip={member_ip} port={port}
    ovn_sbctl_cmd = (
        f'ovn-sbctl --db={sb_connection} --format=csv --no-headings '
        f'--data=bare --columns=status '
        f'find Service_Monitor ip={member_ip} port={protocol_port}'
    )

    # Wrap command for containerized or direct execution
    if current_topology.has_containers:
        runtime_name = containers.get_container_runtime_name()
        cmd = f'{runtime_name} exec ovn_controller {ovn_sbctl_cmd}'
        LOG.debug("Using containerized ovn-sbctl command")
    else:
        cmd = ovn_sbctl_cmd
        LOG.debug("Using direct ovn-sbctl command")

    for attempt in tobiko.retry(
            timeout=timeout,
            interval=interval,
            default_timeout=360.,
            default_interval=5.):

        output = sh.execute(cmd, ssh_client=controller.ssh_client, sudo=True)
        status = output.stdout.strip()

        if not status:
            LOG.debug(
                f"No Service_Monitor found for member IP {member_ip} yet, "
                "waiting...")
            attempt.check_limits()
            continue

        # Check if status matches expected
        if status == expected_status:
            LOG.info(
                f"Service_Monitor for {member_ip} has expected status: "
                f"{status}")
            return

        LOG.debug(
            f"Waiting for Service_Monitor {member_ip} to reach "
            f"'{expected_status}' - Current: '{status}'")
        attempt.check_limits()
