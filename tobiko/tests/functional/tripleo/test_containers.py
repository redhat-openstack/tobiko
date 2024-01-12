# Copyright 2021 Red Hat
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

import testtools

from tobiko.rhosp import containers as rhosp_containers
from tobiko.tripleo import containers


@containers.skip_unless_has_container_runtime()
class RuntimeRuntimeTest(testtools.TestCase):

    def test_get_container_runtime(self):
        runtime = containers.get_container_runtime()
        self.assertIsInstance(runtime, rhosp_containers.ContainerRuntime)

    def test_list_containers(self):
        containers_list = containers.list_containers()
        for container in containers_list:
            self.assertIsNotNone(container)
