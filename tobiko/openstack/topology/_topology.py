# Copyright 2019 Red Hat
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
from collections import abc
import configparser
import functools
import re
import typing
from urllib import parse
import weakref

import netaddr
from oslo_log import log
from packaging import version

import tobiko
from tobiko.shell import files
from tobiko.shell import ip
from tobiko.shell import sh
from tobiko.shell import ssh
from tobiko.openstack import neutron
from tobiko.openstack import nova
from tobiko.openstack import keystone
from tobiko.openstack.topology import _address
from tobiko.openstack.topology import _config
from tobiko.openstack.topology import _connection
from tobiko.openstack.topology import _exception


LOG = log.getLogger(__name__)


PatternType = type(re.compile(r'.*'))
OpenstackGroupNameType = typing.Union[str, typing.Pattern]
OpenstackGroupNamesType = typing.Optional[typing.Union[
    OpenstackGroupNameType, typing.Iterable[OpenstackGroupNameType]]]


HostAddressType = typing.Union[str, netaddr.IPAddress]


def list_openstack_nodes(addresses: typing.Iterable[netaddr.IPAddress] = None,
                         group: OpenstackGroupNamesType = None,
                         hostnames: typing.Iterable[str] = None,
                         topology: 'OpenStackTopology' = None,
                         **kwargs) \
        -> tobiko.Selection['OpenStackTopologyNode']:
    if topology is None:
        topology = get_openstack_topology()

    nodes: tobiko.Selection[OpenStackTopologyNode]
    if group is None:
        nodes = topology.nodes
    elif isinstance(group, str):
        nodes = topology.get_group(group=group)
    elif isinstance(group, PatternType):
        nodes = topology.get_groups(groups=[group])
    else:
        assert isinstance(group, abc.Iterable)
        nodes = topology.get_groups(groups=group)

    return select_openstack_nodes(nodes,
                                  addresses=addresses,
                                  hostnames=hostnames,
                                  **kwargs)


def split_addresses_and_names(*hosts: HostAddressType) \
        -> typing.Tuple[typing.Set[netaddr.IPAddress], typing.Set[str]]:
    addresses = set()
    hostnames = set()
    for host in hosts:
        try:
            addresses.add(netaddr.IPAddress(host))
        except netaddr.AddrFormatError:
            hostnames.add(host)
    return addresses, hostnames


def select_openstack_nodes(
        nodes: tobiko.Selection['OpenStackTopologyNode'],
        addresses: typing.Iterable[netaddr.IPAddress] = None,
        hostnames: typing.Iterable[str] = None,
        **kwargs) \
        -> tobiko.Selection['OpenStackTopologyNode']:
    for selector in addresses, hostnames:
        if selector is not None and not selector:
            return tobiko.Selection()

    if addresses is not None:
        _addresses = set(addresses)
        nodes = nodes.select(
            lambda node: bool(set(node.addresses) & _addresses))

    if hostnames is not None:
        names = {node_name_from_hostname(hostname)
                 for hostname in hostnames}
        nodes = nodes.select(lambda node: node.name in names)

    if kwargs:
        nodes = nodes.with_attributes(**kwargs)
    return nodes


def find_openstack_node(addresses: typing.Iterable[netaddr.IPAddress] = None,
                        group: OpenstackGroupNamesType = None,
                        hostnames: typing.Iterable[str] = None,
                        topology: 'OpenStackTopology' = None,
                        unique=False,
                        **kwargs) \
        -> 'OpenStackTopologyNode':
    nodes = list_openstack_nodes(topology=topology,
                                 addresses=addresses,
                                 group=group,
                                 hostnames=hostnames,
                                 **kwargs)
    if unique:
        return nodes.unique
    else:
        return nodes.first


def get_l3_agent_mode(name: str = None,
                      hostname: str = None,
                      address=None,
                      topology: 'OpenStackTopology' = None):
    return get_openstack_node(name=name,
                              hostname=hostname,
                              address=address,
                              topology=topology).l3_agent_mode


def get_openstack_node(name: str = None,
                       hostname: str = None,
                       address=None,
                       topology: 'OpenStackTopology' = None) \
        -> 'OpenStackTopologyNode':
    if topology is None:
        topology = get_openstack_topology()
    return topology.get_node(name=name,
                             hostname=hostname,
                             address=address)


