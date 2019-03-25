# Copyright 2018 Red Hat
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

from tobiko import config

CONF = config.CONF

TEMPLATE_SUFFIX = ".yaml"

DEFAULT_PARAMS = {

    # Nova
    'image': CONF.tobiko.nova.image,
    'flavor': CONF.tobiko.nova.flavor,

    # Neutron
    'public_net': CONF.tobiko.neutron.floating_network,
}
