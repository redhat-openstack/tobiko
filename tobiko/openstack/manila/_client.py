# Copyright 2023 Red Hat
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

from manilaclient.v2 import client as manilaclient
from manilaclient import exceptions
from oslo_log import log

import tobiko
from tobiko import config
from tobiko.openstack import keystone
from tobiko.openstack import _client
from tobiko.openstack.manila import _exceptions

LOG = log.getLogger(__name__)
CONF = config.CONF


class ManilaClientFixture(_client.OpenstackClientFixture):

    def init_client(self, session):
        cacert = (session.cert or CONF.tobiko.tripleo.undercloud_cacert_file
                  if 'https://' in session.auth.auth_url
                  else None)
        return manilaclient.Client(session=session, cacert=cacert)


class ManilaClientManager(_client.OpenstackClientManager):

    def create_client(self, session):
        return ManilaClientFixture(session=session)


CLIENTS = ManilaClientManager()


@keystone.skip_if_missing_service(name='manila')
def manila_client(obj=None):
    obj = obj or default_manila_client()
    if tobiko.is_fixture(obj):
        obj = tobiko.setup_fixture(obj).client
    return tobiko.check_valid_type(obj, manilaclient.Client)


def default_manila_client():
    return get_manila_client()


def get_manila_client(session=None, shared=True, init_client=None,
                      manager=None):
    manager = manager or CLIENTS
    fixture = manager.get_client(session=session, shared=shared,
                                 init_client=init_client)
    return manila_client(fixture)


def create_share(share_protocol=None, size=None, client=None, **kwargs):
    share_protocol = share_protocol or CONF.tobiko.manila.share_protocol
    share_size = size or CONF.tobiko.manila.size
    return manila_client(client).shares.create(
        share_proto=share_protocol, size=share_size, return_raw=True,
        **kwargs)


def list_shares(client=None, **kwargs):
    return manila_client(client).shares.list(return_raw=True, **kwargs)


def delete_share(share_id, client=None, **kwargs):
    try:
        manila_client(client).shares.delete(share_id, **kwargs)
    except exceptions.NotFound:
        LOG.debug(f'Share {share_id} was not found')
        return False
    else:
        LOG.debug(f'Share {share_id} was deleted successfully')
        return True


def extend_share(share_id, new_size, client=None):
    return manila_client(client).shares.extend(share_id, new_size)


def get_share(share_id, client=None):
    try:
        return manila_client(client).shares.get(share_id, return_raw=True)
    except exceptions.NotFound as ex:
        raise _exceptions.ShareNotFound(id=share_id) from ex


def get_shares_by_name(share_name, client=None):
    share_list = list_shares(client=client)
    shares = [
        s for s in share_list if s['name'] == share_name
    ]
    return shares


def list_share_types(client=None):
    return manila_client(client).share_types.list()


def create_share_type(name, spec_driver_handles_share_servers,
                      client=None):
    return manila_client(client).share_types.create(
        name, spec_driver_handles_share_servers)


def ensure_default_share_type_exists(client=None):
    name = CONF.tobiko.manila.default_share_type_name
    dhss = CONF.tobiko.manila.spec_driver_handles_share_servers
    for share_type in list_share_types(client=client):
        if share_type.name == name:
            return
    create_share_type(name, dhss, client=client)
