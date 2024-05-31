from __future__ import absolute_import

import functools
import os
import time
import typing

from oslo_log import log
import pandas

import tobiko
from tobiko import config
from tobiko.openstack import neutron
from tobiko.openstack import topology
from tobiko import rhosp as rhosp_topology
from tobiko.rhosp import containers as rhosp_containers


CONF = config.CONF
LOG = log.getLogger(__name__)


class ContainerRuntimeFixture(tobiko.SharedFixture):

    runtime: typing.Optional[rhosp_containers.ContainerRuntime] = None

    def setup_fixture(self):
        self.runtime = self.get_runtime()

    def cleanup_fixture(self):
        self.runtime = None

    @staticmethod
    def get_runtime() -> typing.Optional[rhosp_containers.ContainerRuntime]:
        """return handle to the container runtime"""
        return rhosp_containers.PODMAN_RUNTIME


def get_container_runtime() -> rhosp_containers.ContainerRuntime:
    runtime = tobiko.setup_fixture(ContainerRuntimeFixture).runtime
    return runtime


def get_container_runtime_name() -> str:
    return get_container_runtime().runtime_name


def is_docker() -> bool:
    return False


def is_podman() -> bool:
    return True


def has_container_runtime() -> bool:
    return True


@functools.lru_cache()
def list_node_containers(ssh_client):
    """returns a list of containers and their run state"""
    return get_container_runtime().list_containers(ssh_client=ssh_client)


def get_container_client(ssh_client=None):
    """returns a list of containers and their run state"""
    return get_container_runtime().get_client(ssh_client=ssh_client)


def list_containers_df(group=None):
    actual_containers_list = list_containers(group)
    return pandas.DataFrame(
        get_container_states_list(actual_containers_list),
        columns=['container_host', 'container_name', 'container_state'])


def list_containers(group=None):
    """get list of containers in running state
    from specified node group
    returns : a list of overcloud_node's running containers"""

    # moved here from topology
    # reason : Workaround for :
    # AttributeError: module 'tobiko.openstack.topology' has no
    # attribute 'container_runtime'

    if group is None:
        group = 'compute'
    containers_list = tobiko.Selection()
    openstack_nodes = topology.list_openstack_nodes(group=group)

    for node in openstack_nodes:
        LOG.debug(f"List containers for node {node.name}")
        node_containers_list = list_node_containers(ssh_client=node.ssh_client)
        containers_list.extend(node_containers_list)
    return containers_list


def assert_containers_running(group, expected_containers, full_name=True,
                              bool_check=False, nodenames=None):

    """assert that all containers specified in the list are running
    on the specified openstack group(controller or compute etc..)
    if bool_check is True then return only True or false without failing"""

    if is_docker():
        LOG.info('not checking common containers since we are on docker')
        return

    failures = []

    openstack_nodes = topology.list_openstack_nodes(group=group,
                                                    hostnames=nodenames)
    for node in openstack_nodes:
        node_containers = list_node_containers(ssh_client=node.ssh_client)
        containers_list_df = pandas.DataFrame(
            get_container_states_list(node_containers),
            columns=['container_host', 'container_name', 'container_state'])
        # check that the containers are present
        LOG.info('node: {} containers list : {}'.format(
            node.name, containers_list_df.to_string(index=False)))
        for container in expected_containers:
            # get container attrs dataframe
            if full_name:
                container_attrs = containers_list_df.query(
                    'container_name == "{}"'.format(container))
            else:
                container_attrs = containers_list_df[
                    containers_list_df['container_name'].
                    str.contains(container)]
            # check if the container exists
            LOG.info('checking container: {}'.format(container))
            if container_attrs.empty:
                failures.append(
                    'expected container {} not found on node {} ! : \n\n'.
                    format(container, node.name))
            # if container exists, check it is running
            else:
                # only one running container is expected
                container_running_attrs = container_attrs.query(
                    'container_state=="running"')
                if container_running_attrs.empty:
                    failures.append(
                        'expected container {} is not running on node {} , '
                        'its state is {}! : \n\n'.format(
                            container, node.name,
                            container_attrs.container_state.values.item()))
                elif len(container_running_attrs) > 1:
                    failures.append(
                        'only one running container {} was expected on '
                        'node {}, but got {}! : \n\n'.format(
                            container, node.name,
                            len(container_running_attrs)))

    if not bool_check and failures:
        tobiko.fail(
            'container states mismatched:\n{}'.format('\n'.join(failures)),
            rhosp_containers.ContainerMismatchException)

    elif bool_check and failures:
        return False

    else:
        LOG.info('All specified containers are in running state! ')
        return True


def assert_ovn_containers_running():
    if not neutron.has_ovn():
        LOG.info("Networking OVN not configured")
        return
    ovn_containers = ['ovn_metadata_agent',
                      'ovn_controller']
    potential_groups = ['edpm-compute', 'edpm-networker']
    groups = [group for group in potential_groups if
              group in topology.get_openstack_topology().groups]
    for group in groups:
        assert_containers_running(group, ovn_containers, full_name=False)
    LOG.info("Networking OVN containers verified in running state")


def get_container_states_list(containers_list,
                              include_container_objects=False):
    container_states_list = tobiko.Selection()
    container_states_list.extend([comparable_container_keys(
        container, include_container_objects=include_container_objects) for
                                  container in containers_list])
    return container_states_list


