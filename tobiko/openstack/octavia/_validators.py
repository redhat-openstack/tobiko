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

import collections
import typing

from oslo_log import log

import tobiko
from tobiko.openstack import octavia
from tobiko.shell import curl
from tobiko.shell import ssh
from tobiko.shell import sh


LOG = log.getLogger(__name__)


def check_members_balanced(ip_address: str,
                           protocol: str,
                           port: int,
                           pool_id: str = None,
                           members_count: int = None,
                           lb_algorithm: str = None,
                           requests_count: int = 10,
                           connect_timeout: tobiko.Seconds = 10.,
                           interval: tobiko.Seconds = 1,
                           ssh_client: ssh.SSHClientFixture = None) -> (
        typing.Dict[str, int]):

    """Check if traffic is properly balanced between members."""

    # Getting the members count
    if members_count is None:
        if pool_id is None:
            raise ValueError('Either members_count or pool_id has to be passed'
                             ' to the function.')

        else:  # members_count is None and pool_id is not None
            members_count = len(list(octavia.list_members(pool_id=pool_id)))

    last_content = None
    replies: typing.Dict[str, int] = collections.defaultdict(lambda: 0)
    for attempt in tobiko.retry(count=members_count * requests_count,
                                interval=interval):
        try:
            content = curl.execute_curl(
                hostname=ip_address,
                scheme='HTTP' if protocol == 'TCP' else protocol,
                port=port,
                path='id',
                connect_timeout=connect_timeout,
                ssh_client=ssh_client).strip()
        except sh.ShellCommandFailed as ex:
            if ex.exit_status == 28:
                raise octavia.TrafficTimeoutError(
                    reason=str(ex.stderr)) from ex
            else:
                raise ex

        replies[content] += 1

        if last_content is not None and lb_algorithm == 'ROUND_ROBIN':
            if members_count > 1 and last_content == content:
                raise octavia.RoundRobinException(
                    'Request was forwarded two times to the same host:\n'
                    f'members_count: {members_count}\n'
                    f'expected: {last_content}\n'
                    f'actual: {content}\n')

        last_content = content

        if attempt.is_last:
            break
    else:
        raise RuntimeError('Broken retry loop')

    LOG.debug(f"Replies counts from load balancer: {replies}")

    # assert that 'members_count' servers replied
    missing_members_count = members_count - len(replies)
    LOG.debug(f'Members count from pool {pool_id} is {members_count}')
    LOG.debug(f'len(replies) is {len(replies)}')

    if 0 != missing_members_count:
        raise octavia.RoundRobinException(
            f'Missing replies from {missing_members_count} members.')

    return replies


def verify_lb_traffic(pool_id: str,
                      ip_address: str,
                      lb_algorithm: str,
                      protocol: str,
                      port: int,
                      timeout: tobiko.Seconds = 300.,
                      members_count: int = None,
                      requests_count: int = 10,
                      connect_timeout: tobiko.Seconds = 10.,
                      interval: tobiko.Seconds = 1,
                      ssh_client: ssh.SSHClientFixture = None,
                      exceptions: tuple = None):
    """Verify load balancer traffic with retries.

    This function attempts to verify that traffic is properly balanced to
    all members of a load balancer pool, retrying on expected exceptions
    during resource provisioning or service disruption.

    Raises:
        The last exception caught if all retries are exhausted

    Returns:
        Dict mapping member addresses to request counts
    """
    if exceptions is None:
        exceptions = (octavia.RoundRobinException,
                      octavia.TrafficTimeoutError,
                      sh.ShellCommandFailed,
                      octavia.OctaviaClientException)

    for attempt in tobiko.retry(timeout=timeout):
        try:
            return check_members_balanced(
                pool_id=pool_id,
                ip_address=ip_address,
                lb_algorithm=lb_algorithm,
                protocol=protocol,
                port=port,
                members_count=members_count,
                requests_count=requests_count,
                connect_timeout=connect_timeout,
                interval=interval,
                ssh_client=ssh_client)
        except exceptions:
            LOG.exception(
                f"Traffic verification failed after #{attempt.number} "
                f"attempts and {attempt.elapsed_time} seconds")
            if attempt.is_last:
                raise
