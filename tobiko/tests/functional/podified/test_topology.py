# Copyright (c) 2023 Red Hat, Inc.
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

import tobiko
from tobiko.tests.functional.openstack import test_topology
from tobiko import podified


@podified.skip_if_not_podified
class PodifiedTopologyTest(test_topology.OpenStackTopologyTest):

    @property
    def topology(self) -> podified.PodifiedTopology:
        return tobiko.setup_fixture(podified.PodifiedTopology)

    def test_controller_group(self):
        self.skipTest("Discovery of the OCP workers is "
                      "not implemented yet.")
