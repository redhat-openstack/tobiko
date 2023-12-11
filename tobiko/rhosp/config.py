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


# Group with config options common for RHOSP deployments
# (both Tripleo and Podified)
RHOSP_GROUP_NAME = 'rhosp'
# Group with config options related only for Tripleo based deployments
TRIPLEO_GROUP_NAME = 'tripleo'
# Group with config options related only for podified (NextGen) deployments
PODIFIED_GROUP_NAME = "podified"

RHOSP_OPTIONS = [
    cfg.IntOpt('ssh_port',
               default=None,
               deprecated_name='overcloud_ssh_port',
               deprecated_group=TRIPLEO_GROUP_NAME,
               help="TCP port of SSH server on overcloud or EDPM compute "
                    "hosts"),
    cfg.StrOpt('ssh_username',
               default=None,
               deprecated_name='overcloud_ssh_username',
               deprecated_group=TRIPLEO_GROUP_NAME,
               help="Default username used to connect to overcloud or EDPM "
                    "compute nodes"),
    cfg.StrOpt('ssh_key_filename',
               default='~/.ssh/osp_ssh_key',
               deprecated_name='overcloud_ssh_key_filename',
               deprecated_group=TRIPLEO_GROUP_NAME,
               help="SSH key filename used to login to Overcloud or EDPM "
                    "compute nodes"),
    cfg.StrOpt('cloud_name',
               default='overcloud',
               deprecated_name='overcloud_cloud_name',
               deprecated_group=TRIPLEO_GROUP_NAME,
               help='cloud name to be used for loading credentials '),
    cfg.IntOpt('ip_version',
               deprecated_name='overcloud_ip_version',
               deprecated_group=TRIPLEO_GROUP_NAME,
               help=("Default IP address version to be used to connect to "
                     "overcloud or EDPM compute nodes")),

    cfg.StrOpt('inventory_file',
               default='.ansible/inventory/tripleo.yaml',
               deprecated_group=TRIPLEO_GROUP_NAME,
               help="path to where to export tripleo inventory file"),

    cfg.BoolOpt('has_external_load_balancer',
                default=False,
                deprecated_group=TRIPLEO_GROUP_NAME,
                help="OSP env was done with an external load balancer"),

    cfg.BoolOpt('ceph_rgw',
                default=False,
                deprecated_group=TRIPLEO_GROUP_NAME,
                help="whether Ceph RGW is deployed"),
]

TRIPLEO_OPTIONS = [
    # Undercloud options
    cfg.StrOpt('undercloud_ssh_hostname',
               default='undercloud-0',
               help="hostname or IP address to be used to connect to "
                    "undercloud host"),
    cfg.IntOpt('undercloud_ssh_port',
               default=None,
               help="TCP port of SSH server on undercloud host"),
    cfg.StrOpt('undercloud_ssh_username',
               default='stack',
               help="Username with access to stackrc and overcloudrc files"),
    cfg.StrOpt('undercloud_ssh_key_filename',
               default=None,
               help="SSH key filename used to login to Undercloud node"),
    cfg.ListOpt('undercloud_rcfile',
                default=['~/stackrc'],
                help="Undercloud RC filename"),
    cfg.StrOpt('undercloud_cloud_name',
               default='undercloud',
               help='undercloud cloud name to be used for loading credentials '
                    'from the undercloud clouds files'),
    cfg.StrOpt('undercloud_cacert_file',
               default='/etc/pki/tls/certs/ca-bundle.trust.crt',
               help='Path to cacert file that can be used to send https '
                    'request from the undercloud'),

    cfg.ListOpt('overcloud_rcfile',
                default=['~/overcloudrc', '~/qe-Cloud-0rc'],
                help="Overcloud RC filenames"),
    cfg.StrOpt('overcloud_network_name',
               help="Name of network used to connect to overcloud nodes"),
    cfg.DictOpt('overcloud_groups_dict',
                help='Dictionary with the node groups corresponding to '
                     'different hostname prefixes',
                default={'ctrl': 'controller', 'cmp': 'compute'}),
]


def register_tobiko_options(conf):
    conf.register_opts(group=cfg.OptGroup(RHOSP_GROUP_NAME),
                       opts=RHOSP_OPTIONS)
    conf.register_opts(group=cfg.OptGroup(TRIPLEO_GROUP_NAME),
                       opts=TRIPLEO_OPTIONS)


def list_options():
    return [(RHOSP_GROUP_NAME, itertools.chain(RHOSP_OPTIONS)),
            (TRIPLEO_GROUP_NAME, itertools.chain(TRIPLEO_OPTIONS))]
