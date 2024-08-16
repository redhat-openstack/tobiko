# Copyright (c) 2020 Red Hat
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
import re
import sys
import typing
import time

from oslo_log import log
import testtools

import tobiko
from tobiko.openstack import neutron
from tobiko.openstack import nova
from tobiko.openstack import stacks
from tobiko.openstack import tests
from tobiko.openstack import topology
from tobiko.podified import _openshift
from tobiko import podified
from tobiko.shell import ping
from tobiko.shell import sh


LOG = log.getLogger(__name__)

# typing hits
AgentType = typing.Dict[str, typing.Any]
AgentListType = typing.List[AgentType]

STOP = "stop"
START = "start"
RESTART = "restart"


class BaseAgentTest(testtools.TestCase):

    agent_name: str = '<undefined agent name>'

    @classmethod
    def setUpClass(cls):
        cls.service_name: str = topology.get_agent_service_name(cls.agent_name)
        cls.container_name: str = ''
        cls.agents: AgentListType = \
            neutron.list_networking_agents(binary=cls.agent_name)

    def setUp(self):
        super(BaseAgentTest, self).setUp()
        if not self.agents:
            self.skipTest(f"Missing Neutron agent(s): '{self.agent_name}'")
        self.addCleanup(tests.test_neutron_agents_are_alive)

    @property
    def hosts(self) -> typing.List[str]:
        return [agent['host'] for agent in self.agents]

    @property
    def container_runtime_name(self):
        return topology.get_openstack_topology().container_runtime_cmd

    def get_agent_container_name(self, agent_name):
        try:
            return topology.get_agent_container_name(agent_name)
        except topology.UnknowOpenStackContainerNameError:
            LOG.debug(
                'Network agents are not contenerized on this environment')
            return

    def get_ovn_agents_from_containers(self):
        if not self.agents:
            self.container_name = self.get_agent_container_name(
                self.agent_name)
            if not self.container_name:
                return
            oc_containers_df = \
                topology.get_openstack_topology().list_containers_df().query(
                    f'container_name == "{self.container_name}"')
            LOG.debug(
                f"{self.container_name} container found:\n{oc_containers_df}")

            self.agents = []
            for _, oc_container in oc_containers_df.iterrows():
                if oc_container['container_state'] == 'running':
                    agent_info = {'host': oc_container['container_host'],
                                  'name': oc_container['container_name']}
                    self.agents.append(agent_info)

    def _do_agent_action(self, action: str,
                         hosts: typing.Optional[typing.List[str]] = None):
        '''Do action on network agent on hosts

        It ensures that given operation, like START, STOP or RESTART of the
        service is done using systemd service or container.

        :parm action: String with action to do, it can be one of the following:
                      start, stop, restart
        :parm hosts: List of hostnames to do action on
        :type hosts: list of strings
        '''
        hosts = hosts or self.hosts
        self.assertNotEqual([], hosts, "Host list is empty")

        for host in hosts:
            ssh_client = topology.get_openstack_node(hostname=host).ssh_client
            if ssh_client is None and podified.has_podified_cp():
                LOG.warning("SSH access to OCP nodes not implemented yet")
                continue
            is_systemd = topology.check_systemd_monitors_agent(host,
                                                               self.agent_name)
            if is_systemd:
                LOG.debug(f"{action} service '{self.service_name}' on "
                          f"host '{host}'...")
                sh.execute(f"systemctl {action} {self.service_name}",
                           ssh_client=ssh_client,
                           sudo=True)
                LOG.debug(f"{action} of the service '{self.service_name}' "
                          f"on host '{host}' done.")
            else:
                if self.container_name == '':
                    self.container_name = self.get_agent_container_name(
                        self.agent_name)
                LOG.debug(f'{action} container {self.container_name} on '
                          f"host '{host}'...")
                sh.execute(f'{self.container_runtime_name} {action} '
                           f'{self.container_name}',
                           ssh_client=ssh_client,
                           sudo=True)
                LOG.debug(f'{action} of the container {self.container_name} '
                          f"on host '{host}' done.")

    def stop_agent(self, hosts: typing.Optional[typing.List[str]] = None):
        '''Stop network agent on hosts

        It ensures service service is stopped and register systemd service
        restart as test case cleanup. In case of systemd service is not
        available it stops the container itself

        :parm hosts: List of hostnames to stop agent on
        :type hosts: list of strings
        '''
        hosts = hosts or self.hosts
        self._do_agent_action(STOP, hosts)
        # Schedule auto-restart of service at the end of this test case
        self.addCleanup(self.start_agent, hosts=hosts)

    def start_agent(self, hosts: typing.Optional[typing.List[str]] = None):
        '''Start network agent on hosts

        It ensures system service is running. If the systemd service is not
        available it starts container itself

        :parm hosts: List of hostnames to start agent on
        :type hosts: list of strings
        '''
        self._do_agent_action(START, hosts)
        if self.container_name:
            topology.get_openstack_topology().assert_containers_running(
                expected_containers=[self.container_name],
                nodenames=hosts or self.hosts)

    def restart_agent(self, hosts: typing.Optional[typing.List[str]] = None):
        '''Restart network agent on hosts

        It ensures system service is restarted.

        :parm hosts: List of hostnames to start agent on
        :type hosts: list of strings
        '''
        self._do_agent_action(RESTART, hosts)
        if self.container_name:
            topology.get_openstack_topology().assert_containers_running(
                expected_containers=[self.container_name],
                nodenames=hosts or self.hosts)

    def restart_agent_container(
            self, hosts: typing.Optional[typing.List[str]] = None):
        '''Restart network agent containers on hosts

        Restart docker or podman containers and check network agents are up and
        running after it

        :parm hosts: List of hostnames to start agent on
        :type hosts: list of strings
        '''
        hosts = hosts or self.hosts
        self.assertNotEqual([], hosts, "Host list is empty")

        self.container_name = (self.container_name or
                               self.get_agent_container_name(
                                   self.agent_name))
        if not self.container_name:
            self.skipTest(f"Missing container(s): '{self.container_name}'")

        for host in hosts:
            ssh_client = topology.get_openstack_node(hostname=host).ssh_client
            if ssh_client is None and podified.has_podified_cp():
                LOG.warning("SSH access to OCP nodes not implemented yet")
                continue
            sh.execute(f'{self.container_runtime_name} restart '
                       f'{self.container_name}',
                       ssh_client=ssh_client,
                       sudo=True)

        if self.container_name:
            topology.get_openstack_topology().assert_containers_running(
                expected_containers=[self.container_name],
                nodenames=hosts or self.hosts)

    def get_cmd_pids(self, process_name, command_filter, hosts=None,
                     timeout=120, interval=2, min_pids_per_host=1,
                     max_pids_per_host=sys.maxsize) -> \
            typing.Dict[str, frozenset]:
        '''Search for PIDs that match creteria on requested hosts

        :param process_name: Name of the executable of the process
        :type process_name: string
        :parm command_filter: Regex to be found in process command details
        :type command_filter: string
        :param hosts: List of hostnames to search for processes on
        :type hosts: list of strings
        :param timeout: Time to search for processes
        :type timeout: int
        :param interval: Time to wait between searching attempts
        :param min_pids_per_host: Minimum amount of processes to be found
        :type min_pids_per_host: int
        :param max_pids_per_host: Maximum amount of processes to be found
        :type max_pids_per_host: int
        :return: Dictionary with hostnames as a key and list of PIDs as value
        :rtype: dict
        '''
        hosts = hosts or self.hosts
        self.assertNotEqual([], hosts, "Host list is empty")
        self.assertGreater(min_pids_per_host, 0)
        self.assertGreater(max_pids_per_host, 0)
        self.assertGreaterEqual(max_pids_per_host, min_pids_per_host)
        pids_count_range = range(min_pids_per_host, max_pids_per_host + 1)
        pids_per_host: collections.defaultdict = collections.defaultdict(set)
        checked_pids_per_host: collections.defaultdict = (
            collections.defaultdict(list))
        for host in hosts:
            LOG.debug(f'Search for {process_name} process on {host}')
            for attempt in tobiko.retry(timeout=timeout, interval=interval):
                pids, checked_pids = self.list_pids(
                    host, command_filter, process_name,
                    checked_pids_per_host[host])
                checked_pids_per_host[host] += checked_pids
                pids_per_host[host] |= set(pids)
                if (len(pids_per_host[host]) in pids_count_range
                        or attempt.is_last):
                    LOG.debug(f"Process '{process_name}' is running "
                              f"on host '{host}' "
                              f"(PIDs={pids_per_host[host]!r})")
                    break
                LOG.debug(f"PIDs for {process_name} on {host} not found.")
            else:
                raise RuntimeError("Broken retry loop")
        LOG.debug(f"Found PIDs: {pids_per_host}")
        return pids_per_host

    def list_pids(self, host, command_filter, process_name, known_pids=None):
        '''Search for PIDs matched with filter and process name

        :param host: Hostname of the node to search processes on
        :type host: string
        :param command_filter: Regex to be found in process command details
        :type command_filter: string
        :param process_name: Name of the executable in process list
        :type process_name: string
        :param known_pids: List of the pids which were already checked on host
        :type: known_pids: list
        '''
        ssh_client = topology.get_openstack_node(hostname=host).ssh_client
        processes = sh.list_processes(command=process_name,
                                      ssh_client=ssh_client)
        known_pids = known_pids or []
        pids = []
        checked_pids = []
        for process in processes:
            if process.pid in known_pids:
                continue
            try:
                command = sh.execute(f'cat /proc/{process.pid}/cmdline',
                                     ssh_client=ssh_client)
                checked_pids.append(process.pid)
                if re.search(command_filter, command.stdout):
                    pids.append(process.pid)
            except sh.ShellCommandFailed:
                LOG.debug(f'Process {process.pid} has been terminated right '
                          f'after the process list has been collected')
        return pids, checked_pids

    def kill_pids(self, host, pids):
        '''Kill processes with specific PIDs on the host

        :param host: Hostname of the node to kill processes on
        :type host: string
        :param pids: List of PIDs to be killed
        :type pids: list of int
        '''
        ssh_client = topology.get_openstack_node(hostname=host).ssh_client
        pid_args = ' '.join(str(pid) for pid in pids)
        sh.execute(f'kill -15 {pid_args}', ssh_client=ssh_client, sudo=True)
        retry = tobiko.retry(timeout=60, interval=2)
        for _ in retry:
            pid_status = sh.execute(f'kill -0 {pid_args}',
                                    ssh_client=ssh_client,
                                    expect_exit_status=None,
                                    sudo=True).stderr.strip().split('\n')
            if all('No such process' in status for status in pid_status) and \
                    len(pid_status) == len(pids):
                break

    def wait_processes_destroyed(self, command_filter, pids_per_host,
                                 timeout=120, interval=2):
        '''Wait for processes to be terminated on hosts

        Make sure that all processes from the list are terminated or return
        an error otherwise. Tricky situation may happen when the different
        process with same PID can be spawned so then need to check it against
        `command_filter`.

        :param command_filter: Patter to be found in process command details
        :type command_filter: string
        :param pids_per_host: Dictionary with hostnames as a key and list of
                PIDs as a value
        :type pids_per_host: dict
        :param timeout: Time to wait till each process will be terminated
        :type timeout: int
        :param interval: Time to sleep between attempts
        :type interval: int
        '''
        LOG.debug(f'Waiting for processes to be finished: {pids_per_host}')
        for host, pids in pids_per_host.items():
            for pid in pids:
                retry = tobiko.retry(timeout=timeout, interval=interval)
                for _ in retry:
                    LOG.debug(f'Check if {pid} has been terminated on {host}')
                    if self.is_destroyed(pid, command_filter, host):
                        LOG.debug(f'Process {pid} finished on {host}')
                        break

    def is_destroyed(self, pid, command_filter, hostname):
        '''Check if process has been terminated

        :param pid: Process ID to check if exist and handles specific command
        :type pid: int
        :param command_filter: Patter to be found in process command details
        :type command_filter: string
        :param hostname: Hostname of the node to look for PID on
        :type hostname: string
        '''
        host = topology.get_openstack_node(hostname=hostname)
        processes = sh.list_processes(ssh_client=host.ssh_client)
        process = processes.with_attributes(pid=pid)
        process_destroyed = False
        if not process:
            LOG.debug(f'No PID {pid} has been found in process list')
            process_destroyed = True
        else:
            try:
                command = sh.execute(f'cat /proc/{pid}/cmdline',
                                     ssh_client=host.ssh_client)
                if command_filter not in command.stdout:
                    LOG.debug(f'Different process with same PID {pid} exist')
                    process_destroyed = True
            except sh.ShellCommandFailed:
                LOG.debug(f'Process {pid} has been terminated right after the'
                          f' process list has been collected')
                process_destroyed = True
        return process_destroyed