def save_containers_state_to_file(expected_containers_list,):
    expected_containers_list_df = pandas.DataFrame(
        get_container_states_list(expected_containers_list),
        columns=['container_host', 'container_name', 'container_state'])
    expected_containers_list_df.to_csv(
        rhosp_containers.expected_containers_file)
    return rhosp_containers.expected_containers_file


def comparable_container_keys(container, include_container_objects=False):
    """returns the tuple : 'container_host','container_name',
    'container_state, container object if specified'
     """
    host_or_ip = container.client.base_url.netloc.rsplit('_')[1]
    nodes_matching = topology.list_openstack_nodes(hostnames=[host_or_ip])
    nodename = (nodes_matching[0].name
                if nodes_matching
                else rhosp_topology.ip_to_hostname(host_or_ip))

    # Differenciate between podman_ver3 with podman-py from earlier api
    if include_container_objects:
        return (nodename,
                container.attrs['Names'][0], container.attrs['State'],
                container)
    else:
        return (nodename,
                container.attrs['Names'][0],
                container.attrs['State'])


@functools.lru_cache()
def list_containers_objects_df():
    containers_list = list_containers()
    containers_objects_list_df = pandas.DataFrame(
        get_container_states_list(
            containers_list, include_container_objects=True),
        columns=['container_host', 'container_name',
                 'container_state', 'container_object'])
    return containers_objects_list_df


def get_edpm_container(container_name=None, container_host=None,
                       partial_container_name=None):
    """gets an container object by name on specified host
    container"""
    con_obj_df = list_containers_objects_df()
    if partial_container_name and container_host:
        con_obj_df = con_obj_df[con_obj_df['container_name'].str.contains(
            partial_container_name)]
        contaniner_obj = con_obj_df.query(
            'container_host == "{container_host}"'.format(
                container_host=container_host))['container_object']
    elif container_host:
        contaniner_obj = con_obj_df.query(
            'container_name == "{container_name}"'
            ' and container_host == "{container_host}"'.
            format(container_host=container_host,
                   container_name=container_name)).container_object
    else:
        contaniner_obj = con_obj_df.query(
            'container_name == "{container_name}"'.
            format(container_name=container_name)).container_object
    if not contaniner_obj.empty:
        return contaniner_obj.values[0]
    else:
        tobiko.fail('container {} not found!'.format(container_name))


def action_on_container(action: str,
                        container_name=None,
                        container_host=None,
                        partial_container_name=None):
    """take a container and perform an action on it
    actions are as defined in : podman/libs/containers.py:14/164"""

    LOG.debug(f"Executing '{action}' action on container "
              f"'{container_name}@{container_host}'...")
    container = get_edpm_container(
        container_name=container_name,
        container_host=container_host,
        partial_container_name=partial_container_name)

    container_class: typing.Type = type(container)
    # we get the specified action as function from podman lib
    action_method: typing.Optional[typing.Callable] = getattr(
        container_class, action, None)
    if action_method is None:
        raise TypeError(f"Unsupported container action for class :"
                        f" {container_class}")
    if not callable(action_method):
        raise TypeError(
            f"Attribute '{container_class.__qualname__}.{action}' value "
            f" is not a method: {action_method!r}")
    LOG.debug(f"Calling '{action_method}' action on container "
              f"'{container}'")
    return action_method(container)


def assert_equal_containers_state(expected_containers_list=None,
                                  timeout=120, interval=2,
                                  recreate_expected=False):

    """compare all edpm container states with using two lists:
    one is current , the other some past list
    first time this method runs it creates a file holding overcloud
    containers' states: ~/expected_containers_list_df.csv'
    second time it creates a current containers states list and
    compares them, they must be identical"""

    expected_containers_list_df = []
    # if we have a file or an explicit variable use that , otherwise  create
    # and return
    if recreate_expected or (
            not expected_containers_list and
            not os.path.exists(rhosp_containers.expected_containers_file)):
        save_containers_state_to_file(list_containers())
        return

    elif expected_containers_list:
        expected_containers_list_df = pandas.DataFrame(
            get_container_states_list(expected_containers_list),
            columns=['container_host', 'container_name', 'container_state'])

    elif os.path.exists(rhosp_containers.expected_containers_file):
        expected_containers_list_df = pandas.read_csv(
            rhosp_containers.expected_containers_file)

    failures = []
    start = time.time()
    error_info = 'Output explanation: left_only is the original state, ' \
                 'right_only is the new state'

    while time.time() - start < timeout:

        failures = []
        actual_containers_list_df = list_containers_df()

        LOG.info('expected_containers_list_df: {} '.format(
            expected_containers_list_df.to_string(index=False)))
        LOG.info('actual_containers_list_df: {} '.format(
            actual_containers_list_df.to_string(index=False)))

        # execute a `dataframe` diff between the expected and actual containers
        expected_containers_state_changed = \
            rhosp_containers.dataframe_difference(
                    expected_containers_list_df,
                    actual_containers_list_df)
        # check for changed state containerstopology
        if not expected_containers_state_changed.empty:
            failures.append('expected containers changed state ! : '
                            '\n\n{}\n{}'.format(
                             expected_containers_state_changed.
                             to_string(index=False), error_info))
            LOG.info('container states mismatched:\n{}\n'.format(failures))
            time.sleep(interval)
            # clear cache to obtain new data
            list_node_containers.cache_clear()
        else:
            LOG.info("assert_equal_containers_state :"
                     " OK, all containers are on the same state")
            return
    if failures:
        tobiko.fail('container states mismatched:\n{!s}', '\n'.join(
            failures))
