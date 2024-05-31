from __future__ import absolute_import

import functools
import os
import re
import time
import typing

from oslo_log import log
import pandas

import tobiko
from tobiko import config
from tobiko import podman
from tobiko.openstack import neutron
from tobiko.openstack import topology
from tobiko import rhosp as rhosp_topology
from tobiko.rhosp import containers as rhosp_containers
from tobiko.shell import sh
from tobiko.tripleo import overcloud


CONF = config.CONF
LOG = log.getLogger(__name__)


class ContainerRuntimeFixture(tobiko.SharedFixture):

    runtime: typing.Optional[rhosp_containers.ContainerRuntime] = None

    def setup_fixture(self):
        if overcloud.has_overcloud():
            self.runtime = self.get_runtime()

    def cleanup_fixture(self):
        self.runtime = None

    @staticmethod
    def get_runtime() -> typing.Optional[rhosp_containers.ContainerRuntime]:
        """check what container runtime is running
        and return a handle to it"""
        # TODO THIS LOCKS SSH CLIENT TO CONTROLLER
        for node in topology.list_openstack_nodes(group='controller'):
            try:
                result = sh.execute('podman --version || docker --version',
                                    ssh_client=node.ssh_client)
            except sh.ShellCommandFailed:
                continue
            for runtime in rhosp_containers.CONTAINER_RUNTIMES:
                for version in [result.stdout, result.stderr]:
                    if runtime.match_version(version):
                        return runtime
        raise RuntimeError(
            "Unable to find any container runtime in any overcloud "
            "controller node")


def get_container_runtime() -> rhosp_containers.ContainerRuntime:
    runtime = tobiko.setup_fixture(ContainerRuntimeFixture).runtime
    return runtime


def get_container_runtime_name() -> str:
    return get_container_runtime().runtime_name


def is_docker() -> bool:
    return get_container_runtime().runtime_name == 'docker'


def is_podman() -> bool:
    return get_container_runtime().runtime_name == 'podman'


def has_container_runtime() -> bool:
    return get_container_runtime() is not None


def skip_unless_has_container_runtime():
    return tobiko.skip_unless('Container runtime not found',
                              has_container_runtime)


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
        group = 'overcloud'
    containers_list = tobiko.Selection()
    openstack_nodes = topology.list_openstack_nodes(group=group)

    for node in openstack_nodes:
        LOG.debug(f"List containers for node {node.name}")
        node_containers_list = list_node_containers(ssh_client=node.ssh_client)
        containers_list.extend(node_containers_list)
    return containers_list


def save_containers_state_to_file(expected_containers_list,):
    expected_containers_list_df = pandas.DataFrame(
        get_container_states_list(expected_containers_list),
        columns=['container_host', 'container_name', 'container_state'])
    expected_containers_list_df.to_csv(
        rhosp_containers.expected_containers_file)
    return rhosp_containers.expected_containers_file


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


def get_libvirt_container_name():
    if topology.verify_osp_version('17.0', lower=True):
        return 'nova_libvirt'
    else:
        return 'nova_virtqemud'


