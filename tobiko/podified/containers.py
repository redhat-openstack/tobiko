from __future__ import absolute_import

import functools
import os
import typing

from oslo_log import log

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


def list_containers_td(group=None):
    actual_containers_list = list_containers(group)
    return tobiko.TableData(
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


def _select_container(
        container_itr: typing.Union[str, typing.Iterable[str]],
        full_name,
        node_name,
        containers_list_td,
) -> typing.Tuple[typing.Optional[str], tobiko.TableData, list]:
    """Return the status of a single container if present"""
    _name, _attrs, _fail = None, tobiko.TableData(), []
    if isinstance(container_itr, str):
        container_itr = [container_itr]

    # Get selected container attrs tabledata.
    for _name in container_itr:
        if full_name:
            _attrs = containers_list_td.query(
                'container_name == "{}"'.format(_name))
        else:
            container_attrs_rows = []
            for row in containers_list_td:
                if _name in row['container_name']:
                    container_attrs_rows.append(row)
            _attrs = tobiko.TableData(container_attrs_rows)
        if _attrs.empty:
            _fail.append(
                'expected container {} not found on node {} ! : \n\n'.
                format(_name, node_name))
        else:
            break

    return _name, _attrs, _fail


def assert_containers_running(
        group: topology.OpenstackGroupNamesType,
        expected_containers: typing.Iterable[
            typing.Union[str, typing.Iterable[str]]],
        full_name: bool = True,
        bool_check: bool = False,
        nodenames: typing.Iterable[str] = None,
) -> typing.Union[None, bool]:
    """assert that all containers specified in the list are running
    on the specified openstack group(controller or compute etc..)
    if bool_check is True then return only True or false without failing"""

    failures = []

    openstack_nodes = topology.list_openstack_nodes(group=group,
                                                    hostnames=nodenames)
    for node in openstack_nodes:
        node_containers = list_node_containers(ssh_client=node.ssh_client)
        containers_list_td = tobiko.TableData(
            get_container_states_list(node_containers),
            columns=['container_host', 'container_name', 'container_state'])
        # check that the containers are present
        LOG.info('node: {} containers list : {}'.format(
            node.name, containers_list_td.to_string()))
        for container_itr in expected_containers:
            container_name, container_attrs, container_fail = (
                _select_container(container_itr, full_name, node.name,
                                  containers_list_td))

            # check if any container exists
            LOG.info('checking container(s): {}'.format(container_itr))
            if not container_name:
                failures += container_fail
                continue
            else:
                LOG.info('selected container: {}'.format(container_name))

            # If one container exists, check it is running and discard the
            # other options. Only one running container is expected.
            container_running_attrs = container_attrs.query(
                'container_state=="running"')
            if container_running_attrs.empty:
                failures.append(
                    'expected container {} is not running on node {} , '
                    'its state is {}! : \n\n'.format(
                        container_name, node.name,
                        container_attrs['container_state'].values.item()))
            elif len(container_running_attrs) > 1:
                failures.append(
                    'only one running container {} was expected on '
                    'node {}, but got {}! : \n\n'.format(
                        container_name, node.name,
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
    ovn_containers = [('ovn_metadata_agent', 'ovn_agent'),
                      'ovn_controller']
    potential_groups = ['edpm-compute', 'edpm-networker']
    groups = [group for group in potential_groups if
              group in topology.get_openstack_topology().groups]
    for group in groups:
        assert_containers_running(group, ovn_containers)
    LOG.info("Networking OVN containers verified in running state")


def get_container_states_list(containers_list,
                              include_container_objects=False):
    container_states_list = tobiko.Selection()
    container_states_list.extend([comparable_container_keys(
        container, include_container_objects=include_container_objects) for
                                  container in containers_list])
    return container_states_list


def save_containers_state_to_file(expected_containers_list,):
    expected_containers_td = tobiko.TableData(
        get_container_states_list(expected_containers_list),
        columns=['container_host', 'container_name', 'container_state'])
    expected_containers_td.to_csv(
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
def list_containers_objects_td():
    containers_list = list_containers()
    containers_objects_list_td = tobiko.TableData(
        get_container_states_list(
            containers_list, include_container_objects=True),
        columns=['container_host', 'container_name',
                 'container_state', 'container_object'])
    return containers_objects_list_td


def get_edpm_container(container_name=None, container_host=None,
                       partial_container_name=None):
    """gets an container object by name on specified host
    container"""
    con_obj_td = list_containers_objects_td()
    if partial_container_name and container_host:
        filtered_rows = []
        for row in con_obj_td:
            if partial_container_name in row['container_name']:
                filtered_rows.append(row)
        con_obj_td = tobiko.TableData(filtered_rows)

        container_obj = con_obj_td.query(
            'container_host == "{container_host}"'.format(
                container_host=container_host))
        if not container_obj.empty:
            return container_obj.data[0]['container_object']
    elif container_host:
        container_obj = con_obj_td.query(
            'container_name == "{container_name}"'
            ' and container_host == "{container_host}"'.
            format(container_host=container_host,
                   container_name=container_name))
        if not container_obj.empty:
            return container_obj.data[0]['container_object']
    else:
        container_obj = con_obj_td.query(
            'container_name == "{container_name}"'.
            format(container_name=container_name))
        if not container_obj.empty:
            return container_obj.data[0]['container_object']

    tobiko.fail('container {} not found!'.format(container_name))


def action_on_container(action: str,
                        container_name=None,
                        container_host=None,
                        partial_container_name=None):
    """take a container and perform an action on it
    actions are as defined in : podman/libs/containers.py:14/164"""

    LOG.debug(f"Executing '{action}' action on container "
              f"'{container_name}' "
              f"on host '{container_host}'")

    container_object = get_edpm_container(
        container_name=container_name,
        container_host=container_host,
        partial_container_name=partial_container_name)

    try:
        container_action = getattr(container_object, action)
        container_action()
        LOG.debug(f"Successfully executed '{action}' action on container "
                  f"'{container_name}' on host '{container_host}'")
    except Exception as e:
        LOG.error(f"Error occurred while executing '{action}' action on "
                  f"container '{container_name}' on host '{container_host}': "
                  f"{e}")
        raise


def assert_equal_containers_state(expected_containers_list=None,
                                  timeout=120, interval=2,
                                  recreate_expected=False):

    """
    compare the current containers with the expected containers list
    the container states list is either built from the expected_containers_list
    or is the current containers state compared to the previously created file
    """

    expected_containers_td = None
    if recreate_expected or (
            not expected_containers_list and
            not os.path.exists(rhosp_containers.expected_containers_file)):
        save_containers_state_to_file(list_containers())
        return
    elif expected_containers_list:
        expected_containers_td = tobiko.TableData(
            get_container_states_list(expected_containers_list),
            columns=['container_host', 'container_name', 'container_state'])

    elif os.path.exists(rhosp_containers.expected_containers_file):
        with open(rhosp_containers.expected_containers_file, 'r') as f:
            expected_containers_td = tobiko.TableData.read_csv(f, header=0)

    LOG.info("Comparing current containers with expected containers")

    for attempt in tobiko.retry(timeout=timeout, interval=interval):
        actual_containers_td = list_containers_td()

        LOG.info(f'expected_containers_td: {expected_containers_td}')
        LOG.info(f'actual_containers_td: {actual_containers_td}')

        # execute a `tabledata` diff between the expected and actual containers
        diff_tb = rhosp_containers.tabledata_difference(
            expected_containers_td,
            actual_containers_td)

        if diff_tb.empty:
            LOG.info("All containers are on the same state")
            return

        if attempt.is_last:
            tobiko.fail("Containers state does not match expected state:\n"
                        f"{diff_tb}")
