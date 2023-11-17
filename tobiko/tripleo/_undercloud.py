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

import functools
import json
import os
import typing

from oslo_log import log

import tobiko
from tobiko import config
from tobiko.openstack import keystone
from tobiko import rhosp
from tobiko.shell import ssh
from tobiko.shell import sh


CONF = config.CONF

LOG = log.getLogger(__name__)


def undercloud_ssh_client() -> ssh.SSHClientFixture:
    host_config = undercloud_host_config()
    if not host_config.hostname:
        raise NoSuchUndercloudHostname('No such undercloud hostname')
    return ssh.ssh_client(host=host_config.hostname,
                          **host_config.connect_parameters)


class NoSuchUndercloudHostname(tobiko.TobikoException):
    message = "Undercloud hostname not specified"


class InvalidRCFile(tobiko.TobikoException):
    message = "Invalid RC file: {rcfile}"


@functools.lru_cache()
def fetch_os_env(rcfile: str, *rcfiles: str) -> typing.Dict[str, str]:
    rcfiles = (rcfile,) + rcfiles
    LOG.debug('Fetching OS environment variables from TripleO undercloud '
              f'host files: {",".join(rcfiles)}')
    errors = []
    for rcfile in rcfiles:
        LOG.debug(f'Reading rcfile: {rcfile}...')
        try:
            result = sh.execute(f". {rcfile}; env | grep '^OS_'",
                                ssh_client=undercloud_ssh_client())
        except sh.ShellCommandFailed as ex:
            LOG.debug(f"Unable to get overcloud RC file '{rcfile}' content "
                      f"({ex})")
            errors.append(ex)
        else:
            LOG.debug(f'Parsing environment variables from: {rcfile}...')
            env = {}
            for line in result.stdout.splitlines():
                name, value = line.split('=')
                env[name] = value
            if env:
                env_dump = json.dumps(env, sort_keys=True, indent=4)
                LOG.debug(f'Environment variables read from: {rcfile}:\n'
                          f'{env_dump}')
                return env
    if errors and all("No such file or directory" in error.stderr
                      for error in errors):
        LOG.warning('None of the credentials files were found')
        raise keystone.NoSuchKeystoneCredentials()
    raise InvalidRCFile(rcfile=", ".join(rcfiles))


def load_undercloud_rcfile() -> typing.Dict[str, str]:
    conf = tobiko.tobiko_config().tripleo
    return fetch_os_env(*conf.undercloud_rcfile)


class UndercloudKeystoneCredentialsFixtureBase(
        keystone.KeystoneCredentialsFixture):

    def _get_credentials(self) -> keystone.KeystoneCredentials:
        if not has_undercloud():
            raise keystone.NoSuchKeystoneCredentials()
        return super()._get_credentials()

    def _get_connection(self) -> sh.ShellConnectionType:
        return undercloud_ssh_client()

    def _get_environ(self) -> typing.Dict[str, str]:
        return load_undercloud_rcfile()


class UndercloudCloudsFileKeystoneCredentialsFixture(
        UndercloudKeystoneCredentialsFixtureBase,
        keystone.CloudsFileKeystoneCredentialsFixture):

    @staticmethod
    def _get_default_cloud_name() -> typing.Optional[str]:
        return tobiko.tobiko_config().tripleo.undercloud_cloud_name


class UndercloudEnvironKeystoneCredentialsFixture(
        UndercloudKeystoneCredentialsFixtureBase,
        keystone.EnvironKeystoneCredentialsFixture):
    pass


@functools.lru_cache()
def has_undercloud(min_version: tobiko.VersionType = None,
                   max_version: tobiko.VersionType = None) -> bool:
    try:
        check_undercloud(min_version=min_version,
                         max_version=max_version)
    except (UndercloudNotFound, UndercloudVersionMismatch) as ex:
        LOG.debug(f'TripleO undercloud host not found:\n'
                  f'{ex}')
        return False
    except Exception:
        LOG.exception('Error looking for undercloud host')
        return False
    else:
        LOG.debug('TripleO undercloud host found')
        return True


