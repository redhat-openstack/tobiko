
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

import base64
import io
import os

import tobiko
from tobiko import config
from tobiko.podified import _openshift
from tobiko.shell import ssh

CONF = config.CONF


def edpm_host_config(node=None,
                     ip_version: int = None,
                     key_filename: str = None):
    node = node or {}
    host_config = EdpmHostConfig(
        host=node.get('host'),
        ip_version=ip_version,
        key_filename=key_filename,
        port=node.get('port'),
        username=node.get('username'))
    return tobiko.setup_fixture(host_config)


def edpm_ssh_client(ip_version: int = None,
                    host_config=None,
                    node=None):
    if host_config is None:
        host_config = edpm_host_config(node=node,
                                       ip_version=ip_version)
    tobiko.check_valid_type(host_config.host, str)
    return ssh.ssh_client(host=host_config.host,
                          **host_config.connect_parameters)


class EdpmSshKeyFileFixture(tobiko.SharedFixture):

    @property
    def key_filename(self):
        return tobiko.tobiko_config_path(
            CONF.tobiko.rhosp.ssh_key_filename)

    def setup_fixture(self):
        self.setup_key_file()

    def setup_key_file(self):
        priv_key_filename = self.key_filename
        pub_key_filename = priv_key_filename + ".pub"
        key_dirname = os.path.dirname(priv_key_filename)
        tobiko.makedirs(key_dirname, mode=0o700)

        private_key, public_key = _openshift.get_dataplane_ssh_keypair()
        if private_key:
            with io.open(priv_key_filename, 'wb') as fd:
                fd.write(base64.b64decode(private_key))
                os.chmod(priv_key_filename, 0o600)
        if public_key:
            with io.open(pub_key_filename, 'wb') as fd:
                fd.write(base64.b64decode(public_key))
                os.chmod(pub_key_filename, 0o600)


class EdpmHostConfig(tobiko.SharedFixture):

    key_file = tobiko.required_fixture(EdpmSshKeyFileFixture)

    def __init__(self,
                 host: str,
                 ip_version: int = None,
                 key_filename: str = None,
                 port: int = None,
                 username: str = None,
                 **kwargs):
        super(EdpmHostConfig, self).__init__()
        self.host = host
        self.ip_version = ip_version
        self.key_filename = key_filename
        self.port = port
        self.username = username
        self._connect_parameters = ssh.gather_ssh_connect_parameters(**kwargs)

    def setup_fixture(self):
        if self.port is None:
            self.port = CONF.tobiko.rhosp.ssh_port
        if self.username is None:
            self.username = CONF.tobiko.rhosp.ssh_username
        if self.key_filename is None:
            self.key_filename = self.key_file.key_filename

    @property
    def connect_parameters(self):
        parameters = ssh.ssh_host_config(
            host=str(self.host)).connect_parameters
        parameters.update(ssh.gather_ssh_connect_parameters(self))
        parameters.update(self._connect_parameters)
        return parameters
