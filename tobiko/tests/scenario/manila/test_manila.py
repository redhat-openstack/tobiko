# Copyright (c) 2023 Red Hat, Inc.
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

import testtools
from oslo_log import log

import tobiko
from tobiko import config
from tobiko.openstack import keystone
from tobiko.openstack import manila
from tobiko.openstack import stacks

LOG = log.getLogger(__name__)
CONF = config.CONF


@keystone.skip_if_missing_service(name='manila')
class ManilaApiTestCase(testtools.TestCase):
    """Manila scenario tests.

    Create a manila share.
    Check it reaches status 'available'.
    After upgrade/disruptions/etc, check the share is still valid and it can be
    extended.
    """
    share_fixture = tobiko.required_fixture(stacks.ManilaShareFixture)
    share = None

    def setUp(self):
        super(ManilaApiTestCase, self).setUp()
        self.share = self.share_fixture.share

    @config.skip_if_prevent_create()
    def test_1_create_share(self):
        manila.wait_for_share_status(self.share['id'])
        found_shares = manila.get_shares_by_name(self.share['name'])
        self.assertEqual(len(found_shares), 1)

    @config.skip_unless_prevent_create()
    def test_2_extend_share(self):
        share_id = self.share['id']
        manila.extend_share(share_id, new_size=CONF.tobiko.manila.size + 1)
        manila.wait_for_share_status(share_id)
        share_size = manila.get_share(share_id)['size']
        self.assertEqual(CONF.tobiko.manila.size + 1, share_size)