def list_openstack_node_groups(topology=None):
    topology = topology or get_openstack_topology()
    return topology.groups


def get_default_openstack_topology_class() -> typing.Type:
    return DEFAULT_TOPOLOGY_CLASS


def set_default_openstack_topology_class(topology_class: typing.Type):
    # pylint: disable=global-statement
    if not issubclass(topology_class, OpenStackTopology):
        raise TypeError(f"'{topology_class}' is not subclass of "
                        f"'{OpenStackTopology}'")
    global DEFAULT_TOPOLOGY_CLASS
    DEFAULT_TOPOLOGY_CLASS = topology_class


def get_agent_service_name(agent_name: str) -> str:
    topology_class = get_default_openstack_topology_class()
    return topology_class.get_agent_service_name(agent_name)


def get_agent_container_name(agent_name: str) -> str:
    topology_class = get_default_openstack_topology_class()
    return topology_class.get_agent_container_name(agent_name)


def check_systemd_monitors_agent(hostname: str, agent_name: str) -> bool:
    ssh_client = get_openstack_node(hostname=hostname).ssh_client
    services = sh.execute('systemctl list-units --type=service --all '
                          '--no-pager --no-legend',
                          ssh_client=ssh_client,
                          sudo=True).stdout.split('\n')
    for service in services:
        if get_agent_service_name(agent_name) in service:
            return True
    return False


class UnknowOpenStackServiceNameError(tobiko.TobikoException):
    message = ("Unknown service name for agent name '{agent_name}' and "
               "topology class '{topology_class}'")


class UnknowOpenStackContainerNameError(tobiko.TobikoException):
    message = ("Unknown container name for agent name '{agent_name}' and "
               "topology class '{topology_class}'")


class UnknownOpenStackConfigurationFile(tobiko.TobikoException):
    message = ("Unknown configuration file '{file_name}'")


class OpenStackTopologyNode:

    _docker_client = None
    _podman_client = None

    def __init__(self,
                 topology: 'OpenStackTopology',
                 name: str,
                 ssh_client: typing.Optional[ssh.SSHClientFixture],
                 addresses: typing.Iterable[netaddr.IPAddress],
                 hostname: str):
        self._topology = weakref.ref(topology)
        self.name = name
        self.ssh_client = ssh_client
        self.groups: typing.Set[str] = set()
        self.addresses: tobiko.Selection[netaddr.IPAddress] = tobiko.select(
            addresses)
        self.hostname: str = hostname

    _connection: typing.Optional[sh.ShellConnection] = None

    @property
    def connection(self) -> sh.ShellConnection:
        if self._connection is None:
            self._connection = sh.shell_connection(self.ssh_client)
        return self._connection

    @property
    def topology(self):
        return self._topology()

    def add_group(self, group: str):
        self.groups.add(group)

    @property
    def public_ip(self):
        return self.addresses[0]

    @property
    def ssh_parameters(self):
        return self.ssh_client.setup_connect_parameters()

    @property
    def docker_client(self):
        docker_client = self._docker_client
        if not docker_client:
            from tobiko import docker
            self._docker_client = docker_client = docker.get_docker_client(
                ssh_client=self.ssh_client)
        return docker_client

    @property
    def podman_client(self):
        podman_client = self._podman_client
        if not podman_client:
            from tobiko import podman
            self._podman_client = podman_client = podman.get_podman_client(
                ssh_client=self.ssh_client)
        return podman_client

    l3_agent_conf_path = '/etc/neutron/l3_agent.ini'
    _l3_agent_mode: typing.Optional[str] = None

    @property
    def l3_agent_mode(self) -> typing.Optional[str]:
        if self._l3_agent_mode is None:
            try:
                self._l3_agent_mode = neutron.get_l3_agent_mode(
                    l3_agent_conf_path=self.l3_agent_conf_path,
                    connection=self.connection)
            except sh.ShellCommandFailed:
                LOG.debug('Unable to read L3 agent mode for host '
                          f'{self.hostname}. Assuming legacy mode.',
                          exc_info=1)
                self._l3_agent_mode = 'legacy'
        return self._l3_agent_mode

    def __repr__(self):
        return "{cls!s}<name={name!r}>".format(cls=type(self).__name__,
                                               name=self.name)


