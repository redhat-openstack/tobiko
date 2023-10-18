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
from tobiko.openstack.keystone import _credentials
from tobiko.shell import find
from tobiko.shell import sh


LOG = log.getLogger(__name__)

YAML_SUFFIXES = ('.yaml', '.yml')
JSON_SUFFIXES = ('.json',)
CLOUDS_FILE_SUFFIXES = JSON_SUFFIXES + YAML_SUFFIXES


class CloudsFileNotFoundError(tobiko.TobikoException):
    message = "No such clouds file(s): {clouds_files!s}"


CloudsFileContentType = typing.Mapping[str, typing.Any]


class CloudsFileKeystoneCredentialsFixture(
        _credentials.KeystoneCredentialsFixture):

    def __init__(self,
                 credentials: _credentials.KeystoneCredentials = None,
                 connection: sh.ShellConnectionType = None,
                 environ: typing.Dict[str, str] = None,
                 cloud_name: str = None,
                 directories: typing.Iterable[str] = None,
                 filenames: typing.Iterable[str] = None):
        super().__init__(credentials=credentials,
                         connection=connection,
                         environ=environ)
        self._cloud_name = cloud_name
        if directories is not None:
            directories = list(directories)
        self._directories = directories
        if filenames is not None:
            filenames = list(filenames)
        self._filenames = filenames

    default_cloud_name: typing.Optional[str] = None

    @property
    def cloud_name(self) -> typing.Optional[str]:
        if self._cloud_name is None:
            self._cloud_name = self._get_cloud_name()
        return self._cloud_name

    @property
    def directories(self) -> typing.List[str]:
        if self._directories is None:
            directories = [self.connection.get_config_path(directory)
                           for directory in self._get_directories()]
            self._directories = directories
        return self._directories

    @property
    def filenames(self) -> typing.List[str]:
        if self._filenames is None:
            self._filenames = self._get_filenames()
        return self._filenames

    def _get_credentials(self) -> _credentials.KeystoneCredentials:
        try:
            filenames = find.find_files(path=self.directories,
                                        name=self.filenames,
                                        max_depth=1,
                                        type='f',
                                        ssh_client=self.connection.ssh_client)
        except find.FilesNotFound as ex:
            raise _credentials.NoSuchKeystoneCredentials(
                reason=('Cloud files not found:\n'
                        f"  login: {self.login}\n"
                        f"  directories: {self.directories}\n"
                        f"  filenames: {self.filenames}\n"
                        f"  error: {ex}\n")) from ex

        if self.cloud_name is None:
            raise _credentials.NoSuchKeystoneCredentials(
                reason=(f"[{self.fixture_name}] Clouds name not found at"
                        f" {self.login!r}"))

        for filename in filenames:
            file_spec = f"{self.login}:{filename}"
            content = load_clouds_file_content(
                connection=self.connection,
                filename=filename)
            try:
                return parse_credentials(
                    file_spec=file_spec,
                    content=content,
                    cloud_name=self.cloud_name)
            except _credentials.NoSuchKeystoneCredentials:
                LOG.debug(f'Cloud with name {self.cloud_name} not found '
                          f'in {file_spec}')
        raise _credentials.NoSuchKeystoneCredentials(
            reason=(f"[{self.fixture_name}] Keystone credentials not found "
                    f"for cloud name {self.cloud_name!r} in files "
                    f"{filenames!r} (login={self.login})"))

    def _get_cloud_name(self) -> typing.Optional[str]:
        for var_name in ['OS_CLOUD', 'OS_CLOUDNAME']:
            cloud_name = self.environ.get(var_name)
            if cloud_name:
                LOG.debug(f"Got cloud name from '{var_name}' environment "
                          f"variable: {cloud_name}", )
                return cloud_name
        return self._get_default_cloud_name()

    @staticmethod
    def _get_default_cloud_name() -> typing.Optional[str]:
        return tobiko.tobiko_config().keystone.cloud_name

    @staticmethod
    def _get_directories() -> typing.List[str]:
        return tobiko.tobiko_config().keystone.clouds_file_dirs

    @staticmethod
    def _get_filenames() -> typing.List[str]:
        return tobiko.tobiko_config().keystone.clouds_file_names


def parse_credentials(file_spec: str,
                      cloud_name: str,
                      content: CloudsFileContentType):
    clouds_section = content.get("clouds")
    if clouds_section is None:
        raise _credentials.NoSuchKeystoneCredentials(
            reason=f"'clouds' section not found in {file_spec!r}")

    clouds_config = clouds_section.get(cloud_name)
    if clouds_config is None:
        raise _credentials.NoSuchKeystoneCredentials(
            reason=f"cloud name {cloud_name!r} not found in {file_spec!r}")

    auth = clouds_config.get("auth")
    if auth is None:
        raise _credentials.NoSuchKeystoneCredentials(
            reason=f"'auth' section not found for cloud name "
                   f"{cloud_name!r} in {file_spec!r}")

    auth_url = auth.get("auth_url")
    if not auth_url:
        raise _credentials.NoSuchKeystoneCredentials(
            reason=f"'auth_url' is {auth_url!r} for cloud name "
                   f"{cloud_name!r} in {file_spec!r}")

    username = auth.get('username') or auth.get('user_id')
    if not username:
        raise _credentials.NoSuchKeystoneCredentials(
            reason=f"'username' is {username!r} for cloud name "
                   f"{cloud_name!r} in {file_spec!r}")

    password = auth.get('password')
    if not password:
        raise _credentials.NoSuchKeystoneCredentials(
            reason=f"'password' is {password!r} for cloud name "
                   f"{cloud_name!r} in {file_spec!r}")
    elif not isinstance(password, str):
        password = str(password)

    cacert = clouds_config.get('cacert')
    project_name = (auth.get('project_name') or
                    auth.get('tenant_namer') or
                    auth.get('project_id') or
                    auth.get_env('tenant_id'))

    api_version = (int(clouds_config.get("identity_api_version", 0)) or
                   _credentials.api_version_from_url(auth_url))
    if api_version == 2:
        return _credentials.keystone_credentials(
            api_version=api_version,
            auth_url=auth_url,
            username=username,
            password=password,
            project_name=project_name)
    else:
        domain_name = (auth.get("domain_name") or
                       auth.get("domain_id"))
        user_domain_name = (auth.get("user_domain_name") or
                            auth.get("user_domain_id"))
        project_domain_name = auth.get("project_domain_name")
        project_domain_id = auth.get("project_domain_id")
        trust_id = auth.get("trust_id")
        return _credentials.keystone_credentials(
            api_version=api_version,
            auth_url=auth_url,
            username=username,
            password=password,
            project_name=project_name,
            domain_name=domain_name,
            user_domain_name=user_domain_name,
            project_domain_name=project_domain_name,
            project_domain_id=project_domain_id,
            cacert=cacert,
            trust_id=trust_id)


@functools.lru_cache()
def load_clouds_file_content(connection: sh.ShellConnection,
                             filename: str) \
        -> CloudsFileContentType:
    with connection.open_file(filename, 'r') as f:
        _, suffix = os.path.splitext(filename)
        if suffix in JSON_SUFFIXES:
            LOG.debug(f'Load JSON clouds file: {filename!r}')
            return json.load(f)
        else:
            LOG.debug(f'Load YAML clouds file: {filename!r}')
            return tobiko.load_yaml(f)
