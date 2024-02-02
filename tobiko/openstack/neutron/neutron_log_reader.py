# Copyright 2021 Red Hat
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

import ast
import datetime
import re
import typing

from oslo_log import log

import tobiko
from tobiko.openstack import neutron
from tobiko.openstack.neutron import _agent
from tobiko.openstack import topology
from tobiko import podified
from tobiko.shell import files


LOG = log.getLogger(__name__)


class NeutronNovaResponse(typing.NamedTuple):
    hostname: str
    timestamp: float
    name: str
    server_uuid: str
    status: str
    code: int
    tag: str
    line: str

    def __lt__(self, other):
        return self.timestamp < other.timestamp


class NeutronNovaCommonReader(tobiko.SharedFixture):
    log_digger: files.MultihostLogFileDigger
    groups: typing.List[str]
    message_pattern: str
    datetime_pattern: typing.Pattern
    config = tobiko.required_fixture(topology.OpenStackTopologyConfig)
    service_name = neutron.SERVER

    def setup_fixture(self):
        self.datetime_pattern = re.compile(
            self.config.conf.log_datetime_pattern)
        self.log_digger = self.useFixture(
            topology.get_log_file_digger(
                service_name=self.service_name,
                groups=self.groups,
                pattern=self.message_pattern))
        self.read_responses()

    def _get_log_timestamp(self,
                           log_line: str) -> float:
        found = self.datetime_pattern.match(log_line)
        if not found:
            return 0.0
        return datetime.datetime.strptime(
            found.group(1), "%Y-%m-%d %H:%M:%S.%f").timestamp()

    def read_responses(self):
        raise NotImplementedError


class NeutronNovaResponseReader(NeutronNovaCommonReader):
    groups = ['controller']
    message_pattern = r'Nova event response: '
    responses: tobiko.Selection[NeutronNovaResponse]

    def read_responses(self) -> tobiko.Selection[NeutronNovaResponse]:
        # pylint: disable=no-member
        responses = tobiko.Selection[NeutronNovaResponse]()
        message_pattern = re.compile(self.message_pattern)
        for hostname, line in self.log_digger.find_lines(
                new_lines=hasattr(self, 'responses')):
            found = message_pattern.search(line)
            assert found is not None
            response_text = line[found.end():].strip()
            response_data = ast.literal_eval(response_text)
            assert isinstance(response_data, dict)
            response = NeutronNovaResponse(
                hostname=hostname,
                line=line,
                timestamp=self._get_log_timestamp(line[:found.start()]),
                **response_data)
            responses.append(response)
        responses.sort()
        if hasattr(self, 'responses'):
            self.responses.extend(responses)
        else:
            self.responses = responses
        return responses


def read_neutron_nova_responses(
        reader: NeutronNovaResponseReader = None,
        new_lines=True,
        **attributes) \
        -> tobiko.Selection[NeutronNovaResponse]:
    if reader is None:
        reader = tobiko.setup_fixture(NeutronNovaResponseReader)
    responses = reader.read_responses()
    if not new_lines:
        responses = reader.responses
    if attributes and responses:
        responses = responses.with_attributes(**attributes)
    return responses


class UnsupportedDhcpOptionMessage(typing.NamedTuple):
    port_uuid: str
    unsupported_dhcp_option: str
    timestamp: float
    line: str

    def __lt__(self, other):
        return self.timestamp < other.timestamp


@podified.skip_if_podified
@_agent.skip_unless_is_ovn()
class OvnUnsupportedDhcpOptionReader(NeutronNovaCommonReader):
    groups = ['controller']
    message_pattern = (
        'The DHCP option .* on port .* is not suppported by OVN, ignoring it')
    responses: tobiko.Selection[UnsupportedDhcpOptionMessage]

    def read_responses(self) \
            -> tobiko.Selection[UnsupportedDhcpOptionMessage]:
        # pylint: disable=no-member
        def _get_port_uuid(line):
            port_pattern = 'on port (.*) is not suppported by OVN'
            return re.findall(port_pattern, line)[0]

        def _get_dhcp_option(line):
            dhcp_opt_pattern = 'The DHCP option (.*) on port'
            return re.findall(dhcp_opt_pattern, line)[0]

        responses = tobiko.Selection[UnsupportedDhcpOptionMessage]()
        message_pattern = re.compile(self.message_pattern)
        for _, line in self.log_digger.find_lines(
                new_lines=hasattr(self, 'responses')):
            found = message_pattern.search(line)
            assert found is not None
            response = UnsupportedDhcpOptionMessage(
                line=line,
                timestamp=self._get_log_timestamp(line[:found.start()]),
                port_uuid=_get_port_uuid(line),
                unsupported_dhcp_option=_get_dhcp_option(line))
            responses.append(response)
        responses.sort()
        if hasattr(self, 'responses'):
            self.responses.extend(responses)
        else:
            self.responses = responses
        return responses


def assert_ovn_unsupported_dhcp_option_messages(
        reader: OvnUnsupportedDhcpOptionReader = None,
        new_lines=True,
        unsupported_options: typing.Optional[typing.List] = None,
        **attributes):
    if reader is None:
        reader = tobiko.setup_fixture(OvnUnsupportedDhcpOptionReader)
    # find new logs that match the pattern
    responses = reader.read_responses()
    if not new_lines:
        responses = reader.responses
    if attributes and responses:
        responses = responses.with_attributes(**attributes)

    # assert one line matches per unsupported dhcp option
    test_case = tobiko.get_test_case()
    for unsupported_option in unsupported_options or []:
        messages_unsupported_option = responses.with_attributes(
            unsupported_dhcp_option=unsupported_option)
        test_case.assertEqual(1, len(messages_unsupported_option))
        LOG.debug('Found one match for unsupported dhcp option '
                  f'{unsupported_option}')