class OpenStackTopology(tobiko.SharedFixture):

    config = tobiko.required_fixture(_config.OpenStackTopologyConfig)

    agent_to_service_name_mappings = {
        neutron.DHCP_AGENT: 'devstack@q-dhcp',
        neutron.L3_AGENT: 'devstack@q-l3',
        neutron.OPENVSWITCH_AGENT: 'devstack@q-agt',
        neutron.METADATA_AGENT: 'devstack@q-meta',
        neutron.OVN_METADATA_AGENT: 'devstack@q-ovn-metadata-agent',
        neutron.NEUTRON_OVN_METADATA_AGENT: 'devstack@q-ovn-metadata-agent',
        neutron.OVN_CONTROLLER: 'ovn-controller',
        neutron.OVN_BGP_AGENT: 'ovn-bgp-agent',
        neutron.FRR: 'frr',
        neutron.NEUTRON: 'neutron'
    }
    agent_to_container_name_mappings: typing.Dict[str, str] = {}

    has_containers = False

    container_runtime_cmd = 'docker'

    config_file_mappings = {
        'ml2_conf.ini': '/etc/neutron/plugins/ml2/ml2_conf.ini',
        'bgp-agent.conf': '/etc/ovn-bgp-agent/bgp-agent.conf'
    }

    _connections = tobiko.required_fixture(
        _connection.SSHConnectionManager)

    # In Devstack based env logs can be accessed by journalctl
    file_digger_class: typing.Type[files.LogFileDigger] = \
        files.JournalLogDigger

    # This is dict which handles mapping of the log file and systemd_unit (if
    # needed) for the OpenStack services.
    # In case of Devstack topology file name in fact name of the systemd unit
    # as logs are stored in journalctl
    log_names_mappings = {
        neutron.SERVER: 'devstack@q-svc',
    }

    def __init__(self):
        super(OpenStackTopology, self).__init__()
        self._names: typing.Dict[str, OpenStackTopologyNode] = (
            collections.OrderedDict())
        self._groups: typing.Dict[str, tobiko.Selection] = (
            collections.OrderedDict())
        self._addresses: typing.Dict[netaddr.IPAddress,
                                     OpenStackTopologyNode] = (
            collections.OrderedDict())

    def setup_fixture(self):
        self.discover_nodes()

    def cleanup_fixture(self):
        tobiko.cleanup_fixture(self._connections)
        self._names.clear()
        self._groups.clear()
        self._addresses.clear()

    @classmethod
    def get_agent_service_name(cls, agent_name: str) -> str:
        try:
            return cls.agent_to_service_name_mappings[agent_name]
        except KeyError:
            pass
        raise UnknowOpenStackServiceNameError(agent_name=agent_name,
                                              topology_class=cls)

    @classmethod
    def get_agent_container_name(cls, agent_name: str) -> str:
        try:
            return cls.agent_to_container_name_mappings[agent_name]
        except KeyError:
            pass
        raise UnknowOpenStackContainerNameError(agent_name=agent_name,
                                                topology_class=cls)

    def get_config_file_path(self, file_name: str) -> str:
        try:
            return self.config_file_mappings[file_name]
        except KeyError as e:
            raise UnknownOpenStackConfigurationFile(file_name=file_name) from e

    def get_log_file_digger(self,
                            service_name: str,
                            pattern: typing.Optional[str] = None,
                            groups: typing.Optional[typing.List[str]] = None,
                            sudo=True,
                            **execute_params) -> \
            files.MultihostLogFileDigger:
        digger = files.MultihostLogFileDigger(
            filename=self.log_names_mappings[service_name],
            pattern=pattern,
            file_digger_class=self.file_digger_class,
            sudo=sudo,
            **execute_params)
        if groups is None:
            nodes = self.nodes
        else:
            nodes = self.get_groups(groups=groups)
        for node in nodes:
            digger.add_host(hostname=node.name,
                            ssh_client=node.ssh_client)
        return digger

    def assert_containers_running(self, expected_containers,
                                  group=None,
                                  full_name=True, bool_check=False,
                                  nodenames=None):
        pass

    def list_containers_df(self, group=None):
        pass

    def discover_nodes(self):
        self.discover_ssh_proxy_jump_node()
        self.discover_configured_nodes()
        if keystone.has_keystone_credentials():
            self.discover_controller_nodes()
            self.discover_compute_nodes()

    def discover_ssh_proxy_jump_node(self):
        ssh_client = ssh.ssh_proxy_client()
        if ssh_client is not None:
            self.add_node(ssh_client=ssh_client,
                          group='proxy_jump')

    def discover_configured_nodes(self):
        for address in self.config.conf.nodes or []:
            self.add_node(address=address)

    def discover_controller_nodes(self):
        endpoints = keystone.list_endpoints(interface='public')
        addresses = set(parse.urlparse(endpoint.url).hostname
                        for endpoint in endpoints)
        for address in addresses:
            try:
                self.add_node(address=address, group='controller')
            except _connection.UreachableSSHServer as ex:
                LOG.debug(f"Unable to SSH to end point address '{address}'. "
                          f"{ex}")

    def discover_compute_nodes(self):
        for hypervisor in nova.list_hypervisors():
            self.add_node(hostname=hypervisor.hypervisor_hostname,
                          address=hypervisor.host_ip,
                          group='compute')

    def add_node(self,
                 hostname: typing.Optional[str] = None,
                 address: typing.Optional[str] = None,
                 group: typing.Optional[str] = None,
                 ssh_client: typing.Optional[ssh.SSHClientFixture] = None,
                 **create_params) \
            -> OpenStackTopologyNode:
        if ssh_client is not None:
            # detect all global addresses from remote server
            try:
                hostname = sh.get_hostname(ssh_client=ssh_client)
            except Exception:
                LOG.exception("Unable to get node hostname from "
                              f"{ssh_client}")
                ssh_client = None
        name = hostname and node_name_from_hostname(hostname) or None

        addresses: typing.List[netaddr.IPAddress] = []
        if address:
            # add manually configure addresses first
            addresses.extend(self._list_addresses(address))
        addresses = tobiko.select(remove_duplications(addresses))

        try:
            node = self.get_node(name=name, address=addresses)
        except _exception.NoSuchOpenStackTopologyNode:
            node = self._add_node(addresses=addresses,
                                  hostname=hostname,
                                  ssh_client=ssh_client,
                                  **create_params)

        if group:
            # Add group anyway even if the node hasn't been added
            group_nodes = self.add_group(group=group)
            if node and node not in group_nodes:
                group_nodes.append(node)
                node.add_group(group=group)

        return node

    def _add_node(self,
                  addresses: typing.List[netaddr.IPAddress],
                  hostname: str = None,
                  ssh_client: ssh.SSHClientFixture = None,
                  create_ssh_client: bool = True,
                  **create_params):
        if ssh_client is None and create_ssh_client:
            ssh_client = self._ssh_connect(hostname=hostname,
                                           addresses=addresses)
        addresses.extend(self._list_addresses_from_host(ssh_client=ssh_client))
        addresses = tobiko.select(remove_duplications(addresses))
        hostname = hostname or sh.get_hostname(ssh_client=ssh_client)
        name = node_name_from_hostname(hostname)
        try:
            node = self._names[name]
        except KeyError:
            ssh_login = (
                ssh_client.login if ssh_client else "No SSH Client configured")
            LOG.debug("Add topology node:\n"
                      f" - name: {name}\n"
                      f" - hostname: {hostname}\n"
                      f" - login: {ssh_login}\n"
                      f" - addresses: {addresses}\n")
            self._names[name] = node = self.create_node(name=name,
                                                        hostname=hostname,
                                                        ssh_client=ssh_client,
                                                        addresses=addresses,
                                                        **create_params)

        for address in addresses:
            address_node = self._addresses.setdefault(address, node)
            if address_node is not node:
                LOG.warning(f"Address '{address}' of node '{name}' is already "
                            f"used by node '{address_node.name}'")
        return node

    def get_node(self,
                 name: str = None,
                 hostname: str = None,
                 address=None) \
            -> 'OpenStackTopologyNode':
        if name is None and hostname is not None:
            name = node_name_from_hostname(hostname)
        details = {}
        if name is not None:
            tobiko.check_valid_type(name, str)
            details['name'] = name
            try:
                return self._names[name]
            except KeyError:
                pass
        if address is not None:
            details['address'] = address
            for address in self._list_addresses(address):
                try:
                    return self._addresses[address]
                except KeyError:
                    pass
        raise _exception.NoSuchOpenStackTopologyNode(details=details)

    def create_node(self, name, ssh_client, **kwargs):
        return OpenStackTopologyNode(topology=self, name=name,
                                     ssh_client=ssh_client, **kwargs)

    @property
    def nodes(self) -> tobiko.Selection[OpenStackTopologyNode]:
        return tobiko.select(self.get_node(name)
                             for name in self._names)

    def add_group(self, group: str) -> tobiko.Selection:
        try:
            return self._groups[group]
        except KeyError:
            self._groups[group] = nodes = self.create_group()
            return nodes

    @staticmethod
    def create_group() -> tobiko.Selection[OpenStackTopologyNode]:
        return tobiko.Selection()

    def get_group(self, group: str) \
            -> tobiko.Selection[OpenStackTopologyNode]:
        tobiko.check_valid_type(group, str)
        try:
            return tobiko.Selection(self._groups[group])
        except KeyError as ex:
            raise _exception.NoSuchOpenStackTopologyNodeGroup(
                group=group) from ex

    def list_group_names(self,
                         *matchers: 'MatchStringType') \
            -> typing.List[str]:
        group_names: typing.List[str] = list(self._groups.keys())
        if matchers and group_names:
            group_names = match_strings(group_names, *matchers)
        return group_names

    def get_groups(self, groups: typing.Iterable['MatchStringType']) -> \
            tobiko.Selection[OpenStackTopologyNode]:
        node_names: typing.Set[str] = set()
        for group in self.list_group_names(*groups):
            node_names.update(node.name for node in self.get_group(group))
        return self.nodes.select(lambda node: node.name in node_names)

    @property
    def groups(self) -> typing.List[str]:
        return list(self._groups)

    def _ssh_connect(self,
                     addresses: typing.List[netaddr.IPAddress],
                     hostname: str = None,
                     **connect_params) -> ssh.SSHClientFixture:
        if hostname is not None:
            try:
                return tobiko.setup_fixture(
                    ssh.ssh_client(hostname, **connect_params))
            except Exception:
                LOG.debug(f'Unable to connect to {hostname} using regular '
                          'SSH configuration')

        try:
            return _connection.ssh_connect(addresses,
                                           **connect_params)
        except _connection.UreachableSSHServer:
            for proxy_node in self.nodes:
                proxy_client = proxy_node.ssh_client
                if proxy_client:
                    LOG.debug("Try connecting through a proxy node "
                              f"'{proxy_node.name}'")
                    try:
                        return self._ssh_connect_with_proxy_client(
                            addresses, proxy_client, **connect_params)
                    except _connection.UreachableSSHServer:
                        pass
            raise

    def _ssh_connect_with_proxy_client(self, addresses, proxy_client,
                                       **connect_params) -> \
            ssh.SSHClientFixture:
        ssh_client = _connection.ssh_connect(addresses,
                                             proxy_client=proxy_client,
                                             **connect_params)
        addresses = self._list_addresses_from_host(ssh_client=ssh_client)
        try:
            LOG.debug("Try connecting through an address that doesn't require "
                      "an SSH proxy host")
            return _connection.ssh_connect(addresses, **connect_params)
        except _connection.UreachableSSHServer:
            return ssh_client

    @property
    def ip_version(self) -> typing.Optional[int]:
        ip_version = self.config.conf.ip_version
        return ip_version and int(ip_version) or None

    def _list_addresses_from_host(
            self,
            ssh_client: typing.Optional[ssh.SSHClientFixture]):
        if not ssh_client:
            return tobiko.Selection()
        return ip.list_ip_addresses(ssh_client=ssh_client,
                                    ip_version=self.ip_version,
                                    scope='global')

    def _list_addresses(self, obj) -> typing.List[netaddr.IPAddress]:
        return _address.list_addresses(obj,
                                       ip_version=self.ip_version,
                                       ssh_config=True)


