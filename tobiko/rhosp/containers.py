from __future__ import absolute_import

import abc
import os
import re
import typing

from oslo_log import log

import tobiko
from tobiko.openstack import topology
from tobiko import podman
from tobiko import docker
from tobiko.shell import ssh


LOG = log.getLogger(__name__)


expected_containers_file = os.path.expanduser(
    '~/expected_containers_list_df.csv')


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
                LOG.debug('Unable to connect to docker server',
                          exc_info=1)
                ssh.reset_default_ssh_port_forward_manager()
        else:
            raise RuntimeError("Broken retry loop")
        return client

    def _get_client(self, ssh_client):
        raise NotImplementedError

    def list_containers(self, ssh_client):
        raise NotImplementedError


class DockerContainerRuntime(ContainerRuntime):
    runtime_name = 'docker'
    version_pattern = re.compile('Docker version .*', re.IGNORECASE)

    def _get_client(self, ssh_client):
        return docker.get_docker_client(ssh_client=ssh_client,
                                        sudo=True).connect()

    def list_containers(self, ssh_client):
        client = self.get_client(ssh_client=ssh_client)
        return docker.list_docker_containers(client=client)


class PodmanContainerRuntime(ContainerRuntime):
    runtime_name = 'podman'
    version_pattern = re.compile('Podman version .*', re.IGNORECASE)

    def _get_client(self, ssh_client):
        return podman.get_podman_client(ssh_client=ssh_client).connect()

    def list_containers(self, ssh_client):
        client = self.get_client(ssh_client=ssh_client)
        return podman.list_podman_containers(client=client)


DOCKER_RUNTIME = DockerContainerRuntime()
PODMAN_RUNTIME = PodmanContainerRuntime()
CONTAINER_RUNTIMES = [PODMAN_RUNTIME, DOCKER_RUNTIME]


class ContainerMismatchException(tobiko.TobikoException):
    pass


def remove_containers_from_comparison(comparable_containers_df):
    """remove any containers if comparing them with previous status is not
    necessary or makes no sense
    """
    os_topology = topology.get_openstack_topology()
    for row in comparable_containers_df.iterrows():
        for ignore_container in os_topology.ignore_containers_list:
            if ignore_container in str(row):
                LOG.info(f'container {ignore_container} has changed state, '
                         'but that\'s ok - it will be ignored and the test '
                         f'will not fail due to this: {str(row)}')
                # if a pcs resource is found , we drop that row
                comparable_containers_df.drop(row[0], inplace=True)
                # this row was already dropped, go to next row
                break


def dataframe_difference(df1, df2, which=None):
    """Find rows which are different between two DataFrames."""
    comparison_df = df1.merge(df2,
                              indicator='same_state',
                              how='outer')
    # return only non identical rows
    if which is None:
        diff_df = comparison_df[comparison_df['same_state'] != 'both']

    else:
        diff_df = comparison_df[comparison_df['same_state'] == which]

    # if the list of different state containers includes sidecar containers,
    # ignore them because the existence of these containers depends on the
    # created resources
    # if the list of different state containers includes pacemaker resources,
    # ignore them since the sanity and fault tests check pacemaker status too
    remove_containers_from_comparison(diff_df)

    return diff_df
