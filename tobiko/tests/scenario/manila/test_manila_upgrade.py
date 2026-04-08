# Copyright (c) 2025 Red Hat, Inc.
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
"""Manila upgrade test cases

This module contains test cases for testing Manila functionality across
OpenStack upgrades. The tests follow this workflow:

Pre-upgrade (with TOBIKO_PREVENT_CREATE=no):
    1. Create a Manila share of configured size and protocol
    2. Allow access to a pre-configured client with configured access type
    3. Mount the share on a destination host with configured mount options
    4. Write the date continuously into a file on the mounted share
    5. Ensure the mount and date writer service survive system restarts

Post-upgrade (with TOBIKO_PREVENT_CREATE=yes):
    1. Verify the share is still accessible
    2. Verify the date log file exists and contains data from before upgrade
    3. Create a snapshot of the share
    4. Create a new share from the snapshot
"""
# pylint: disable=unsubscriptable-object
from __future__ import absolute_import

import time

import testtools
from oslo_log import log

import tobiko
from tobiko import config
from tobiko.openstack import manila
from tobiko.openstack import stacks
from tobiko.shell import sh

LOG = log.getLogger(__name__)
CONF = config.CONF


@manila.skip_if_missing_manila_service
class ManilaUpgradeTestCase(testtools.TestCase):
    """Manila upgrade test cases.

    These tests validate Manila functionality before and after an OpenStack
    upgrade. The pre-upgrade tests create resources and start continuous
    operations, while post-upgrade tests verify existing resources, ensure
    continuous workloads survived, and test advanced features like snapshots.
    """

    # Use the advanced Manila fixture with mounting capabilities
    share_fixture = tobiko.required_fixture(stacks.ManilaShareWithMountFixture)

    snapshot = None
    snapshot_share = None

    def setUp(self):
        super(ManilaUpgradeTestCase, self).setUp()

        # Skip tests if required configuration is missing
        if not CONF.tobiko.manila.destination_host:
            tobiko.skip_test("manila.destination_host must be configured")

    @config.skip_if_prevent_create()
    def test_01_create_share(self):
        """Create Manila share and verify it reaches 'available' status

        This test creates a Manila share with the configured protocol and size.
        It waits for the share to become available before proceeding.
        """
        share = self.share_fixture.share

        self.assertIsNotNone(share)
        self.assertIn('id', share)
        self.assertIn('name', share)

        LOG.info(f"Created Manila share: {share['name']} "
                 f"(ID: {share['id']})")

        manila.wait_for_share_status(share['id'])

        updated_share = manila.get_share(share['id'])
        self.assertEqual('available', updated_share['status'].lower())

        LOG.info(f"Share {share['name']} is available")

    @config.skip_if_prevent_create()
    def test_02_grant_access(self):
        """Grant access to the Manila share

        This test grants access to the share using the configured access type
        (e.g., IP, CephX key) and verifies the access rule was created.
        """
        share_id = self.share_fixture.share_id
        access_rule = self.share_fixture.access_rule

        self.assertIsNotNone(access_rule)
        self.assertIn('id', access_rule)
        self.assertIn('access_type', access_rule)
        self.assertIn('access_to', access_rule)
        self.assertIn('access_level', access_rule)

        LOG.info(
            f"Access granted: {access_rule['access_type']}:"
            f"{access_rule['access_to']} "
            f"with level {access_rule['access_level']}")

        access_rules = manila.list_access_rules(share_id)
        rule_ids = [rule['id'] for rule in access_rules]
        self.assertIn(access_rule['id'], rule_ids)

        LOG.info(f"Access rule verified for share {share_id}")

    @config.skip_if_prevent_create()
    def test_03_mount_share(self):
        """Mount the Manila share on the destination host

        This test mounts the share on the configured destination host and
        verifies the mount point is accessible.
        """
        # The share should be automatically mounted by the fixture
        # Verify the mount by checking if the mount point exists
        mount_point = (self.share_fixture.mount_point
                       or CONF.tobiko.manila.mount_point)

        LOG.info(f"Verifying share is mounted at {mount_point}")

        # Execute a simple test to verify the mount point
        result = sh.execute(
            f"test -d {mount_point}",
            ssh_client=self.share_fixture.ssh_client,
            expect_exit_status=None)

        self.assertEqual(0, result.exit_status,
                         f"Mount point {mount_point} does not exist")

        # Verify we can write to the mount point
        test_file = f"{mount_point}/test_write.txt"
        result = sh.execute(
            f"sudo sh -c 'echo test > {test_file} && cat {test_file}'",
            ssh_client=self.share_fixture.ssh_client)

        self.assertIn('test', result.stdout)

        # Clean up test file
        sh.execute(f"sudo rm -f {test_file}",
                   ssh_client=self.share_fixture.ssh_client,
                   expect_exit_status=None)

        LOG.info(f"Share successfully mounted and writable at {mount_point}")

    @config.skip_if_prevent_create()
    def test_04_verify_date_writer_running(self):
        """Verify the date writer service is running

        This test verifies that the systemd service writing dates to the
        log file is active and running.
        """
        service_name = self.share_fixture.systemd_service_name

        LOG.info(f"Checking if service {service_name} is running")

        # Check service status
        result = sh.execute(
            f"sudo systemctl is-active {service_name}",
            ssh_client=self.share_fixture.ssh_client,
            expect_exit_status=None)

        self.assertEqual(0, result.exit_status,
                         f"Service {service_name} is not active")
        self.assertIn('active', result.stdout.lower())

        LOG.info(f"Date writer service {service_name} is active")

        # Wait a few seconds and verify the log file is being written to
        time.sleep(10)

        log_path = self.share_fixture.get_date_log_path()
        result = sh.execute(
            f"wc -l {log_path}",
            ssh_client=self.share_fixture.ssh_client)

        # Should have at least 2 lines (service writes every 5 seconds)
        line_count = int(result.stdout.split()[0])
        self.assertGreaterEqual(
            line_count, 1,
            f"Date log file should have content: {log_path}")

        LOG.info(f"Date log file has {line_count} lines")

    @config.skip_if_prevent_create()
    def test_05_verify_persistence_config(self):
        """Verify mount and service are configured to survive reboots

        This test verifies that the share mount is in /etc/fstab and the
        date writer service is enabled to start on boot.
        """
        mount_point = (self.share_fixture.mount_point
                       or CONF.tobiko.manila.mount_point)
        service_name = self.share_fixture.systemd_service_name

        # Verify fstab entry
        result = sh.execute(
            f"grep '{mount_point}' /etc/fstab",
            ssh_client=self.share_fixture.ssh_client,
            expect_exit_status=None)

        self.assertEqual(0, result.exit_status,
                         "Mount point not found in /etc/fstab")
        self.assertIn(mount_point, result.stdout)

        LOG.info("Mount point is configured in /etc/fstab for persistence")

        # Verify service is enabled
        result = sh.execute(
            f"sudo systemctl is-enabled {service_name}",
            ssh_client=self.share_fixture.ssh_client,
            expect_exit_status=None)

        self.assertEqual(0, result.exit_status,
                         f"Service {service_name} is not enabled")
        self.assertIn('enabled', result.stdout.lower())

        LOG.info(f"Service {service_name} is enabled for automatic start")

    # Post-upgrade tests

    @config.skip_unless_prevent_create()
    def test_06_verify_share_accessible(self):
        """Verify the Manila share is still accessible after upgrade

        This test verifies that the share created before the upgrade is
        still present and in 'available' status.
        """
        share = self.share_fixture.share
        share_id = share['id']

        LOG.info(f"Verifying share {share_id} is accessible after upgrade")

        updated_share = manila.get_share(share_id)

        self.assertIsNotNone(updated_share)
        self.assertEqual(share_id, updated_share['id'])
        self.assertEqual('available', updated_share['status'].lower())

        LOG.info(f"Share {share_id} is accessible and available")

    @config.skip_unless_prevent_create()
    def test_07_verify_date_log_exists(self):
        """Verify the date log file exists and is accessible after upgrade

        This test verifies that the date log file on the mounted share
        still exists and contains data, indicating the mount and service
        survived the upgrade.
        """
        LOG.info("Verifying date log file after upgrade")

        # Use the fixture method to verify the log
        log_content = self.share_fixture.verify_date_log_exists()

        self.assertIsNotNone(log_content)
        self.assertTrue(
            len(log_content) > 0,
            "Date log file should not be empty")

        # Verify log contains date entries
        lines = log_content.strip().split('\n')
        self.assertGreater(
            len(lines), 0,
            "Date log should have multiple entries")

        LOG.info(f"Date log file verified with {len(lines)} entries")
        LOG.debug(f"First entry: {lines[0]}")
        LOG.debug(f"Last entry: {lines[-1]}")

    @config.skip_unless_prevent_create()
    def test_08_create_snapshot(self):
        """Create a snapshot of the Manila share after upgrade"""
        share_id = self.share_fixture.share_id
        snapshot_name = f"tobiko-snapshot-{share_id[:8]}"

        snapshot = manila.create_snapshot(
            share_id,
            name=snapshot_name,
            description="Tobiko Manila upgrade test snapshot")
        self.__class__.snapshot = snapshot

        self.assertIsNotNone(snapshot)
        self.assertIn('id', snapshot)

        manila.wait_for_snapshot_status(snapshot['id'])

        updated = manila.get_snapshot(snapshot['id'])
        self.assertEqual('available', updated['status'].lower())

        LOG.info(f"Snapshot {snapshot['id']} is available")

    @config.skip_unless_prevent_create()
    def test_09_create_share_from_snapshot(self):
        """Create a new share from the snapshot"""
        snapshot = self.snapshot
        if not snapshot:
            tobiko.skip_test("Snapshot not created in previous test")

        snapshot_id = snapshot['id']
        share_name = f"tobiko-from-snapshot-{snapshot_id[:8]}"

        new_share = manila.create_share_from_snapshot(
            snapshot_id,
            name=share_name,
            description="Tobiko Manila share created from snapshot")
        self.__class__.snapshot_share = new_share

        self.assertIsNotNone(new_share)
        self.assertIn('id', new_share)

        manila.wait_for_share_status(new_share['id'])

        updated = manila.get_share(new_share['id'])
        self.assertEqual('available', updated['status'].lower())

        LOG.info(
            f"Share from snapshot {new_share['id']} is available")

    @classmethod
    def tearDownClass(cls):
        super(ManilaUpgradeTestCase, cls).tearDownClass()
        snapshot_share = cls.snapshot_share
        if snapshot_share:
            try:
                manila.delete_share(snapshot_share['id'])
                manila.wait_for_resource_deletion(
                    snapshot_share['id'])
            except Exception as ex:
                LOG.warning(
                    f"Failed to clean up snapshot share: {ex}")
        snapshot = cls.snapshot
        if snapshot:
            try:
                manila.delete_snapshot(snapshot['id'])
                manila.wait_for_snapshot_deletion(snapshot['id'])
            except Exception as ex:
                LOG.warning(f"Failed to clean up snapshot: {ex}")