def get_openstack_topology(topology_class: typing.Type = None) -> \
        OpenStackTopology:
    if topology_class:
        if not issubclass(topology_class, OpenStackTopology):
            raise TypeError(f"'{topology_class}' is not subclass of "
                            f"'{OpenStackTopology}'")
    else:
        topology_class = get_default_openstack_topology_class()
    return tobiko.setup_fixture(topology_class)


def get_log_file_digger(
        service_name: str,
        pattern: str = None,
        groups: typing.List[str] = None,
        topology: OpenStackTopology = None,
        sudo=True,
        **execute_params) \
        -> files.MultihostLogFileDigger:
    if topology is None:
        topology = get_openstack_topology()
    return topology.get_log_file_digger(service_name=service_name,
                                        pattern=pattern,
                                        groups=groups,
                                        sudo=sudo,
                                        **execute_params)


def get_config_file_path(file_name: str) -> str:
    topology = get_openstack_topology()
    return topology.get_config_file_path(file_name)


def get_config_setting(file_name: str,
                       ssh_client: ssh.SSHClientFixture,
                       param: str,
                       section: str = None) -> typing.Optional[str]:
    config_file_path = get_config_file_path(file_name)
    config_file_content = sh.execute(f'cat {config_file_path}',
                                     ssh_client=ssh_client, sudo=True).stdout
    config = configparser.ConfigParser()
    config.read_string(config_file_content)
    if section is None:
        value = config.defaults().get(param)
    elif section not in config.sections():
        value = None
    else:
        value = config[section].get(param)

    return value