class DHCPAgentTest(BaseAgentTest):

    agent_name = neutron.DHCP_AGENT

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(stacks.CirrosServerStackFixture)

    def test_restart_dhcp_agent(self):
        '''Test that dnsmasq processes are not broken after DHCP agent restart

        Dnsmasq processes should be restarted once DHCP agent is returned
        to active state.
        '''
        self.agents = neutron.list_dhcp_agent_hosting_network(
            self.stack.network)
        self.assertNotEqual(
            [], self.agents, "No DHCP agent found serving network "
            f"'{self.stack.network}'")
        pids = self.get_cmd_pids("dnsmasq", self.stack.network)

        self.restart_agent()

        self.wait_processes_destroyed(self.stack.network, pids)
        new_pids = self.get_cmd_pids("dnsmasq", self.stack.network)
        self.assertNotEqual(pids, new_pids)

    def test_dhcp_lease_served_when_dhcp_agent_down(self):
        '''Test that DHCP lease is correctly served when DHCP agent is down

        Make sure that the VM will receive IP address after the reboot.
        DHCP agent should be down during the VM reboot. VM should receive
        the same IP address that was assigned to it before the reboot.
        '''
        ping.ping_until_received(self.stack.ip_address).assert_replied()

        self.agents = neutron.list_dhcp_agent_hosting_network(
            self.stack.network)
        self.assertNotEqual(
            [], self.agents, "No DHCP agent found serving network "
            f"'{self.stack.network}'")
        pids = self.get_cmd_pids("dnsmasq", self.stack.network)
        self.stop_agent()

        nova.shutoff_server(self.stack.server_id)
        nova.activate_server(self.stack.server_id)
        ping.ping_until_received(self.stack.ip_address).assert_replied()

        self.start_agent()
        self.wait_processes_destroyed(self.stack.network, pids)
        new_pids = self.get_cmd_pids("dnsmasq", self.stack.network)
        self.assertNotEqual(pids, new_pids)


