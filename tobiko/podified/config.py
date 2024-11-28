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

import itertools

from oslo_config import cfg


def setup_tobiko_config(conf):
    # pylint: disable=unused-argument
    from tobiko.podified import _openshift
    from tobiko.podified import _topology

    if _openshift.has_podified_cp():
        _topology.setup_podified_topology()


GROUP_NAME = "podified"
OPTIONS = [
    cfg.StrOpt('osp_project',
               default='openstack',
               help="Openshift project that includes the Openstack resources"),
    cfg.StrOpt('background_tasks_project',
               default='tobiko',
               help='Name of the OpenShift project which will be used to run '
                    'PODs with tobiko background commands, like e.g.'
                    '`tobiko ping`'),
    cfg.StrOpt('tobiko_image',
               default='quay.io/podified-antelope-centos9/openstack-tobiko:current-podified',  # noqa
               help='Contaniner image used to run background tobiko commands '
                    'like e.g. `tobiko ping` in the POD.'),
    cfg.IntOpt('tobiko_start_pod_timeout',
               default=60,
               help='Defines how long Tobiko will wait until POD with the '
                    'background command (like tobiko ping) will be `Running`. '
                    'In most cases, if tobiko image is already in the local '
                    'registry it will need just few seconds to start POD but '
                    'if image is not yet cached locally it may take a bit '
                    'longer time to download it.'),
]


def register_tobiko_options(conf):
    conf.register_opts(group=cfg.OptGroup(GROUP_NAME), opts=OPTIONS)


def list_options():
    return [(GROUP_NAME, itertools.chain(OPTIONS))]