def get_rhosp_version():
    ssh_client = list_openstack_nodes(group='controller')[0].ssh_client
    rhosp_release = sh.execute('cat /etc/rhosp-release',
                               ssh_client=ssh_client).stdout
    rhosp_version = re.search(r"[0-9]*\.[0-9]*\.[0-9]*", rhosp_release)[0]
    return rhosp_version


def get_nova_version_from_container():
    ssh_client = list_openstack_nodes(group='controller')[0].ssh_client
    for container_runtime_cmd in ('docker', 'podman'):
        try:
            cmd = (container_runtime_cmd +
                   ' exec -uroot nova_conductor nova-manage --version')
            return sh.execute(cmd,
                              ssh_client=ssh_client,
                              sudo=True).stdout
        except sh.ShellCommandFailed:
            pass


# During a execution of tobiko, openstack version does not change, so let's
# cache the output of this function
@functools.lru_cache()
def get_openstack_version():
    try:
        return get_rhosp_version()
    except (TypeError, sh.ShellCommandFailed):
        pass

    nova_version = get_nova_version_from_container()
    if nova_version is None:
        ssh_client = list_openstack_nodes(group='controller')[0].ssh_client
        nova_version = sh.execute('nova-manage --version',
                                  ssh_client=ssh_client,
                                  sudo=True).stdout
    os_to_nova_versions = {'13.0.0': '17',  # Queens
                           '16.0.0': '19',  # Stein
                           '16.1.0': '20',  # Train
                           '17.0.0': '23'}  # Wallaby
    for os_version, nova_major_version in os_to_nova_versions.items():
        if nova_version.split('.')[0] == nova_major_version:
            return os_version


