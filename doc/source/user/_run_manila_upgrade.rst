Manila Upgrade Tests
~~~~~~~~~~~~~~~~~~~~

The Manila upgrade tests are designed to verify that Manila shares and their
data survive an OpenStack upgrade. The tests follow this workflow:

**Pre-Upgrade Phase** (``TOBIKO_PREVENT_CREATE=no``):

1. **Create Manila Share**: Creates a Manila share with configured size and protocol
2. **Grant Access**: Grants access to a pre-configured client using configured access type (IP, CephX, etc.)
3. **Mount Share**: Mounts the share on a destination host with configured mount options
4. **Start Date Writer**: Installs and starts a systemd service that continuously writes timestamps to a log file on the mounted share
5. **Verify Persistence**: Ensures the mount and service are configured to survive system restarts

**Upgrade Phase**:

Perform your OpenStack upgrade (this is done outside of Tobiko).

**Post-Upgrade Phase** (``TOBIKO_PREVENT_CREATE=yes``):

1. **Verify Share Accessible**: Verifies the Manila share is still present and available
2. **Verify Log File**: Checks that the date log file exists and is accessible, proving data persistence

Configuration
^^^^^^^^^^^^^

To run Manila upgrade tests, you need to configure the following options in
your ``tobiko.conf`` file:

Required Configuration
""""""""""""""""""""""

.. code-block:: ini

    [manila]
    # Protocol for Manila share (nfs, cephfs, etc.)
    share_protocol = nfs

    # Size of the share in GB
    size = 1

    # Destination host where the share will be mounted (required!)
    destination_host = 192.168.1.100

    # Access control - IP address or identifier for the destination host (required!)
    access_to = 192.168.1.100

Optional Configuration
""""""""""""""""""""""

.. code-block:: ini

    [manila]
    # Access type (ip, user, cert, cephx)
    access_type = ip

    # Access level (rw, ro)
    access_level = rw

    # Mount point on destination host
    mount_point = /mnt/tobiko_manila_test

    # Mount options (comma-separated)
    mount_options = vers=4.1,proto=tcp

    # SSH connection details for destination host
    destination_ssh_username = root
    destination_ssh_key_filename = /path/to/ssh/key

    # Date log filename on the mounted share
    date_log_filename = date_log.txt

Running the Tests
^^^^^^^^^^^^^^^^^

Complete Upgrade Workflow
""""""""""""""""""""""""""

Run the following commands to execute the complete Manila upgrade test workflow::

    # 1. Before upgrade: Create resources and start continuous operations
    tox -e manila -- tobiko/tests/scenario/manila/test_manila_upgrade.py

    # 2. Perform your OpenStack upgrade
    # ... upgrade your OpenStack environment ...

    # 3. After upgrade: Verify resources and test advanced functionality
    TOBIKO_PREVENT_CREATE=yes tox -e manila -- tobiko/tests/scenario/manila/test_manila_upgrade.py

Running Individual Test Phases
"""""""""""""""""""""""""""""""

You can also run individual test phases separately.

**Pre-Upgrade Tests Only**::

    tox -e manila -- tobiko/tests/scenario/manila/test_manila_upgrade.py::ManilaUpgradeTestCase::test_01_create_share
    tox -e manila -- tobiko/tests/scenario/manila/test_manila_upgrade.py::ManilaUpgradeTestCase::test_02_grant_access
    tox -e manila -- tobiko/tests/scenario/manila/test_manila_upgrade.py::ManilaUpgradeTestCase::test_03_mount_share
    tox -e manila -- tobiko/tests/scenario/manila/test_manila_upgrade.py::ManilaUpgradeTestCase::test_04_verify_date_writer_running
    tox -e manila -- tobiko/tests/scenario/manila/test_manila_upgrade.py::ManilaUpgradeTestCase::test_05_verify_persistence_config

**Post-Upgrade Tests Only**::

    TOBIKO_PREVENT_CREATE=yes tox -e manila -- tobiko/tests/scenario/manila/test_manila_upgrade.py::ManilaUpgradeTestCase::test_06_verify_share_accessible
    TOBIKO_PREVENT_CREATE=yes tox -e manila -- tobiko/tests/scenario/manila/test_manila_upgrade.py::ManilaUpgradeTestCase::test_07_verify_date_log_exists

Configuration Examples
^^^^^^^^^^^^^^^^^^^^^^

Example 1: NFS Share with IP-based Access
""""""""""""""""""""""""""""""""""""""""""

.. code-block:: ini

    [manila]
    share_protocol = nfs
    size = 2
    access_type = ip
    access_to = 192.168.1.100
    access_level = rw
    mount_point = /mnt/manila_nfs
    mount_options = vers=4.1,proto=tcp
    destination_host = 192.168.1.100
    destination_ssh_username = cloud-user
    destination_ssh_key_filename = ~/.ssh/id_rsa

Example 2: CephFS Share with CephX Access
""""""""""""""""""""""""""""""""""""""""""

.. code-block:: ini

    [manila]
    share_protocol = cephfs
    size = 5
    access_type = cephx
    access_to = client.manila_user
    access_level = rw
    mount_point = /mnt/manila_cephfs
    mount_options =
    destination_host = 192.168.1.101
    destination_ssh_username = root

Troubleshooting
^^^^^^^^^^^^^^^

Share Mount Fails
"""""""""""""""""

**Problem**: The share fails to mount on the destination host.

**Solutions**:

- Verify the destination host has the required mount utilities installed (e.g., ``nfs-utils`` for NFS)
- Check that the access rule allows the destination host
- Verify network connectivity between the destination host and Manila backend
- Check mount options are appropriate for your share protocol

Date Writer Service Not Starting
"""""""""""""""""""""""""""""""""

**Problem**: The systemd service fails to start or write to the log file.

**Solutions**:

- Verify the mount point is writable
- Check systemd service status: ``systemctl status tobiko-manila-date-writer``
- Review systemd journal: ``journalctl -u tobiko-manila-date-writer``
- Ensure the destination host has sufficient permissions

SSH Connection Issues
"""""""""""""""""""""

**Problem**: Cannot connect to destination host via SSH.

**Solutions**:

- Verify ``destination_host`` is reachable
- Check SSH credentials (``destination_ssh_username`` and ``destination_ssh_key_filename``)
- Ensure SSH key has correct permissions (600)
- Verify firewall rules allow SSH connections
