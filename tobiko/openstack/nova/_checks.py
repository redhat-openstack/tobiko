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
from oslo_log import log

import tobiko
from tobiko.openstack.nova import _client
from tobiko.openstack.nova import _server
from tobiko.openstack.nova import _service
from tobiko.openstack import topology
from tobiko.shell import ping
from tobiko.shell import sh


LOG = log.getLogger(__name__)


def check_nova_services_health(timeout=600., interval=2.):
    retry = tobiko.retry(timeout=timeout, interval=interval)
    _service.wait_for_services_up(retry=retry)


def check_virsh_domains_running():
    """check all vms are running via virsh list command"""
    for compute in topology.list_openstack_nodes(group='compute'):
        hostname = sh.get_hostname(ssh_client=compute.ssh_client,
                                   fqdn=True)
        param = {'OS-EXT-SRV-ATTR:hypervisor_hostname': hostname}
        vm_list_per_compute = _client.list_servers(**param)
        for vm in vm_list_per_compute:
            for attempt in tobiko.retry(timeout=120, interval=5):
                if check_vm_running_via_virsh(compute, vm.id):
                    LOG.info(f"{vm.id} is running ok on {hostname}")
                    break
                else:
                    msg = f"{vm.id} is not in running state on {hostname}"
                    if attempt.is_last:
                        tobiko.fail("timeout!! " + msg)
                    LOG.error(f"{vm.id} is not in running state on "
                              f"{hostname} ... Retrying")


def check_vms_ping(vm_list):
    for vm in vm_list:
        fip = _server.list_server_ip_addresses(vm,
                                               address_type='floating').first
        ping.ping_until_received(fip).assert_replied()


def check_vm_evacuations(vms_old=None, compute_host=None, timeout=600,
                         interval=2, check_no_evacuation=False):
    """check evacuation of vms
        'vms_old' - all the vms that originally (before evacuation) were
        running on the 'compute_host' machine"""
    for attempt in tobiko.retry(timeout=timeout, interval=interval):
        failures = []
        vms_new = _client.list_servers()
        for vm_old in vms_old or []:
            vm_evacuated = vms_new.with_attributes(  # pylint: disable=W0212
                id=vm_old.id).unique
            new_vm_host = vm_evacuated._info[  # pylint: disable=W0212
                'OS-EXT-SRV-ATTR:hypervisor_hostname']
            LOG.info(f"server {vm_old} evacuated to {new_vm_host}")

            if check_no_evacuation:
                cond = bool(compute_host != new_vm_host)
            else:
                cond = bool(compute_host == new_vm_host)
            if cond:
                failures.append(
                    'Failed vm evacuations: {}\n\n'.format(vm_old))

        if not failures:
            LOG.debug(vms_old)
            LOG.debug('All vms were evacuated!')
            return

        if attempt.is_last:
            tobiko.fail(
                'Timeout checking VM evacuations:\n{!s}', '\n'.join(failures))
        else:
            LOG.error('Failed nova evacuation:\n {}'.format(failures))
            LOG.error('Retrying...')


def check_vm_running_via_virsh(topology_compute, vm_id):
    """check that a vm is in running state via virsh command,
    return false if not"""
    if vm_id in get_vm_uuid_list_running_via_virsh(topology_compute):
        return True
    else:
        return False


def get_vm_uuid_list_running_via_virsh(topology_compute):
    from tobiko import podified
    from tobiko.tripleo import containers
    from tobiko.tripleo import overcloud

    get_uuid_loop = ("for i in `virsh list --name --state-running`; do "
                     "virsh domuuid $i; done")
    containerized_libvirt_cmd = \
        "{container_runtime} exec -u root {nova_libvirt} sh -c '{get_uuids}'"

    if podified.has_podified_cp():
        command = containerized_libvirt_cmd.format(
            container_runtime=podified.CONTAINER_RUNTIME,
            nova_libvirt=podified.NOVA_LIBVIRT_CONTAINER,
            get_uuids=get_uuid_loop)
    elif overcloud.has_overcloud():
        command = containerized_libvirt_cmd.format(
            container_runtime=containers.get_container_runtime_name(),
            nova_libvirt=containers.get_libvirt_container_name(),
            get_uuids=get_uuid_loop)
    else:
        command = get_uuid_loop

    return sh.execute(command,
                      ssh_client=topology_compute.ssh_client,
                      sudo=True).stdout.split()


def wait_for_all_instances_status(status, timeout=None):
    """wait for all instances for a certain status or raise an exception"""
    for instance in _client.list_servers():
        _client.wait_for_server_status(server=instance.id, status=status,
                                       timeout=timeout)
        instance_info = 'instance {nova_instance} is {state} on {host}'.format(
            nova_instance=instance.name,
            state=status,
            host=instance._info[  # pylint: disable=W0212
                'OS-EXT-SRV-ATTR:hypervisor_hostname'])
        LOG.info(instance_info)
