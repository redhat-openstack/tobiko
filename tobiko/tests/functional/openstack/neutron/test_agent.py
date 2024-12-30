# Copyright (c) 2022 Red Hat, Inc.
#
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

import os

import testtools

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import neutron
from tobiko.openstack import tests
from tobiko.openstack import stacks
from tobiko.shell import sh


@keystone.skip_unless_has_keystone_credentials()
class AgentTest(testtools.TestCase):

    def test_skip_if_missing_agents(self, count=1, should_skip=False,
                                    **params):
        if should_skip:
            expected_exception = self.skipException
        else:
            expected_exception = self.failureException

        @neutron.skip_if_missing_networking_agents(count=count, **params)
        def method():
            raise self.fail('Not skipped')

        exception = self.assertRaises(expected_exception, method)
        if should_skip:
            agents = neutron.list_agents(**params)
            message = "missing {!r} agent(s)".format(count - len(agents))
            if params:
                message += " with {!s}".format(
                    ','.join('{!s}={!r}'.format(k, v)
                             for k, v in params.items()))
            self.assertEqual(message, str(exception))
        else:
            self.assertEqual('Not skipped', str(exception))

    def test_skip_if_missing_agents_with_no_agents(self):
        self.test_skip_if_missing_agents(binary='never-never-land',
                                         should_skip=True)

    def test_skip_if_missing_agents_with_big_count(self):
        self.test_skip_if_missing_agents(count=1000000,
                                         should_skip=True)

    def test_neutron_agents_are_alive(self):
        agents = tests.test_neutron_agents_are_alive()
        # check has agents and they are all alive
        self.assertNotEqual([], agents)
        self.assertNotEqual([], agents.with_items(alive=True))

    def test_find_agents_with_binary(self):
        agent = neutron.list_agents().first
        agents = neutron.list_agents(binary=agent['binary'])
        self.assertIn(agent['id'], {a['id'] for a in agents})


class GetL3AgentModeTest(testtools.TestCase):

    @property
    def connection(self) -> sh.ShellConnection:
        return sh.local_shell_connection()

    def create_file(self, text: str) -> str:
        temp_dir = self.connection.make_temp_dir()
        temp_file = os.path.join(temp_dir, 'l3_agent.ini')
        with self.connection.open_file(temp_file, 'wt') as fd:
            fd.write(text)
        return temp_file

    def test_get_l3_agent_mode(self):
        text = """
        agent_mode=dvr
        """
        l3_agent_conf_path = self.create_file(text=text)
        result = neutron.get_l3_agent_mode(
            l3_agent_conf_path=l3_agent_conf_path,
            connection=self.connection)
        self.assertEqual('dvr', result)

    def test_get_l3_agent_mode_with_empty(self):
        l3_agent_conf_path = self.create_file(text='')
        result = neutron.get_l3_agent_mode(
            l3_agent_conf_path=l3_agent_conf_path,
            connection=self.connection)
        self.assertEqual('legacy', result)

    def test_get_l3_agent_mode_with_section(self):
        text = """
        [DEFAULT]
        agent_mode=dvr_no_external
        """
        l3_agent_conf_path = self.create_file(text=text)
        result = neutron.get_l3_agent_mode(
            l3_agent_conf_path=l3_agent_conf_path,
            connection=self.connection)
        self.assertEqual('dvr_no_external', result)

    def test_get_l3_agent_mode_with_wrong_section(self):
        text = """
        [wrong-section]
        agent_mode=dvr
        """
        l3_agent_conf_path = self.create_file(text=text)
        result = neutron.get_l3_agent_mode(
            l3_agent_conf_path=l3_agent_conf_path,
            connection=self.connection)
        self.assertEqual('legacy', result)

    def test_get_l3_agent_mode_with_tricky_option(self):
        text = """
        agent_mode_2=dvr
        """
        l3_agent_conf_path = self.create_file(text=text)
        result = neutron.get_l3_agent_mode(
            l3_agent_conf_path=l3_agent_conf_path,
            connection=self.connection)
        self.assertEqual('legacy', result)


class SSHGetL3AgentModeTest(GetL3AgentModeTest):

    server_stack = tobiko.required_fixture(
        stacks.AdvancedServerStackFixture)

    @property
    def connection(self) -> sh.SSHShellConnection:
        connection = sh.shell_connection()
        if isinstance(connection, sh.SSHShellConnection):
            return connection
        return self.server_stack.connection
