# Copyright (c) 2026 Red Hat, Inc.
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

import testtools

from tobiko import podified


@podified.skip_if_not_podified
class OcpPodsSanityTest(testtools.TestCase):
    """Sanity test: verify all OSP pods are healthy and ready."""

    def test_ocp_pods_running(self):
        """Assert all pods in the OSP namespace are Running and Ready.

        Uses the same assert_ocp_pods_running() check that runs before and
        after disruption tests, so results are directly comparable.
        A pod is considered healthy when it is in Succeeded phase (completed
        jobs) or in Running phase with all containers passing their readiness
        probes.
        """
        podified.assert_ocp_pods_running()