DEFAULT_TOPOLOGY_CLASS = OpenStackTopology


def node_name_from_hostname(hostname: str):
    return hostname.split('.', 1)[0].lower()


def remove_duplications(items: typing.List) -> typing.List:
    # use all items as dictionary keys to remove duplications
    mapping = collections.OrderedDict((k, None) for k in items)
    return list(mapping.keys())


def verify_osp_version(required_version, higher=False, lower=False):
    try:
        current_version = get_openstack_version()
    except Exception:
        current_version = None
    if current_version is None:
        return True

    required_version_parsed = version.parse(required_version)
    current_version_parsed = version.parse(current_version)

    if higher and lower:
        raise RuntimeError
    elif not higher and not lower:  # this means equal
        return current_version_parsed == required_version_parsed
    elif higher:
        return current_version_parsed > required_version_parsed
    elif lower:
        return current_version_parsed < required_version_parsed


def skip_unless_osp_version(required_version, higher=False, lower=False):
    skip_msg = "OSP version doesn't match the requirement"
    return tobiko.skip_unless(skip_msg, verify_osp_version,
                              required_version, higher, lower)


MatchStringType = typing.Union[str, typing.Pattern]


def match_strings(strings: typing.Iterable[str],
                  *matchers: MatchStringType) -> \
        typing.List[str]:
    matching: typing.List[str] = []
    for matcher in matchers:
        tobiko.check_valid_type(matcher, str, PatternType)
        if isinstance(matcher, str):
            if matcher in strings:
                matching.append(matcher)
        else:
            assert isinstance(matcher, PatternType)
            for string in strings:
                if matcher.match(string):
                    matching.append(string)
    return matching