class L3AgentTest(BaseAgentTest):

    agent_name = neutron.L3_AGENT

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(stacks.CirrosPeerServerStackFixture)
    ha_stack = tobiko.required_fixture(stacks.L3haServerStackFixture)

    def setUp(self):
        super(L3AgentTest, self).setUp()
        self.router_id = self.stack.network_stack.gateway_id

    def wait_for_active_ha_l3_agent(self) -> AgentType:
        ha_router_id = self.ha_stack.network_stack.gateway_id
        for attempt in tobiko.retry(timeout=180., interval=5.):
            agents = neutron.list_l3_agent_hosting_routers(ha_router_id)
            try:
                active_agent = agents.with_items(ha_state='active').unique
                break
            except (tobiko.MultipleObjectsFound, tobiko.ObjectNotFound):
                attempt.check_limits()
                continue

        return active_agent

    # Note- Sleep(30 sec) to make sure the L3 agent has time to
    # fully provision all the resources - rhbz#2133743
    def start_agent(self, hosts: typing.Optional[typing.List[str]] = None):
        super(L3AgentTest, self).start_agent(hosts)
        time.sleep(30)

    @neutron.skip_if_missing_networking_extensions('l3-ha')
    @neutron.skip_if_missing_networking_extensions('l3_agent_scheduler')
    def test_keepalived_after_l3_agent_restart(self):
        """Verifies that keepalived survives restart of L3 agents

        Keepalived should keep the same process IDs after L3 agents have been
        restarted
        """
        self.agents = [self.wait_for_active_ha_l3_agent()]
        ha_router_id = self.ha_stack.network_stack.gateway_id
        pids = self.get_cmd_pids('keepalived', ha_router_id,
                                 min_pids_per_host=2)
        self.stop_agent()
        self.start_agent()
        self.agents = [self.wait_for_active_ha_l3_agent()]
        self.assertEqual(pids,
                         self.get_cmd_pids('keepalived',
                                           ha_router_id,
                                           min_pids_per_host=2))

    @neutron.skip_if_missing_networking_extensions('l3-ha')
    @neutron.skip_if_missing_networking_extensions('l3_agent_scheduler')
    def test_keepalived_failover(self):
        ha_router_id = self.ha_stack.network_stack.gateway_id
        self.agents = [self.wait_for_active_ha_l3_agent()]
        keepalived_pids = self.get_cmd_pids('keepalived',
                                            ha_router_id,
                                            min_pids_per_host=2)
        ping.ping_until_received(self.ha_stack.ip_address).assert_replied()
        active_agent_host = self.agents[0]['host']

        # Need to make sure that 'keepalived-state-change' process is UP
        # before we will kill 'keepalived' process as it can break the agent
        # status otherwise. So will check that keepalived pids are equal for
        # two attemts of listing them
        ka_state_cmd = f'neutron-keepalived-state-change.*{ha_router_id}'
        ka_state_pids = {}
        for _ in tobiko.retry(timeout=120., interval=5.):
            new_ka_state_pids = self.get_cmd_pids('/usr/bin/python',
                                                  ka_state_cmd,
                                                  min_pids_per_host=1)
            if ka_state_pids == new_ka_state_pids:
                break
            else:
                ka_state_pids = new_ka_state_pids

        self.kill_pids(active_agent_host, keepalived_pids[active_agent_host])
        ping.ping_until_received(self.ha_stack.ip_address).assert_replied()

        # Need to make sure that 'keepalived' is spawned back after it has
        # been killed
        self.assertNotEqual(keepalived_pids,
                            self.get_cmd_pids('keepalived',
                                              ha_router_id,
                                              min_pids_per_host=2))

    @neutron.skip_if_missing_networking_extensions('l3_agent_scheduler')
    def test_metadata_haproxy_during_stop_L3_agent(self):
        self.agents = neutron.list_l3_agent_hosting_routers(self.router_id)
        pids = self.get_cmd_pids("haproxy", self.router_id)
        self.assertNotEqual(len(pids), 0)
        self.stop_agent()

        # Now check if haproxy processes are still run and have got same pids
        # like before dhcp agent's stop
        self.assertEqual(pids, self.get_cmd_pids("haproxy", self.router_id))

        self.start_agent()

        # And finally check if haproxy processes are still run and have got
        # same pids like at the beginning of the test
        self.assertEqual(pids, self.get_cmd_pids("haproxy", self.router_id))

    def _is_radvd_process_expected(self):
        stateless_modes = ['slaac', 'dhcpv6-stateless']
        ipv6_ra_mode = self.stack.network_stack.ipv6_subnet_details.get(
            'ipv6_ra_mode')
        ipv6_address_mode = self.stack.network_stack.ipv6_subnet_details.get(
            'ipv6_address_mode')
        if not self.stack.network_stack.ipv6_subnet_details.get('cidr'):
            return False
        if (ipv6_ra_mode not in stateless_modes or
                ipv6_address_mode not in stateless_modes):
            return False
        return True

    def test_radvd_during_stop_l3_agent(self):
        os_topology = topology.get_openstack_topology()
        if os_topology.has_containers:
            self.skip("Radvd process is currently run directly in "
                      "neutron-l3-agent container so it will be always killed "
                      "when neutron-l3-agent container is killed and this "
                      "test is not needed")

        if not self._is_radvd_process_expected():
            self.skip("Radvd process is not expected to be run on router %s" %
                      self.router_id)

        self.agents = neutron.list_l3_agent_hosting_routers(self.router_id)
        pids = self.get_cmd_pids("radvd", self.router_id)
        self.stop_agent()
        # Now check if radvd processes are still run and have got same pids
        # like before dhcp agent's stop
        self.assertEqual(pids, self.get_cmd_pids("radvd", self.router_id))

        self.start_agent()

        # And finally check if dnsmasq processes are still run and have got
        # same pids like at the beginning of the test
        self.assertEqual(pids, self.get_cmd_pids("radvd", self.router_id))