def assert_all_tripleo_containers_running():
    """check that all common tripleo containers are running
    param: group controller or compute , check containers
    sets in computes or controllers"""
    nova_libvirt = get_libvirt_container_name()

    common_controller_tripleo_containers = ['cinder_api', 'cinder_api_cron',
                                            'cinder_scheduler',
                                            'glance_api', 'heat_api',
                                            'heat_api_cfn',
                                            'heat_api_cron', 'heat_engine',
                                            'horizon', 'iscsid', 'keystone',
                                            'logrotate_crond', 'memcached',
                                            'neutron_api', 'nova_api',
                                            'nova_api_cron', 'nova_conductor',
                                            'nova_metadata', 'nova_scheduler',
                                            'nova_vnc_proxy',
                                            'swift_account_auditor',
                                            'swift_account_reaper',
                                            'swift_account_replicator',
                                            'swift_account_server',
                                            'swift_container_auditor',
                                            'swift_container_replicator',
                                            'swift_container_server',
                                            'swift_container_updater',
                                            'swift_object_auditor',
                                            'swift_object_expirer',
                                            'swift_object_replicator',
                                            'swift_object_server',
                                            'swift_object_updater',
                                            'swift_proxy', 'swift_rsync']

    shiftonstack_controller_tripleo_containers = ['cinder_api',
                                                  'cinder_api_cron',
                                                  'cinder_scheduler',
                                                  'glance_api', 'heat_api',
                                                  'heat_api_cfn',
                                                  'heat_api_cron',
                                                  'heat_engine',
                                                  'horizon', 'iscsid',
                                                  'keystone',
                                                  'logrotate_crond',
                                                  'memcached',
                                                  'neutron_api', 'nova_api',
                                                  'nova_api_cron',
                                                  'nova_conductor',
                                                  'nova_metadata',
                                                  'nova_scheduler',
                                                  'nova_vnc_proxy']

    common_compute_tripleo_containers = ['iscsid', 'logrotate_crond',
                                         'nova_compute', nova_libvirt,
                                         'nova_migration_target',
                                         'nova_virtlogd']

    if ceph_rgw_expected():
        tripleo_containers_to_check = \
            shiftonstack_controller_tripleo_containers
    else:
        tripleo_containers_to_check = \
            common_controller_tripleo_containers

    for group, group_containers in [('controller',
                                     tripleo_containers_to_check),
                                    ('compute',
                                     common_compute_tripleo_containers)]:
        assert_containers_running(group, group_containers)
    # TODO: need to address OSP-version specific containers here.
    # optional ovn containers checks
    assert_ovn_containers_running()


def assert_ceph_rgw_container_running():
    """check if ceph-rgw is running, usually on
    shifton stack deployments , if so we should not check for
    swift containers precence"""
    return assert_containers_running('controller', ['ceph-rgw'],
                                     full_name=False, bool_check=True)


def ceph_rgw_expected():
    """Returns True if 'ceph_rgw' parameter in the config file is set to 'true'
    or ceph rgw containers were detected running by Tobiko.
    """
    return CONF.tobiko.rhosp.ceph_rgw or assert_ceph_rgw_container_running()


def skip_if_ceph_rgw():
    return tobiko.skip_if('Ceph rgw deployed', ceph_rgw_expected)


def osp13_container_name_short_format(container_name_long_format):
    """This takes a long format container name :
    'rhosp13/openstack-neutron-l3-agent'
    and turns it into : neutron_l3_agent
    """
    return re.sub('-', '_', re.sub('rhosp13/openstack-', '',
                                   container_name_long_format))


def assert_ovn_containers_running():
    if not neutron.has_ovn():
        LOG.info("Networking OVN not configured")
        return

    # specific OVN verifications
    ovn_controller_containers = ['ovn_controller']
    if overcloud.is_ovn_using_raft():
        ovn_controller_containers += ['ovn_cluster_northd',
                                      'ovn_cluster_north_db_server',
                                      'ovn_cluster_south_db_server']
    else:
        container_runtime_name = get_container_runtime_name()
        ovn_controller_containers += [
            f'ovn-dbs-bundle-{container_runtime_name}-']
    ovn_compute_containers = ['ovn_metadata_agent',
                              'ovn_controller']
    group_containers_list = [('controller', ovn_controller_containers),
                             ('compute', ovn_compute_containers)]
    if 'networker' in topology.list_openstack_node_groups():
        ovn_networker_containers = ['ovn_controller']
        group_containers_list.append(('networker',
                                      ovn_networker_containers))
    for group, group_containers in group_containers_list:
        assert_containers_running(group, group_containers, full_name=False)
    LOG.info("Networking OVN containers verified in running state")


