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

from collections import abc
import time
from unittest import mock

from heatclient.v1 import client as heatclient
from heatclient import exc

import tobiko
from tobiko.openstack import heat
from tobiko.openstack.heat import _stack
from tobiko.openstack import keystone
from tobiko.tests.unit import openstack


class MyStack(heat.HeatStackFixture):
    template = heat.heat_template({'template': 'from-class'})


class MyStackWithStackName(MyStack):
    stack_name = 'stack.name.from.class'


class MyStackWithParameters(MyStack):
    parameters = heat.heat_stack_parameters({'param': 'from-class'})


class MyStackWithWaitInterval(MyStack):
    wait_interval = 10


class MyTemplateFixture(heat.HeatTemplateFixture):
    template = {'template': 'from-class'}


class MockClient(mock.NonCallableMagicMock):
    pass


class HeatStackFixtureTest(openstack.OpenstackTest):

    def setUp(self):
        super(HeatStackFixtureTest, self).setUp()
        self.patch(heatclient, 'Client', MockClient)

    def test_init(self, fixture_class=MyStack, stack_name=None,
                  template=None, parameters=None, wait_interval=None,
                  client=None):
        stack = fixture_class(stack_name=stack_name, template=template,
                              parameters=parameters,
                              wait_interval=wait_interval, client=client)

        if stack_name:
            self.assertEqual(stack_name, stack.stack_name)
        elif isinstance(fixture_class.stack_name, property):
            self.assertEqual(tobiko.get_fixture_name(stack), stack.stack_name)
        else:
            self.assertEqual(fixture_class.stack_name, stack.stack_name)

        self.check_stack_template(stack=stack, template=template)

        self.assertIsInstance(stack.parameters,
                              _stack.HeatStackParametersFixture)
        self.assertEqual(parameters or getattr(fixture_class.parameters,
                                               'parameters', {}),
                         stack.parameters.parameters)
        self.assertEqual(wait_interval or fixture_class.wait_interval,
                         stack.wait_interval)
        self.assertIs(client or fixture_class.client, stack.client)

    def test_init_with_stack_name(self):
        self.test_init(stack_name='my-stack-name')

    def test_init_with_stack_name_from_class(self):
        self.test_init(fixture_class=MyStackWithStackName)

    def test_init_with_template(self):
        self.test_init(template={'some': 'template'})

    def test_init_with_template_fixture(self):
        self.test_init(template=MyTemplateFixture())

    def test_init_with_parameters(self):
        self.test_init(parameters={'my': 'value'})

    def test_init_with_parameters_from_class(self):
        self.test_init(fixture_class=MyStackWithParameters)

    def test_init_with_wait_interval(self):
        self.test_init(wait_interval=20)

    def test_init_with_wait_interval_from_class(self):
        self.test_init(fixture_class=MyStackWithWaitInterval)

    def test_init_with_client(self):
        session = keystone.get_keystone_session()
        self.test_init(client=heatclient.Client(session=session))

    def test_init_with_client_fixture(self):
        self.test_init(client=heat.HeatClientFixture())

    def test_setup(self, fixture_class=MyStack, template=None,
                   stack_name=None, parameters=None, wait_interval=None,
                   stacks=None, create_conflict=False, call_create=True,
                   call_delete=False, call_sleep=False):
        client = MockClient()
        stacks = stacks or [
            exc.HTTPNotFound,
            mock_stack('CREATE_IN_PROGRESS')]
        client.stacks.get.side_effect = stacks

        if create_conflict:
            client.stacks.create.side_effect = exc.HTTPConflict
        else:
            client.stacks.create.return_value = {
                'stack': {'id': '<stack-id>'}}

        sleep = self.patch(time, 'sleep')
        stack = fixture_class(stack_name=stack_name, parameters=parameters,
                              template=template, wait_interval=wait_interval,
                              client=client)

        stack.setUp()

        self.assertIs(client, stack.client)
        self.assertEqual(wait_interval or fixture_class.wait_interval,
                         stack.wait_interval)
        client.stacks.get.assert_has_calls([mock.call(stack.stack_name,
                                                      resolve_outputs=False)])

        if call_delete:
            client.stacks.delete.assert_called_once_with(stack.stack_id)
        else:
            client.stacks.delete.assert_not_called()

        parameters = (parameters or
                      (fixture_class.parameters and
                       fixture_class.parameters.values) or
                      {})
        self.assertEqual(parameters, stack.parameters.values)
        if call_create:
            client.stacks.create.assert_called_once_with(
                parameters=parameters, stack_name=stack.stack_name,
                template=tobiko.dump_yaml(stack.template.template))
        else:
            client.stacks.create.assert_not_called()

        if call_sleep:
            sleep.assert_called()

    def test_setup_with_stack_name(self):
        self.test_setup(stack_name='my-stack-name')

    def test_setup_with_stack_name_from_class(self):
        self.test_setup(fixture_class=MyStackWithStackName)

    def test_setup_with_template(self):
        self.test_setup(template={'other': 'template'})

    def test_setup_with_template_fixture(self):
        self.test_setup(template=heat.heat_template({'template':
                                                     'from-fixture'}))

    def test_setup_with_template_fixture_type(self):
        self.test_setup(template=MyTemplateFixture)

    def test_setup_with_parameters(self):
        self.test_setup(parameters={'from_init': True})

    def test_setup_with_parameters_from_class(self):
        self.test_setup(fixture_class=MyStackWithParameters)

    def test_setup_with_wait_interval(self):
        self.test_setup(wait_interval=10.)

    def test_setup_with_wait_interval_from_class(self):
        self.test_setup(fixture_class=MyStackWithWaitInterval)

    def test_setup_when_none(self):
        self.test_setup(stacks=[None,
                                mock_stack('CREATE_IN_PROGRESS')])

    def test_setup_when_delete_completed(self):
        self.test_setup(stacks=[mock_stack('DELETE_COMPLETE'),
                                None,
                                mock_stack('CREATE_IN_PROGRESS')])

    def test_setup_when_delete_failed(self):
        self.test_setup(stacks=[mock_stack('DELETE_FAILED'),
                                mock_stack('DELETE_IN_PROGRESS'),
                                mock_stack('DELETE_COMPLETE'),
                                None,
                                mock_stack('CREATE_IN_PROGRESS')],
                        call_delete=True, call_sleep=True)

    def test_setup_when_delete_failed_fast_delete(self):
        self.test_setup(stacks=[mock_stack('DELETE_FAILED'),
                                None,
                                mock_stack('CREATE_IN_PROGRESS')],
                        call_delete=True)

    def test_setup_when_create_complete(self):
        self.test_setup(stacks=[mock_stack('CREATE_COMPLETE')],
                        call_create=False)

    def test_setup_when_create_failed(self):
        self.test_setup(stacks=[mock_stack('CREATE_FAILED'),
                                mock_stack('DELETE_IN_PROGRESS'),
                                mock_stack('DELETE_COMPLETE'),
                                None,
                                mock_stack('CREATE_IN_PROGRESS')],
                        call_delete=True, call_sleep=True)

    def test_setup_when_create_failed_fast_delete(self):
        self.test_setup(stacks=[mock_stack('CREATE_FAILED'),
                                None,
                                mock_stack('CREATE_IN_PROGRESS')],
                        call_delete=True)

    def test_setup_when_create_in_progress(self):
        self.test_setup(stacks=[mock_stack('CREATE_IN_PROGRESS')],
                        call_create=False)

    def test_setup_when_delete_in_progress_then_complete(self):
        self.test_setup(stacks=[mock_stack('DELETE_IN_PROGRESS'),
                                mock_stack('DELETE_COMPLETE'),
                                None,
                                mock_stack('CREATE_IN_PROGRESS')],
                        call_sleep=True)

    def test_setup_when_delete_in_progress_then_failed(self):
        self.test_setup(stacks=[mock_stack('DELETE_IN_PROGRESS'),
                                mock_stack('DELETE_FAILED'),
                                mock_stack('DELETE_COMPLETE'),
                                None,
                                mock_stack('CREATE_IN_PROGRESS')],
                        call_sleep=True, call_delete=True)

    def test_setup_when_create_conflict(self):
        self.test_setup(create_conflict=True)

    def test_setup_when_prevent_to_create_set(self):
        with mock.patch.dict('os.environ', {'TOBIKO_PREVENT_CREATE': 'True'}):
            self.test_setup(stacks=[mock_stack('CREATE_COMPLETE')],
                            call_create=False)

    def test_cleanup(self):
        client = MockClient()
        client.stacks.get.return_value = None
        stack = MyStackWithStackName(client=client)
        stack_name = stack.stack_name
        tobiko.addme_to_shared_resource(
            'tobiko.openstack.heat._stack', stack_name)
        stack.cleanUp()
        client.stacks.delete.assert_called_once_with(stack_name)

    def test_outputs(self):
        stack = mock_stack(status='CREATE_COMPLETE',
                           outputs=[{'output_key': 'key1',
                                     'output_value': 'value1'},
                                    {'output_key': 'key2',
                                     'output_value': 'value2'}])
        client = MockClient()
        client.stacks.get.return_value = stack
        stack_fixture = MyStack(
            template={'outputs': {'key1': {}, 'key2': {}}},
            client=client)

        outputs = stack_fixture.outputs

        self.assertEqual('value1', outputs.key1)
        self.assertEqual('value2', outputs.key2)

    def test_parameters(self):
        stack_fixture = MyStack(
            template={'parameters': {'key1': {}, 'key2': {}}},
            parameters={'key1': 'value1',
                        'key2': 'value2'})

        parameters = stack_fixture.parameters

        self.assertEqual('value1', parameters.key1)
        self.assertEqual('value2', parameters.key2)

    def check_stack_template(self, stack, template):
        expected_template = template or type(stack).template
        if tobiko.is_fixture(expected_template):
            self.assertIs(expected_template, stack.template)
        elif isinstance(expected_template, abc.Mapping):
            self.assertEqual(expected_template, stack.template.template)
        else:
            message = "Unsupported template type: {!r}".format(
                expected_template)
            self.fail(message)


def mock_stack(status, stack_id='<stack-id>', outputs=None):
    return mock.MagicMock(stack_status=status,
                          id=stack_id,
                          outputs=outputs or [])
