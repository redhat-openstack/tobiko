# Copyright (c) 2025 Red Hat, Inc.
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

import typing

from manilaclient.v2.shares import Share
from oslo_log import log

import tobiko
from tobiko.openstack import manila
from tobiko.openstack.base import _fixture as base_fixture

LOG = log.getLogger(__name__)


class ManilaShareFixture(base_fixture.ResourceFixture):

    _resource: typing.Optional[Share] = None
    share_protocol: typing.Optional[str] = None
    size: typing.Optional[int] = None

    def __init__(self, share_protocol=None, size=None):
        super().__init__()
        self.share_protocol = share_protocol or self.share_protocol
        self.size = size or self.size

    @property
    def share_id(self):
        return self.resource_id

    @property
    def share(self):
        return self.resource

    @tobiko.interworker_synched('manila_setup_fixture')
    def try_create_resource(self):
        super().try_create_resource()

    def resource_create(self):
        manila.ensure_default_share_type_exists()
        share = manila.create_share(share_protocol=self.share_protocol,
                                    size=self.size,
                                    name=self.name)
        manila.wait_for_share_status(share['id'])
        LOG.debug(f'Share {share["name"]} was deployed successfully '
                  f'with id {share["id"]}')
        return share

    def resource_delete(self):
        LOG.debug('Deleting Share %r ...', self.name)
        manila.delete_share(self.share_id)
        manila.wait_for_resource_deletion(self.share_id)
        LOG.debug('Share %r deleted.', self.name)

    def resource_find(self):
        found_shares = manila.get_shares_by_name(self.name)
        if len(found_shares) > 1:
            tobiko.fail(f'Unexpected number of shares found: {found_shares}')

        if found_shares:
            LOG.debug("Share %r found.", self.name)
            return found_shares[0]

        # no shares found
        LOG.debug("Share %r not found.", self.name)
