# Copyright (c) 2021 Red Hat, Inc.
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

import os.path
import typing

import netaddr
import pytest
import testtools

import tobiko
from tobiko.shell import curl
from tobiko.shell import sh
from tobiko.shell import ssh
from tobiko.openstack import keystone
from tobiko.openstack import stacks


@pytest.mark.flaky(reruns=2, reruns_delay=60)
@keystone.skip_unless_has_keystone_credentials()
class CurlExecuteTest(testtools.TestCase):

    stack = tobiko.required_fixture(stacks.AdvancedServerStackFixture)

    def test_execute_curl(
            self,
            ip_address: typing.Optional[netaddr.IPAddress] = None,
            ssh_client: typing.Optional[ssh.SSHClientFixture] = None):
        if ip_address is None:
            # Use the floating IP
            ip_address = self.stack.ip_address
        http_port = self.stack.http_port
        result = curl.execute_curl(scheme='http',
                                   hostname=ip_address,
                                   port=http_port,
                                   path='/id',
                                   ssh_client=ssh_client,
                                   connect_timeout=10.,
                                   retry_count=30,
                                   retry_timeout=300.,
                                   retry_interval=10.).strip()
        short_vm_name_from_curl = result.split('.')[0]
        self.assertEqual(self.stack.server_name, short_vm_name_from_curl)

    def test_execute_curl_ipv4(self):
        self.test_execute_curl(ip_address=self.get_fixed_ip(ip_version=4),
                               ssh_client=self.stack.ssh_client)

    def test_execute_curl_ipv6(self):
        self.test_execute_curl(ip_address=self.get_fixed_ip(ip_version=6),
                               ssh_client=self.stack.ssh_client)

    def get_fixed_ip(self, ip_version):
        for fixed_ip in self.stack.fixed_ips:
            ip_address = netaddr.IPAddress(fixed_ip['ip_address'])
            if ip_version == ip_address.version:
                return ip_address
        self.skipTest(f"Server {self.stack.server_id} has any "
                      f"IPv{ip_version} address.")


class CurlTest(testtools.TestCase):

    default_url = 'https://bootstrap.pypa.io/get-pip.py'

    def test_get_url_header(self,
                            url: str = None,
                            location: bool = None,
                            ssh_client: ssh.SSHClientType = None):
        if url is None:
            url = self.default_url
        header = curl.get_url_header(url=url,
                                     location=location,
                                     ssh_client=ssh_client)
        self.assertIsInstance(header, curl.CurlHeader)
        self.assertIn('date', header)
        return header

    def test_get_url_header_with_location(self):
        self.test_get_url_header(location=True)

    def test_get_url_header_with_no_location(self):
        self.test_get_url_header(location=True)

    def test_download_file(self,
                           url: str = None,
                           cached: bool = False,
                           download_dir: str = None,
                           **params) \
            -> curl.CurlProcessFixture:
        if url is None:
            url = tobiko.get_fixture(stacks.CirrosImageFixture).image_url
        if download_dir is None:
            download_dir = sh.make_temp_dir()
        header = self.test_get_url_header(url=url, location=True)
        process = curl.download_file(url=url,
                                     cached=cached,
                                     download_dir=download_dir,
                                     **params)
        try:
            result = process.wait()
        except RuntimeError:
            if not cached:
                raise
        else:
            self.assertIsInstance(result, sh.ShellExecuteResult)
            self.assertEqual(0, result.exit_status)

        if process.file_name is not None:
            self.assertEqual(header.content_length,
                             sh.get_file_size(process.file_name))
        return process

    def test_download_file_with_cached(self):
        process_1 = self.test_download_file(cached=True)
        self.assertTrue(process_1.executed)
        download_dir = os.path.dirname(process_1.file_name)
        process_2 = self.test_download_file(cached=True,
                                            download_dir=download_dir)
        self.assertFalse(process_2.executed)

    def test_assert_downloaded_file(self):
        process = self.test_download_file(cached=True)
        curl.assert_downloaded_file(
            file_name=process.file_name,
            headers_file_name=process.headers_file_name,
            ssh_client=process.ssh_client,
            sudo=process.sudo)
