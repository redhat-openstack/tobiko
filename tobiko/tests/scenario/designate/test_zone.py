# Copyright (c) 2023 Red Hat
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

import testtools
from oslo_log import log
import dns.resolver

import tobiko
from tobiko.openstack import keystone
from tobiko.openstack import topology
from tobiko.openstack import stacks
from tobiko.shell import ip
from tobiko import tripleo

LOG = log.getLogger(__name__)


@keystone.skip_if_missing_service(name='designate')
@tripleo.skip_if_missing_undercloud
class DesignateBasicScenarioTest(testtools.TestCase):
    """Designate sanity scenario test.
    In this test we'll create a Zone and A type recordset
    associated to that zone, then we'll check: that SOA,
     NS and A recordsets are listed in "openstack recordset list"
    and we'll also check (using Dig) that the BIND9 server has
     been updated with the same records: SOA, NS and A.
    """

    zone_stack = tobiko.required_fixture(stacks.DesignateZoneStackFixture)

    def setUp(self):
        super(DesignateBasicScenarioTest, self).setUp()
        # Wait for Designate recourses to be active
        self.zone_stack.wait_for_active_recordsets()

    def test_basic_sanity_scenario(self):

        # check that SOA, NS and A recordsets are listed in recordset list
        recordset_list = self.zone_stack.recordset_list
        expected_recordset_types = ["SOA", "NS", "A"]
        actual_recordset_types = [item["type"] for item in recordset_list]
        expected_recordset_types.sort()
        actual_recordset_types.sort()
        self.assertEqual(expected_recordset_types, actual_recordset_types)

        # list all Controller nodes
        nodes = topology.list_openstack_nodes(group='controller')
        valid_dns_ip_list = []

        for node in nodes:
            LOG.debug(node.ssh_parameters.get('hostname'))

            my_resolver = dns.resolver.Resolver()

            controller_ip_list = ip.list_ip_addresses(
                ssh_client=node.ssh_client, ip_version=4, scope='global')
            for dns_ip in controller_ip_list:
                my_resolver.nameservers = [str(dns_ip)]
                try:
                    answerSOA = my_resolver.resolve(
                        'tobiko.openstack.stacks._designate'
                        '.designatezonestackfixture.', 'SOA')
                    answerNS = my_resolver.resolve(
                        'tobiko.openstack.stacks.'
                        '_designate.designatezonestackfixture.', 'NS')
                    answerA = my_resolver.resolve(
                        'record.tobiko.openstack.stacks._designate.'
                        'designatezonestackfixture.', 'A')
                    LOG.debug(f"{answerSOA},{answerNS},{answerA}"
                              f" is stored for a zone")
                    LOG.debug(f"{dns_ip} is a valid DNS server!")
                    valid_dns_ip_list.append(str(dns_ip))
                except (dns.resolver.Timeout, dns.resolver.NXDOMAIN):
                    LOG.warn(f"{dns_ip} is NOT a valid DNS server!")

        self.assertEqual(len(valid_dns_ip_list), len(nodes))
        LOG.debug(f"List of valid BIND9 IPs: {valid_dns_ip_list}")