skip_if_missing_undercloud = tobiko.skip_unless(
    'TripleO undercloud hostname not configured', has_undercloud)


def skip_unlsess_has_undercloud(min_version: tobiko.VersionType = None,
                                max_version: tobiko.VersionType = None):
    return tobiko.skip_on_error(
        reason='TripleO undercloud not found',
        predicate=check_undercloud,
        min_version=min_version,
        max_version=max_version,
        error_type=(UndercloudNotFound, UndercloudVersionMismatch))


class UndecloudHostConfig(tobiko.SharedFixture):

    hostname: typing.Optional[str] = None
    port: typing.Optional[int] = None
    username: typing.Optional[str] = None

    def __init__(self, **kwargs):
        super(UndecloudHostConfig, self).__init__()
        self._connect_parameters = ssh.gather_ssh_connect_parameters(**kwargs)

    def setup_fixture(self):
        self.hostname = CONF.tobiko.tripleo.undercloud_ssh_hostname.strip()
        self.port = CONF.tobiko.tripleo.undercloud_ssh_port
        self.username = CONF.tobiko.tripleo.undercloud_ssh_username

    @property
    def key_filename(self) -> typing.List[str]:
        key_filenames: typing.List[str] = []
        conf = tobiko.tobiko_config()
        key_filename = conf.tripleo.undercloud_ssh_key_filename
        if key_filename:
            key_filename = tobiko.tobiko_config_path(key_filename)
            if os.path.isfile(key_filename):
                key_filenames.append(key_filename)
        key_filenames.extend(ssh.list_proxy_jump_key_filenames())
        key_filenames.extend(ssh.list_key_filenames())
        return tobiko.select_uniques(key_filenames)

    @property
    def connect_parameters(self):
        parameters = ssh.gather_ssh_connect_parameters(self)
        parameters.update(self._connect_parameters)
        return parameters


def undercloud_host_config() -> UndecloudHostConfig:
    return tobiko.setup_fixture(UndecloudHostConfig)


def undercloud_keystone_client():
    session = undercloud_keystone_session()
    return keystone.get_keystone_client(session=session)


class UndercloudKeystoneCredentialsFixture(
        UndercloudKeystoneCredentialsFixtureBase,
        keystone.DelegateKeystoneCredentialsFixture):

    @staticmethod
    def _get_delegates() -> typing.List[keystone.KeystoneCredentialsFixture]:
        return [
            tobiko.get_fixture(
                UndercloudCloudsFileKeystoneCredentialsFixture),
            tobiko.get_fixture(
                UndercloudEnvironKeystoneCredentialsFixture)]


def undercloud_keystone_session() -> keystone.KeystoneSession:
    credentials = undercloud_keystone_credentials()
    return keystone.get_keystone_session(credentials=credentials)


def undercloud_keystone_credentials() -> keystone.KeystoneCredentialsFixture:
    return tobiko.get_fixture(UndercloudKeystoneCredentialsFixture)


@functools.lru_cache()
def undercloud_version() -> tobiko.Version:
    ssh_client = undercloud_ssh_client()
    return rhosp.get_rhosp_version(connection=ssh_client)


def check_undercloud(min_version: tobiko.Version = None,
                     max_version: tobiko.Version = None):
    try:
        ssh_client = undercloud_ssh_client()
    except NoSuchUndercloudHostname as ex:
        raise UndercloudNotFound(
            cause='TripleO undercloud hostname not found') from ex
    try:
        ssh_client.connect(retry_count=1,
                           connection_attempts=1,
                           timeout=15.)
    except Exception as ex:
        raise UndercloudNotFound(
            cause=f'unable to connect to TripleO undercloud host: {ex}'
        ) from ex

    if min_version or max_version:
        tobiko.check_version(undercloud_version(),
                             min_version=min_version,
                             max_version=max_version,
                             mismatch_error=UndercloudVersionMismatch)


class UndercloudNotFound(tobiko.ObjectNotFound):
    message = 'undercloud not found: {cause}'


class UndercloudVersionMismatch(tobiko.VersionMismatch):
    message = 'undercloud version mismatch: {version} {cause}'
