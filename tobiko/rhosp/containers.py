from __future__ import absolute_import

import abc
import os
import re
import typing

from oslo_log import log

import tobiko
from tobiko.openstack import topology
from tobiko import podman
from tobiko.shell import ssh


LOG = log.getLogger(__name__)


expected_containers_file = os.path.expanduser(
    '~/expected_containers_list_td.csv')


class ContainerRuntime(abc.ABC):
    runtime_name: str
    version_pattern: typing.Pattern

    def match_version(self, version: str) -> bool:
        for version_line in version.splitlines():
            if self.version_pattern.match(version_line) is not None:
                return True
        return False

    def get_client(self, ssh_client):
        for attempt in tobiko.retry(timeout=60.0,
                                    interval=5.0):
            try:
                client = self._get_client(ssh_client=ssh_client)
                break
            # TODO chose a better exception type
            except Exception:
                if attempt.is_last:
                    raise
                LOG.debug(f'Unable to connect to {self.runtime_name} server',
                          exc_info=1)
                ssh.reset_default_ssh_port_forward_manager()
        else:
            raise RuntimeError("Broken retry loop")
        return client

    def _get_client(self, ssh_client):
        raise NotImplementedError

    def list_containers(self, ssh_client):
        raise NotImplementedError


# NOTE: only podman is supported, but we still maintian the base abstract class
# ContainerRuntime in case a different container runtime is supported in the
# future
class PodmanContainerRuntime(ContainerRuntime):
    runtime_name = 'podman'
    version_pattern = re.compile('Podman version .*', re.IGNORECASE)

    def _get_client(self, ssh_client):
        return podman.get_podman_client(ssh_client=ssh_client).connect()

    def list_containers(self, ssh_client):
        client = self.get_client(ssh_client=ssh_client)
        return podman.list_podman_containers(client=client)


PODMAN_RUNTIME = PodmanContainerRuntime()
CONTAINER_RUNTIMES = [PODMAN_RUNTIME]


class ContainerMismatchException(tobiko.TobikoException):
    pass


def remove_containers_from_comparison(comparable_containers_td):
    """remove any containers if comparing them with previous status is not
    necessary or makes no sense
    """
    final_td = tobiko.TableData()
    os_topology = topology.get_openstack_topology()

    for item in comparable_containers_td.data:
        add_this_item = True
        for ignore_container in os_topology.ignore_containers_list:
            if ignore_container in item['container_name']:
                LOG.info(f'container {ignore_container} has changed state, '
                         'but that\'s ok - it will be ignored and the test '
                         f'will not fail due to this: {item}')
                # if a pcs resource is found , we drop that row
                add_this_item = False
                # this row was already dropped, go to next row
                break
        if add_this_item:
            final_td.append(item)
    return final_td


def tabledata_difference(td1, td2, which=None):
    """Find rows which are different between two TableData objects."""
    # Check if schemas match
    if td1.schema != td2.schema:
        raise ValueError("TableData objects must have the same schema")

    # Convert rows to hashable format for comparison
    def row_to_hashable(row):
        return tuple(sorted(row.items()))

    # Create sets of hashable rows
    td1_rows = {row_to_hashable(row): row for row in td1.data}
    td2_rows = {row_to_hashable(row): row for row in td2.data}

    # Find common rows, left-only rows, and right-only rows
    common_keys = set(td1_rows.keys()) & set(td2_rows.keys())
    left_only_keys = set(td1_rows.keys()) - set(td2_rows.keys())
    right_only_keys = set(td2_rows.keys()) - set(td1_rows.keys())

    # Create result rows with indicator column
    result_rows = []

    # Add common rows
    for key in common_keys:
        row = td1_rows[key].copy()
        row['same_state'] = 'both'
        result_rows.append(row)

    # Add left-only rows
    for key in left_only_keys:
        row = td1_rows[key].copy()
        row['same_state'] = 'left_only'
        result_rows.append(row)

    # Add right-only rows
    for key in right_only_keys:
        row = td2_rows[key].copy()
        row['same_state'] = 'right_only'
        result_rows.append(row)

    # Create result TableData
    comparison_td = tobiko.TableData(result_rows)

    # Filter based on which parameter (similar to original function)
    if which is None:
        # Return only non-identical rows
        diff_td = tobiko.TableData([row for row in comparison_td.data
                                    if row['same_state'] != 'both'])
    else:
        # Return only rows with specified state
        diff_td = tobiko.TableData([row for row in comparison_td.data
                                    if row['same_state'] == which])

    # Apply the same filtering logic as the original function
    final_diff_td = remove_containers_from_comparison(diff_td)

    return final_diff_td