class OpenVSwitchAgentTest(BaseAgentTest):

    agent_name = neutron.OPENVSWITCH_AGENT

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(stacks.CirrosServerStackFixture)

    def get_agent_from_host(self, hypervisor_hostname):
        # pylint: disable=not-an-iterable
        short_name = tobiko.get_short_hostname(hypervisor_hostname)
        for agent in self.agents:
            if short_name == tobiko.get_short_hostname(agent['host']):
                return agent
        raise neutron.AgentNotFoundOnHost(agent_type=neutron.OPENVSWITCH_AGENT,
                                          host=hypervisor_hostname)

    def test_vm_reachability_during_stop_ovs_agent(self):
        # Check if vm is reachable before stopping service
        self.start_agent()
        ping.ping_until_received(self.stack.ip_address).assert_replied()

        # Check if vm is reachable after stopping service
        self.stop_agent(hosts=[self.stack.hypervisor_hostname])
        ping.ping_until_received(self.stack.ip_address).assert_replied()


class OvnControllerTest(BaseAgentTest):

    agent_name = neutron.OVN_CONTROLLER

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(stacks.CirrosServerStackFixture)

    def setUp(self):
        super(OvnControllerTest, self).setUp()
        self.get_ovn_agents_from_containers()
        # Ensure that stack is really created to avoid VM error due to dead
        # agents
        ping.ping_until_received(self.stack.ip_address).assert_replied()

    def _get_ovn_controller_pid(self, ssh_client):
        for directory in ('ovn', 'openvswitch'):
            try:
                return sh.execute(f'{self.container_runtime_name} exec '
                                  f'-uroot {self.container_name} cat '
                                  f'/run/{directory}/ovn-controller.pid',
                                  ssh_client=ssh_client,
                                  sudo=True).stdout.splitlines()[0]
            except sh.ShellCommandFailed:
                LOG.debug(f'/run/{directory}/ovn-controller.pid cannot '
                          f'be accessed')

    def kill_ovn_controller(self,
                            hosts: typing.Optional[typing.List[str]] = None,
                            timeout=60, interval=5):
        '''Stop OVN controller container by killing ovn-controller process
        running into it

        Docker/Podman service should restart it automatically

        :parm hosts: List of hostnames to stop agent on
        :type hosts: list of strings
        :param timeout: Time to wait OVN controller is recovered
        :type timeout: int
        :param interval: Time to wait between attempts
        :type interval: int
        '''
        hosts = hosts or self.hosts
        self.assertNotEqual([], hosts, "Host list is empty")

        if self.container_name == '':
            self.container_name = self.get_agent_container_name(
                self.agent_name)

        if not self.container_name:
            self.skipTest(f"Missing container(s): '{self.container_name}'")

        for host in hosts:
            node = topology.get_openstack_node(hostname=host)
            if not node.ssh_client:
                LOG.debug(f'Host {host} is probably an OCP worker in '
                          f'the Podified environment. SSH to that kind of '
                          f'nodes is currently not supported.')
                continue

            ssh_client = node.ssh_client
            pid = self._get_ovn_controller_pid(ssh_client)
            self.assertIsNotNone(pid)
            LOG.debug(f'Killing process {pid} from container '
                      f'{self.container_name} on host {host}')
            # Schedule auto-restart of service at the end of this test case
            self.addCleanup(self.start_agent, hosts=[host, ])
            try:
                sh.execute(f'{self.container_runtime_name} exec -uroot '
                           f'{self.container_name} kill {pid}',
                           ssh_client=ssh_client,
                           sudo=True)
            except sh.ShellCommandFailed as e:
                if "exit status is 137" not in e.message:
                    raise
                else:
                    LOG.exception("Error 137 when killing the ovn-controller "
                                  "process is acceptable")
            LOG.debug(f'Container {self.container_name} has been killed '
                      f"on host '{host}'...")

            # Verify the container is restarted automatically
            for attempt in tobiko.retry(timeout=timeout, interval=interval):
                search_running_ovn_cont = (f"{self.container_runtime_name} ps "
                                           "--format '{{.Names}}'"
                                           f" -f name={self.container_name}")
                output = sh.execute(search_running_ovn_cont,
                                    ssh_client=ssh_client,
                                    sudo=True).stdout.splitlines()

                if self.container_name in output:
                    LOG.debug(f'{self.container_name} successfully restarted')
                    break
                attempt.check_limits()

    def test_restart_ovn_controller(self):
        '''Test that OVN controller agents can be restarted successfully
        '''
        self.stop_agent()
        ping.ping_until_received(self.stack.ip_address).assert_replied()

        self.start_agent()
        ping.ping_until_received(self.stack.ip_address).assert_replied()

    def test_kill_ovn_controller(self):
        '''Test that OVN controller container is restarted automatically after
        ovn-controller process running into it was killed
        '''
        self.kill_ovn_controller()

    @podified.skip_if_not_podified
    def test_delete_ovn_controller_podified(self):
        '''Test that OVN controller pods can be delete and create
        successfully in controlplane
        '''
        # Initial names of pods
        ovn_ctl_ovs_names = _openshift.get_pod_names(
                labels={'service': 'ovn-controller-ovs'})
        ovn_ctl_names = _openshift.get_pod_names(
                labels={'service': 'ovn-controller'})
        # Delete pods
        _openshift.delete_pods(labels={'service': 'ovn-controller-ovs'})
        _openshift.delete_pods(labels={'service': 'ovn-controller'})
        # Check during creation
        for attempt in tobiko.retry(timeout=20, interval=5):
            ovn_ctl_ovs_end = _openshift.get_pod_names(
                    labels={'service': 'ovn-controller-ovs'})
            ovn_ctl_end = _openshift.get_pod_names(
                    labels={'service': 'ovn-controller'})
            try:
                self.assertNotEqual(sorted(ovn_ctl_ovs_names),
                                    sorted(ovn_ctl_ovs_end))
                self.assertNotEqual(sorted(ovn_ctl_names),
                                    sorted(ovn_ctl_end))
                break
            except (_openshift.oc.model.OpenShiftPythonException,
                    AssertionError):
                if attempt.is_last:
                    LOG.error('Failure: pod was not deleted')
                    raise
                LOG.warning('Failed to delete pods.Try again...')

        ping.ping_until_received(self.stack.ip_address).assert_replied()

        # Note: TODO need to implement new ping
        # validations (snat, ping between VMs, ...)

    @podified.skip_if_not_podified
    def test_kill_ovn_controller_podified(self):
        '''Test that OVN controller container is restarted automatically after
        ovn-controller process running into it was killed
        '''
        # controlplane
        # number of pods:
        ovn_ctl_ovs_num = _openshift.get_pod_count(
                labels={'service': 'ovn-controller-ovs'})
        ovn_ctl_num = _openshift.get_pod_count(
                labels={'service': 'ovn-controller'})
        # kill services:
        for ovn_ctl_ovs_pod in _openshift.get_pods(
                labels={'service': 'ovn-controller-ovs'}):
            ovn_ctl_ovs_pod.execute(['sh', '-c', 'killall ovsdb-server'])
            LOG.info('%s was killed', ovn_ctl_ovs_pod)
        for ovn_ctl_pod in _openshift.get_pods(
                labels={'service': 'ovn-controller'}):
            ovn_ctl_pod.execute(['sh', '-c', 'killall ovn-controller'])
            LOG.info('%s was killed', ovn_ctl_pod)
        # After killing  ovn-controller pods, it may take from 1 sec to 60 sec
        # to recover all ovn-controller pods.
        # Check ovn-controller pods
        for attempt in tobiko.retry(timeout=60, interval=5):
            try:
                ovn_ctl_ovs_end = _openshift.get_pod_count(
                        labels={'service': 'ovn-controller-ovs'})
                ovn_ctl_end = _openshift.get_pod_count(
                        labels={'service': 'ovn-controller'})
                self.assertEqual(ovn_ctl_ovs_num, ovn_ctl_ovs_end)
                self.assertEqual(ovn_ctl_num, ovn_ctl_end)
                for ovn_ctl_ovs_pod in _openshift.get_pods(
                        labels={'service': 'ovn-controller-ovs'}):
                    ovsdb_server_pid = ovn_ctl_ovs_pod.execute(
                            ['sh', '-c', 'echo $(pidof ovsdb-server)']
                            ).out().strip()
                    self.assertTrue(ovsdb_server_pid.isnumeric())
                for ovn_ctl_pod in _openshift.get_pods(
                        labels={'service': 'ovn-controller'}):
                    ovn_controller_pid = ovn_ctl_pod.execute(
                            ['sh', '-c', 'echo $(pidof ovn-controller)']
                            ).out().strip()
                    self.assertTrue(ovn_controller_pid.isnumeric())
                break
            except (_openshift.oc.model.OpenShiftPythonException,
                    AssertionError):
                if attempt.is_last:
                    LOG.error('Failed to verify ovn-controller pods')
                    raise
                LOG.warning('Failed to verify ovn-controller pods.Try again..')
        # edpm nodes
        self.kill_ovn_controller()

        ping.ping_until_received(self.stack.ip_address).assert_replied()
        # Note: TODO need to implement new ping
        # validations (snat, ping between VMs, ...)

    def test_restart_ovn_controller_containers(self):
        '''Test that OVN controller containers can be restarted successfully
        '''
        self.restart_agent_container()
        ping.ping_until_received(self.stack.ip_address).assert_replied()


