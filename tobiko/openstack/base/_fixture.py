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
import collections
import typing

from oslo_log import log

import tobiko
from tobiko import config
from tobiko.openstack import keystone
from tobiko.openstack.neutron import _quota_set as neutron_quota
from tobiko.openstack.nova import _quota_set as nova_quota


LOG = log.getLogger(__name__)


class InvalidFixtureError(tobiko.TobikoException):
    message = "invalid fixture {name!r}"


class BaseResourceFixture(tobiko.SharedFixture):
    """Base class for fixtures both types: those which uses heat stacks and
    those which are not.
    """
    client: keystone.KeystoneClient = None
    project: typing.Optional[str] = None
    user: typing.Optional[str] = None

    def setup_fixture(self):
        self.setup_client()
        self.setup_project()
        self.setup_user()

    def setup_project(self):
        if self.project is None:
            self.project = keystone.get_project_id(session=self.session)

    def setup_user(self):
        if self.user is None:
            self.user = keystone.get_user_id(session=self.session)

    @property
    def session(self):
        return self.setup_client().session

    def setup_client(self) -> keystone.KeystoneClient:
        # returns self.client itself, if the keystone client was already
        # created; else, creates a new keystone client and returns it.
        self.client = keystone.keystone_client(self.client)
        return self.client

    def ensure_quota_limits(self):
        """Ensures quota limits before creating a new stack
        """
        try:
            self.ensure_neutron_quota_limits()
            self.ensure_nova_quota_limits()
        except (nova_quota.EnsureNovaQuotaLimitsError,
                neutron_quota.EnsureNeutronQuotaLimitsError) as ex:
            raise InvalidFixtureError(name=self.fixture_name) from ex

    def ensure_neutron_quota_limits(self):
        required_quota_set = self.neutron_required_quota_set
        if required_quota_set:
            neutron_quota.ensure_neutron_quota_limits(project=self.project,
                                                      **required_quota_set)

    def ensure_nova_quota_limits(self):
        required_quota_set = self.nova_required_quota_set
        if required_quota_set:
            nova_quota.ensure_nova_quota_limits(project=self.project,
                                                user=self.user,
                                                **required_quota_set)

    @property
    def neutron_required_quota_set(self) -> typing.Dict[str, int]:
        return collections.defaultdict(int)

    @property
    def nova_required_quota_set(self) -> typing.Dict[str, int]:
        return collections.defaultdict(int)


class ResourceFixture(BaseResourceFixture, abc.ABC):
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
    rules are needed for security_groups; etc.

    Child classes must define the resource_create, resource_delete and
    resource_find methods. In case of resource_create and resource_find, they
    should return an object with the type defined for self._resource.

    Child classes may optionally implement simple properties to access to
    resource_id and resource using a more representative name (these properties
    will simply return self.resource_id or self.resource, respectively).
    """

    name: typing.Optional[str] = None
    _resource: typing.Optional[object] = None
    _not_found_exception_tuple: typing.Type[Exception] = (Exception)

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
        super().setup_fixture()
        self.name = self.fixture_name
        if config.get_bool_env('TOBIKO_PREVENT_CREATE'):
            LOG.debug("%r should have been already created: %r",
                      self.name,
                      self.resource)
        else:
            self.try_create_resource()

        if self.resource is None:
            tobiko.fail("%r not found!", self.name)
        else:
            tobiko.addme_to_shared_resource(__name__, self.name)

    def try_create_resource(self):
        # Ensure quota limits are OK just in time before start creating
        # a new stack
        self.ensure_quota_limits()
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
