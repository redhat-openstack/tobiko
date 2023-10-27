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

import itertools

from oslo_config import cfg


GROUP_NAME = 'keystone'
OPTIONS = [
    cfg.IntOpt('api_version',
               default=None,
               help="Identity API version"),
    cfg.StrOpt('auth_url',
               default=None,
               help="Identity service URL"),
    cfg.StrOpt('username',
               default=None,
               help="Username"),
    cfg.StrOpt('project_name',
               default=None,
               help="Project name"),
    cfg.StrOpt('password',
               default=None,
               help="Password"),
    cfg.StrOpt('domain_name',
               default=None,
               help="Domain name"),
    cfg.StrOpt('user_domain_name',
               default=None,
               help="User domain name"),
    cfg.StrOpt('project_domain_name',
               default=None,
               help="Project domain name"),
    cfg.StrOpt('project_domain_id',
               default=None,
               help="Project domain ID"),
    cfg.StrOpt('trust_id',
               default=None,
               help="Trust ID for trust scoping."),
    cfg.StrOpt('cloud_name',
               default=None,
               help=("Cloud name used pick authentication parameters from "
                     "clouds.*")),
    cfg.ListOpt('clouds_file_hosts',
                default=['localhost'],
                help="Host login from where to search for clouds file"),
    cfg.ListOpt('clouds_file_dirs',
                default=['.', '~/.config/openstack', '/etc/openstack'],
                help="Directories where to look for clouds files"),
    cfg.ListOpt('clouds_file_names',
                default=['clouds.yaml', 'clouds.yml', 'clouds.json'],
                help="Clouds file names"),
    cfg.StrOpt('interface',
               default=None,
               help="default value in case keystone interface is needed")]


def register_tobiko_options(conf):
    conf.register_opts(group=cfg.OptGroup(GROUP_NAME), opts=OPTIONS)


def list_options():
    return [(GROUP_NAME, itertools.chain(OPTIONS))]