def run_container_config_validations():
    """check containers configuration in different scenarios
    """

    # TODO add here any generic configuration validation
    config_checkings = []

    if neutron.has_ovn():
        ovn_config_checkings = \
            [{'node_group': 'controller',
              'container_name': 'neutron_api',
              'config_file': '/etc/neutron/plugins/ml2/ml2_conf.ini',
              'param_validations': [{'section': 'ml2',
                                     'param': 'mechanism_drivers',
                                     'expected_value': 'ovn'},
                                    {'section': 'ml2',
                                     'param': 'type_drivers',
                                     'expected_value': 'geneve'},
                                    {'section': 'ovn',
                                     'param': 'ovn_metadata_enabled',
                                     'expected_value': 'True'}]}]
        config_checkings += ovn_config_checkings
    else:
        ovs_config_checkings = \
            [{'node_group': 'controller',
              'container_name': 'neutron_api',
              'config_file': '/etc/neutron/plugins/ml2/ml2_conf.ini',
              'param_validations': [{'section': 'ml2',
                                     'param': 'mechanism_drivers',
                                     'expected_value': 'openvswitch'}]}]
        config_checkings += ovs_config_checkings

    container_runtime_name = get_container_runtime_name()
    for config_check in config_checkings:
        for node in topology.list_openstack_nodes(
                group=config_check['node_group']):
            for param_check in config_check['param_validations']:
                obtained_param = sh.execute(
                    f"{container_runtime_name} exec -uroot "
                    f"{config_check['container_name']} crudini "
                    f"--get {config_check['config_file']} "
                    f"{param_check['section']} {param_check['param']}",
                    ssh_client=node.ssh_client, sudo=True).stdout.strip()
                if param_check['expected_value'] not in obtained_param:
                    tobiko.fail(f"Expected {param_check['param']} value: "
                                f"{param_check['expected_value']}\n"
                                f"Obtained {param_check['param']} value: "
                                f"{obtained_param}")
        LOG.info("Configuration verified:\n"
                 f"node group: {config_check['node_group']}\n"
                 f"container: {config_check['container_name']}\n"
                 f"config file: {config_check['config_file']}")


def comparable_container_keys(container, include_container_objects=False):
    """returns the tuple : 'container_host','container_name',
    'container_state, container object if specified'
     """
    # Differenciate between podman_ver3 with podman-py from earlier api
    if is_podman():
        if podman.Podman_Version_3():
            con_host_name_stat_obj_tuple = (rhosp_topology.ip_to_hostname(
                container.client.base_url.netloc.rsplit('_')[1]),
                                            container.attrs[
                'Names'][0], container.attrs['State'], container)

            con_host_name_stat_tuple = (rhosp_topology.ip_to_hostname(
                container.client.base_url.netloc.rsplit('_')[1]),
                                        container.attrs[
                'Names'][0], container.attrs['State'])
        else:

            con_host_name_stat_obj_tuple = (rhosp_topology.ip_to_hostname(
                container._client._context.hostname),  # pylint: disable=W0212
                container.data['names'], container.data['status'], container)

            con_host_name_stat_tuple = (rhosp_topology.ip_to_hostname(
                container._client._context.hostname),  # pylint: disable=W0212
                container.data['names'], container.data['status'])

        if include_container_objects:
            return con_host_name_stat_obj_tuple
        else:
            return con_host_name_stat_tuple

    elif is_docker():
        if include_container_objects:
            return (container.client.api.ssh_client.hostname,
                    osp13_container_name_short_format(container.attrs[
                                                          'Labels']['name']),
                    container.attrs['State'],
                    container)
        else:
            return (container.client.api.ssh_client.hostname,
                    osp13_container_name_short_format(container.attrs[
                                                          'Labels']['name']),
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


def get_overcloud_container(container_name=None, container_host=None,
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
    """take a container snd preform an action on it
    actions are as defined in : podman/libs/containers.py:14/164"""

    LOG.debug(f"Executing '{action}' action on container "
              f"'{container_name}@{container_host}'...")
    container = get_overcloud_container(
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


def get_container_states_list(containers_list,
                              include_container_objects=False):
    container_states_list = tobiko.Selection()
    container_states_list.extend([comparable_container_keys(
        container, include_container_objects=include_container_objects) for
                                  container in containers_list])
    return container_states_list


def assert_equal_containers_state(expected_containers_list=None,
                                  timeout=120, interval=2,
                                  recreate_expected=False):

    """compare all overcloud container states with using two lists:
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
        tobiko.fail(
            'container states mismatched:\n{!s}'.format('\n'.join(failures)),
            rhosp_containers.ContainerMismatchException)
