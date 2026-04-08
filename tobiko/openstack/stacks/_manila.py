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
from __future__ import absolute_import

import os
import tempfile
import typing

from oslo_log import log

import tobiko
from tobiko import config
from tobiko.openstack import manila
from tobiko.openstack.base import _fixture as base_fixture
from tobiko.shell import sh
from tobiko.shell import ssh

LOG = log.getLogger(__name__)
CONF = config.CONF


class ManilaShareFixture(base_fixture.ResourceFixture):

    _resource: typing.Optional[dict] = None
    share_protocol: typing.Optional[str] = None
    size: typing.Optional[int] = None

    def __init__(self, share_protocol=None, size=None):
        super().__init__()
        self.share_protocol = share_protocol or self.share_protocol
        self.size = size or self.size

    @property
    def share_id(self):
        return self.resource_id

    @property
    def share(self):
        return self.resource

    @tobiko.interworker_synched('manila_setup_fixture')
    def try_create_resource(self):
        super().try_create_resource()

    def resource_create(self):
        manila.ensure_default_share_type_exists()
        share = manila.create_share(share_protocol=self.share_protocol,
                                    size=self.size,
                                    name=self.name)
        manila.wait_for_share_status(share['id'])
        LOG.debug(f'Share {share["name"]} was deployed successfully '
                  f'with id {share["id"]}')
        return share

    def resource_delete(self):
        LOG.debug('Deleting Share %r ...', self.name)
        manila.delete_share(self.share_id)
        manila.wait_for_resource_deletion(self.share_id)
        LOG.debug('Share %r deleted.', self.name)

    def resource_find(self):
        found_shares = manila.get_shares_by_name(self.name)
        if len(found_shares) > 1:
            tobiko.fail(f'Unexpected number of shares found: {found_shares}')

        if found_shares:
            LOG.debug("Share %r found.", self.name)
            return found_shares[0]

        # no shares found
        LOG.debug("Share %r not found.", self.name)


class ManilaShareWithAccessFixture(ManilaShareFixture):
    """Manila share fixture with access rules management"""

    _access_rule: typing.Optional[typing.Any] = None
    access_type: typing.Optional[str] = None
    access_to: typing.Optional[str] = None
    access_level: typing.Optional[str] = None

    def __init__(self, share_protocol=None, size=None, access_type=None,
                 access_to=None, access_level=None):
        super().__init__(share_protocol=share_protocol, size=size)
        self.access_type = access_type or self.access_type
        self.access_to = access_to or self.access_to
        self.access_level = access_level or self.access_level

    @property
    def access_rule(self):
        return self._access_rule

    def setup_fixture(self):
        super().setup_fixture()
        # Grant access after share is created
        if not self._access_rule:
            self._grant_access()

    def _grant_access(self):
        """Grant access to the Manila share"""
        access_type = self.access_type or CONF.tobiko.manila.access_type
        access_to = self.access_to or CONF.tobiko.manila.access_to
        access_level = self.access_level or CONF.tobiko.manila.access_level

        if not access_to:
            LOG.warning("No access_to configured, skipping access grant")
            return

        # Check if a matching access rule already exists
        existing_rules = manila.list_access_rules(self.share_id)
        for rule in existing_rules:
            if (rule.get('access_type') == access_type and
                    rule.get('access_to') == access_to):
                LOG.debug(f"Access rule already exists: {rule}")
                self._access_rule = rule
                return

        LOG.debug(f"Granting {access_level} access to share {self.share_id} "
                  f"for {access_type}:{access_to}")

        self._access_rule = manila.allow_access(
            self.share_id,
            access_type=access_type,
            access_to=access_to,
            access_level=access_level)

        LOG.debug(f"Access granted: {self._access_rule}")

        # Wait for the access rule to become active before mounting
        rule_id = self._access_rule['id']
        LOG.debug(f"Waiting for access rule {rule_id} to become active")
        manila.wait_for_access_rule_status(rule_id)

    def cleanup_fixture(self):
        # Revoke access before deleting share
        if self._access_rule:
            try:
                rule_id = self._access_rule['id']
                LOG.debug(f"Revoking access rule {rule_id}")
                manila.deny_access(self.share_id, rule_id)
                self._access_rule = None
            except Exception as ex:
                LOG.warning(f"Failed to revoke access: {ex}")

        super().cleanup_fixture()


