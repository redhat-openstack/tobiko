# Copyright 2026 Red Hat
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

import tobiko
from tobiko import config
from tobiko.openstack import keystone

CONF = config.CONF


def is_manila_service_missing() -> bool:
    service_name = CONF.tobiko.manila.service_name
    return keystone.is_service_missing(name=service_name)


skip_if_missing_manila_service = tobiko.skip_if(
    'missing manila service', is_manila_service_missing)