class MetadataAgentTest(BaseAgentTest):

    #: Resources stack with Nova server to send messages to
    stack = tobiko.required_fixture(stacks.CirrosServerStackFixture)

    agent_name = neutron.METADATA_AGENT

    def wait_for_metadata_status(self, count=None, timeout=60., interval=2.,
                                 is_reachable: typing.Optional[bool] = None):
        for attempt in tobiko.retry(timeout=timeout, interval=interval,
                                    count=count):
            if is_reachable is not None:
                try:
                    self.assert_metadata_is_reachable(is_reachable)
                except self.failureException:
                    # re-raises failureException when reaching retry limits
                    attempt.check_limits()
                else:
                    break

    def assert_metadata_is_reachable(self, is_reachable: bool,
                                     metadata_url: str = None):
        """Test if metadata agent is acting as proxy to nova metadata

        Expected response code from metadata agent is "HTTP/1.1 200 OK"
        if the agent is working. "HTTP/1.0 503 Service Unavailable" or
        exit_status=7 otherwise.
        All other HTTP statuses and exit codes are considered failures.
        """
        if is_reachable not in [True, False]:
            raise TypeError("'is_reachable' parameter is not a bool: "
                            f"{is_reachable!r}")
        metadata_url = (metadata_url or
                        'http://%s/latest/meta-data/' % neutron.METADATA_IPv4)

        try:
            result = sh.execute(f"curl '{metadata_url}' -I",
                                ssh_client=self.stack.ssh_client)
        except sh.ShellCommandFailed as ex:
            # Cant reach the server
            self.assertFalse(is_reachable,
                             "Metadata server not reached from Nova server:\n"
                             f"exit_status={ex.exit_status}\n"
                             f"{ex.stderr}")
            self.assertEqual(7, ex.exit_status,
                             f"Unexpected Curl exit status: {ex.exit_status}\n"
                             f"{ex.stderr}")
        else:
            # Command has succeeded, let parse the HTTP status
            curl_output = result.stdout.strip()
            LOG.debug(f"Remote HTTP server replied:\n{curl_output}")
            http_status = parse_http_status(curl_output=curl_output)
            if is_reachable:
                self.assertEqual(
                    200, http_status,
                    "Metadata server not reached from Nova server:\n"
                    f"{curl_output}")
            else:
                self.assertEqual(
                    503, http_status,
                    "Metadata server reached from Nova server:\n"
                    f"{curl_output}")

    def test_metadata_service_restart(self):
        # Ensure service is up
        self.start_agent()
        self.wait_for_metadata_status(is_reachable=True)

        # Ensure the servive gets down
        self.stop_agent()
        self.wait_for_metadata_status(is_reachable=False)

        # Ensure service gets up again
        self.start_agent()
        self.wait_for_metadata_status(is_reachable=True)

    def test_vm_reachability_when_metadata_agent_is_down(self):
        self.stop_agent()
        self.wait_for_metadata_status(is_reachable=False)
        ping.ping_until_received(self.stack.ip_address).assert_replied()
        self.start_agent()
        self.wait_for_metadata_status(is_reachable=True)

    def test_restart_metadata_containers(self):
        self.restart_agent_container()
        self.wait_for_metadata_status(is_reachable=True)


# TODO(eolivare): these tests will always be skipped on OSP13 because 'agent
# list' requests return empty list with OVN+OSP13
# Search for the corresponding container instead of the networking agent
class OvnMetadataAgentTest(MetadataAgentTest):

    agent_name = neutron.NEUTRON_OVN_METADATA_AGENT

    def setUp(self):
        self.get_ovn_agents_from_containers()
        super(OvnMetadataAgentTest, self).setUp()

    @classmethod
    def setUpClass(cls):
        super(OvnMetadataAgentTest, cls).setUpClass()
        if not cls.agents:
            # Let's check if that is maybe older version with networking-ovn
            cls.agents: AgentListType = neutron.list_networking_agents(
                binary=neutron.OVN_METADATA_AGENT)


def parse_http_status(curl_output: str) -> int:
    http_head = curl_output.split('\n', 1)[0]
    return int(http_head.split(' ', 2)[1])