class ManilaShareWithMountFixture(ManilaShareWithAccessFixture):
    """Manila share fixture with mounting and continuous workload"""

    mount_point: typing.Optional[str] = None
    mount_options: typing.Optional[str] = None
    destination_host: typing.Optional[str] = None
    destination_ssh_username: typing.Optional[str] = None
    destination_ssh_key_filename: typing.Optional[str] = None
    date_log_filename: typing.Optional[str] = None
    ssh_client: typing.Optional[ssh.SSHClientFixture] = None

    def __init__(self, share_protocol=None, size=None, access_type=None,
                 access_to=None, access_level=None, mount_point=None,
                 mount_options=None, destination_host=None,
                 destination_ssh_username=None,
                 destination_ssh_key_filename=None,
                 date_log_filename=None):
        super().__init__(share_protocol=share_protocol, size=size,
                         access_type=access_type, access_to=access_to,
                         access_level=access_level)
        self.mount_point = mount_point or self.mount_point
        self.mount_options = mount_options or self.mount_options
        self.destination_host = destination_host or self.destination_host
        self.destination_ssh_username = (destination_ssh_username or
                                         self.destination_ssh_username)
        self.destination_ssh_key_filename = (destination_ssh_key_filename or
                                             self.destination_ssh_key_filename)
        self.date_log_filename = date_log_filename or self.date_log_filename

    def get_export_location(self):
        """Get the export location for the share"""
        export_locations = manila.get_export_locations(self.share_id)

        if not export_locations:
            raise RuntimeError(
                f"No export locations found for share {self.share_id}")

        for location in export_locations:
            if location.get('preferred'):
                LOG.debug("Using preferred export location: %s",
                          location['path'])
                return location['path']

        path = export_locations[0]['path']
        LOG.debug("Using first export location: %s", path)
        return path

    @property
    def systemd_service_name(self):
        """Get the systemd service name for the date writer"""
        return f"manila-date-writer-{self.share_id[:8]}"

    def _create_ssh_client(self):
        """Create SSH client to the destination host"""
        host = self.destination_host or CONF.tobiko.manila.destination_host
        username = (self.destination_ssh_username or
                    CONF.tobiko.manila.destination_ssh_username)
        key_filename = (self.destination_ssh_key_filename or
                        CONF.tobiko.manila.destination_ssh_key_filename)

        if not host:
            raise ValueError("destination_host must be configured")

        ssh_client_params = {'host': host}
        if username:
            ssh_client_params['username'] = username
        if key_filename:
            ssh_client_params['key_filename'] = key_filename

        return ssh.ssh_client(**ssh_client_params)

    def setup_fixture(self):
        super().setup_fixture()

        # Create SSH client
        if not self.ssh_client:
            self.ssh_client = self._create_ssh_client()

        # Mount the share
        self._mount_share()

        # Install and start the date writer service
        self._install_date_writer_service()

    def _mount_share(self):
        """Mount the Manila share on the destination host"""
        export_location = self.get_export_location()
        mount_point = self.mount_point or CONF.tobiko.manila.mount_point
        mount_options = self.mount_options or CONF.tobiko.manila.mount_options

        # Check if already mounted
        result = sh.execute(f"mountpoint -q {mount_point}",
                            ssh_client=self.ssh_client,
                            expect_exit_status=None)
        if result.exit_status == 0:
            LOG.info(f"Share already mounted at {mount_point}")
            return

        LOG.info(f"Mounting share {export_location} at {mount_point}")

        # Create mount point directory
        sh.execute(f"sudo mkdir -p {mount_point}",
                   ssh_client=self.ssh_client)

        # Build mount command
        mount_cmd = self._build_mount_command(
            export_location, mount_point, mount_options)

        # Mount the share, retrying in case NFS-Ganesha needs time
        # to reload its export configuration
        for attempt in tobiko.retry(timeout=60., interval=5.):
            try:
                sh.execute(mount_cmd, ssh_client=self.ssh_client)
                break
            except sh.ShellCommandFailed:
                attempt.check_limits()
                LOG.debug("Mount failed, retrying...")

        LOG.info(f"Share mounted successfully at {mount_point}")

        # Add to fstab for persistence
        self._add_to_fstab(export_location, mount_point, mount_options)

    def _build_mount_command(self, export_location, mount_point,
                             mount_options):
        """Build the mount command based on share protocol"""
        share_protocol = (self.share_protocol or
                          CONF.tobiko.manila.share_protocol)

        if share_protocol.lower() == 'nfs':
            if mount_options:
                return (f"sudo mount -t nfs -o {mount_options} "
                        f"{export_location} {mount_point}")
            else:
                return (f"sudo mount -t nfs {export_location} "
                        f"{mount_point}")
        elif share_protocol.lower() == 'cephfs':
            if mount_options:
                return (f"sudo mount -t ceph {export_location} {mount_point} "
                        f"-o {mount_options}")
            else:
                return f"sudo mount -t ceph {export_location} {mount_point}"
        else:
            # Generic mount command
            if mount_options:
                return (f"sudo mount -o {mount_options} {export_location} "
                        f"{mount_point}")
            else:
                return f"sudo mount {export_location} {mount_point}"

    def _add_to_fstab(self, export_location, mount_point, mount_options):
        """Add mount entry to /etc/fstab for persistence"""
        share_protocol = (self.share_protocol or
                          CONF.tobiko.manila.share_protocol)

        if share_protocol.lower() == 'nfs':
            fstype = 'nfs'
            options = mount_options or 'defaults'
        elif share_protocol.lower() == 'cephfs':
            fstype = 'ceph'
            options = mount_options or 'defaults'
        else:
            fstype = 'auto'
            options = mount_options or 'defaults'

        fstab_entry = (f"{export_location} {mount_point} {fstype} "
                       f"{options} 0 0")

        LOG.debug(f"Adding fstab entry: {fstab_entry}")

        # Check if entry already exists
        result = sh.execute(
            f"grep -q '{mount_point}' /etc/fstab",
            ssh_client=self.ssh_client,
            expect_exit_status=None)

        if result.exit_status == 0:
            LOG.debug("fstab entry already exists")
            return

        # Add entry to fstab
        sh.execute(
            f"echo '{fstab_entry}' | sudo tee -a /etc/fstab",
            ssh_client=self.ssh_client)

        LOG.info("Added mount entry to /etc/fstab")

    def _install_date_writer_service(self):
        """Install and start systemd service to write dates to log file"""
        service_name = self.systemd_service_name

        # Check if service is already running
        result = sh.execute(
            f"sudo systemctl is-active {service_name}",
            ssh_client=self.ssh_client,
            expect_exit_status=None)
        if result.exit_status == 0:
            LOG.info(f"Date writer service {service_name} already running")
            return

        mount_point = self.mount_point or CONF.tobiko.manila.mount_point
        log_filename = (self.date_log_filename or
                        CONF.tobiko.manila.date_log_filename)
        log_path = f"{mount_point}/{log_filename}"

        LOG.info(f"Installing date writer service: {service_name}")

        # Create systemd service file
        service_content = f"""[Unit]
Description=Manila Date Writer for Share {self.share_id}
After=network.target

[Service]
Type=simple
ExecStart=/bin/bash -c 'while true; do date >> {log_path}; sleep 5; done'
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
"""

        service_file = f"/etc/systemd/system/{service_name}.service"
        remote_tmp = f"/tmp/{service_name}.service"

        # Write service file via SFTP to avoid shell quoting issues
        with tempfile.NamedTemporaryFile(mode='w', suffix='.service',
                                         delete=False) as f:
            f.write(service_content)
            local_tmp = f.name

        try:
            sh.put_file(local_file=local_tmp,
                        remote_file=remote_tmp,
                        connection=self.ssh_client)
        finally:
            os.unlink(local_tmp)

        sh.execute(f"sudo mv {remote_tmp} {service_file}",
                   ssh_client=self.ssh_client)

        # Reload systemd
        sh.execute("sudo systemctl daemon-reload",
                   ssh_client=self.ssh_client)

        # Enable and start service
        sh.execute(f"sudo systemctl enable {service_name}",
                   ssh_client=self.ssh_client)
        sh.execute(f"sudo systemctl start {service_name}",
                   ssh_client=self.ssh_client)

        LOG.info(f"Date writer service {service_name} started")

    def get_date_log_path(self):
        """Get the full path to the date log file"""
        mount_point = self.mount_point or CONF.tobiko.manila.mount_point
        log_filename = (self.date_log_filename or
                        CONF.tobiko.manila.date_log_filename)
        return f"{mount_point}/{log_filename}"

    def verify_date_log_exists(self):
        """Verify the date log file exists and return its contents"""
        log_path = self.get_date_log_path()

        LOG.info(f"Verifying date log file exists: {log_path}")

        result = sh.execute(f"cat {log_path}",
                            ssh_client=self.ssh_client)

        return result.stdout

    def cleanup_fixture(self):
        # Stop and disable date writer service
        if self.ssh_client:
            try:
                service_name = self.systemd_service_name
                LOG.debug(f"Stopping service {service_name}")
                sh.execute(f"sudo systemctl stop {service_name}",
                           ssh_client=self.ssh_client,
                           expect_exit_status=None)
                sh.execute(f"sudo systemctl disable {service_name}",
                           ssh_client=self.ssh_client,
                           expect_exit_status=None)
                sh.execute(
                    f"sudo rm -f /etc/systemd/system/{service_name}.service",
                    ssh_client=self.ssh_client,
                    expect_exit_status=None)
                sh.execute("sudo systemctl daemon-reload",
                           ssh_client=self.ssh_client,
                           expect_exit_status=None)
            except Exception as ex:
                LOG.warning(f"Failed to stop date writer service: {ex}")

            # Unmount share
            try:
                mount_point = (self.mount_point or
                               CONF.tobiko.manila.mount_point)
                LOG.debug(f"Unmounting {mount_point}")
                sh.execute(f"sudo umount {mount_point}",
                           ssh_client=self.ssh_client,
                           expect_exit_status=None)
            except Exception as ex:
                LOG.warning(f"Failed to unmount share: {ex}")

            # Remove fstab entry
            try:
                mount_point = (self.mount_point or
                               CONF.tobiko.manila.mount_point)
                sh.execute(
                    f"sudo sed -i '\\|{mount_point}|d' /etc/fstab",
                    ssh_client=self.ssh_client,
                    expect_exit_status=None)
            except Exception as ex:
                LOG.warning(f"Failed to remove fstab entry: {ex}")

        super().cleanup_fixture()
