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

from tobiko import config
from tobiko.openstack import keystone
from tobiko.openstack import manila

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
    @classmethod
    def setUpClass(cls):
        if config.get_bool_env('TOBIKO_PREVENT_CREATE'):
            LOG.debug('skipping creation of manila resources')
            cls.share = manila.get_shares_by_name(manila.SHARE_NAME)[0]
        else:
            manila.ensure_default_share_type_exists()
            cls.share = manila.create_share(name=manila.SHARE_NAME)

        manila.wait_for_share_status(cls.share['id'])

    @config.skip_if_prevent_create()
    def test_1_create_share(self):
        self.assertEqual(manila.SHARE_NAME, self.share['name'])

    @config.skip_unless_prevent_create()
    def test_2_extend_share(self):
        share_id = self.share['id']
        manila.extend_share(share_id, new_size=CONF.tobiko.manila.size + 1)
        manila.wait_for_share_status(share_id)
        share_size = manila.get_share(share_id)['size']
        self.assertEqual(CONF.tobiko.manila.size + 1, share_size)
