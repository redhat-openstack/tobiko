# Copyright (c) 2024 Red Hat, Inc.
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
from oslo_log import log

import tobiko
from tobiko.openstack import topology
from tobiko.podified import _topology
from tobiko.shell import sh

LOG = log.getLogger(__name__)


class KpatchCommandNotFoundError(tobiko.TobikoException):
    message = "kpatch command not found on compute node"


class KpatchCommandFailedError(tobiko.TobikoException):
    message = "kpatch command failed on compute node"


class KpatchNotLoadedError(tobiko.TobikoException):
    message = "no kpatches loaded on compute node"


@_topology.skip_if_not_podified
class KpatchVerificationTest(testtools.TestCase):
    """Test to verify kpatches are applied on compute nodes after update"""

    def test_kpatches_applied_on_compute_nodes(self):
        """Verify that kpatches are loaded on all compute nodes"""
        compute_nodes = topology.list_openstack_nodes(group='compute')

        if not compute_nodes:
            tobiko.skip_test(
                "No EDPM compute nodes found in podified topology")

        LOG.info("Checking kpatches on {} compute nodes".format(
            len(compute_nodes)))

        failed_nodes = []

        for node in compute_nodes:
            if not isinstance(node, _topology.EdpmNode):
                LOG.warning(f"Skipping non-EDPM node: {node.name}")
                continue

            try:
                # Execute kpatch list command
                result = sh.execute('kpatch list',
                                    ssh_client=node.ssh_client,
                                    expect_exit_status=None)

                # Check if kpatch command not found
                if result.exit_status == 127:
                    raise KpatchCommandNotFoundError(
                        f"kpatch command not found on {node.name}")

                # Check if kpatch command failed
                if result.exit_status != 0:
                    raise KpatchCommandFailedError(
                        "kpatch command failed on {} "
                        "(exit code: {}): {}".format(
                            node.name, result.exit_status, result.stderr))

                # Check if no output (no kpatches loaded)
                output = result.stdout.strip()
                if not output:
                    raise KpatchNotLoadedError(
                        f"No kpatches loaded on {node.name}")

                LOG.info("Kpatches on {}:\n{}".format(node.name, output))

            except tobiko.TobikoException:
                # Re-raise tobiko exceptions as-is
                raise
            except Exception as ex:
                LOG.exception(f"Failed to check kpatches on {node.name}")
                failed_nodes.append("Exception on {}: {}".format(
                    node.name, str(ex)))

        # This should only be reached if there were non-tobiko exceptions
        if failed_nodes:
            failure_message = "Kpatch verification failed:\n" + "\n".join(
                "  - {}".format(failure) for failure in failed_nodes)
            raise AssertionError(failure_message)
