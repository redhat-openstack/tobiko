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

import abc
import typing

from oslo_log import log

import tobiko
from tobiko import config


LOG = log.getLogger(__name__)


class ResourceFixture(tobiko.SharedFixture, abc.ABC):
    """Base class for fixtures intended to manage Openstack resources not
    created using Heat, but with openstacksdk or other component clients (such
    as neutronclient, novaclient, manilaclient, etc).
    Those resources will be shared by multiple tests and are not cleaned up
    when the tobiko execution ends.

    Child classes must define the following common attributes:
    _resource: the type of resource that the child class actually manages
    (server, network, loadbalancer, manila share, etc) initialized to None.
    _not_found_exception_tuple: (tuple of) type of exceptions that the
    resource_find method could raise in case of not finding the resource.

    Child classes must define any other attributes required by the
    resource_create, resource_delete and resource_find methods. Examples:
    prefixes and default_prefixlen are needed for subnet_pools; description and
    rules are needed for secutiry_groups; etc.

    Child classes must define the resource_create, resource_delete and
    resource_find methods. In case of resource_create and resource_find, they
    should return an object with the type defined for self._resouce.

    Child classes may optionally implement simple properties to access to
    resource_id and resource using a more representative name (these properties
    will simply return self.resource_id or self.resource, respectively).
    """

    name: typing.Optional[str] = None
    _resource: typing.Optional[object] = None
    _not_found_exception_tuple: typing.Type[Exception] = (Exception)

    def __init__(self):
        self.name = self.fixture_name
        super().__init__()

    @property
    def resource_id(self):
        if self.resource:
            return self._resource['id']

    @property
    def resource(self):
        if not self._resource:
            try:
                self._resource = self.resource_find()
            except self._not_found_exception_tuple:
                LOG.debug("%r not found.", self.name)
                self._resource = None
        return self._resource

    @abc.abstractmethod
    def resource_create(self):
        pass

    @abc.abstractmethod
    def resource_find(self):
        pass

    @abc.abstractmethod
    def resource_delete(self):
        pass

    def setup_fixture(self):
        if config.get_bool_env('TOBIKO_PREVENT_CREATE'):
            LOG.debug("%r should have been already created: %r",
                      self.name,
                      self.resource)
        else:
            self.try_create_resource()

        if self.resource:
            tobiko.addme_to_shared_resource(__name__, self.name)

    def try_create_resource(self):
        if not self.resource:
            self._resource = self.resource_create()

    def cleanup_fixture(self):
        tests_using_resource = tobiko.removeme_from_shared_resource(__name__,
                                                                    self.name)
        if len(tests_using_resource) == 0:
            self._cleanup_resource()
        else:
            LOG.info(f'{self.name} ResourceFixture not deleted because some '
                     f'tests are still using it: {tests_using_resource}')

    def _cleanup_resource(self):
        resource_id = self.resource_id
        if resource_id:
            LOG.debug('Deleting %r (%r)...', self.name, resource_id)
            self.resource_delete()
            LOG.debug('%r (%r) deleted.', self.name, resource_id)
            self._resource = None
