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


GROUP_NAME = 'glance'
OPTIONS = [
    cfg.StrOpt('image_dir',
               default='~/.tobiko/cache/glance/images',
               help=("Default directory where to look for image "
                     "files")),
]


GLANCE_IMAGE_NAMES = ['cirros',
                      'ubuntu']


def register_tobiko_options(conf):
    conf.register_opts(group=cfg.OptGroup(GROUP_NAME), opts=OPTIONS)

    for image_options in get_images_options():
        conf.register_opts(group=image_options[0], opts=image_options[1])


def get_images_options():
    options = []
    for name in GLANCE_IMAGE_NAMES:
        group_name = name.lower()
        options += [(
            group_name,
            [cfg.StrOpt('image_name',
                        help="Default " + name + " image name"),
             cfg.StrOpt('image_url',
                        help="Default " + name + " image URL"),
             cfg.StrOpt('image_file',
                        help="Default " + name + " image filename"),
             cfg.StrOpt('container_format',
                        help="Default " + name + " container format"),
             cfg.StrOpt('disk_format',
                        help="Default " + name + " disk format"),
             cfg.StrOpt('username',
                        help="Default " + name + " username"),
             cfg.StrOpt('password',
                        help="Default " + name + " password"),
             cfg.StrOpt('interface_name',
                        default=None,
                        help="Default " + name + " interface name"),
             cfg.FloatOpt('connection_timeout',
                          default=None,
                          help=("Default " + name +
                                " SSH connection timeout (seconds)")),
             cfg.DictOpt('disabled_algorithms',
                         default=None,
                         help=("Allow to disable SSH auth algorithms"
                               "in order to SSH to old servers like"
                               "CirrOS ones")),
             ]
        )]

    return options


def list_options():
    options = [(GROUP_NAME, itertools.chain(OPTIONS))]
    for image_options in get_images_options():
        options += [
            (image_options[0], itertools.chain(image_options[1]))]
    return options
