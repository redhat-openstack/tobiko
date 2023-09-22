from __future__ import absolute_import

import time
import typing  # noqa
from functools import wraps


from oslo_log import log
import pandas

import tobiko
from tobiko import tripleo
from tobiko.tripleo import overcloud
from tobiko.shell import ping
from tobiko.shell import sh
from tobiko.openstack import nova
from tobiko.openstack import topology
from tobiko.openstack import stacks
from tobiko.tripleo import containers


LOG = log.getLogger(__name__)


def check_nova_services_health(timeout=600., interval=2.):
    retry = tobiko.retry(timeout=timeout, interval=interval)
    nova.wait_for_services_up(retry=retry)


def start_all_instances():
    """try to start all stopped overcloud instances"""
    for instance in nova.list_servers():
        activated_instance = nova.activate_server(instance)
        time.sleep(3)
        instance_info = 'instance {nova_instance} is {state} on {host}'.format(
            nova_instance=activated_instance.name,
            state=activated_instance.status,
            host=activated_instance._info[  # pylint: disable=W0212
                'OS-EXT-SRV-ATTR:hypervisor_hostname'])
        LOG.info(instance_info)
        if activated_instance.status != 'ACTIVE':
            tobiko.fail(instance_info)


def stop_all_instances():
    """try to start all stopped overcloud instances"""
    for instance in nova.list_servers():
        activated_instance = nova.shutoff_server(instance)
        time.sleep(3)
        instance_info = 'instance {nova_instance} is {state} on {host}'.format(
            nova_instance=activated_instance.name,
            state=activated_instance.status,
            host=activated_instance._info[  # pylint: disable=W0212
                'OS-EXT-SRV-ATTR:hypervisor_hostname'])
        LOG.info(instance_info)
        if activated_instance.status != 'SHUTOFF':
            tobiko.fail(instance_info)


def wait_for_all_instances_status(status, timeout=None):
    """wait for all instances for a certain status or raise an exception"""
    for instance in nova.list_servers():
        nova.wait_for_server_status(server=instance.id, status=status,
                                    timeout=timeout)
        instance_info = 'instance {nova_instance} is {state} on {host}'.format(
            nova_instance=instance.name,
            state=status,
            host=instance._info[  # pylint: disable=W0212
                'OS-EXT-SRV-ATTR:hypervisor_hostname'])
        LOG.info(instance_info)


def get_vms_table():
    """populate a dataframe with vm host,id,status"""
    vms_data = [(vm._info[  # pylint: disable=W0212
                     'OS-EXT-SRV-ATTR:hypervisor_hostname'], vm.id,
                 vm.status) for vm in nova.list_servers()]
    vms_df = pandas.DataFrame(vms_data, columns=['vm_host', 'vm_id',
                                                 'vm_state'])
    return vms_df


def list_computes():
    """list compute host names"""
    return [compute.hypervisor_hostname for compute in nova.list_hypervisors()]


def get_compute_vms_df(compute_host):
    """input: compute hostname (can be short)
    output: dataframe with vms of that host"""
    return get_vms_table().query(f"vm_host=='{compute_host}'")


def get_random_compute_with_vms_name():
    """get a randomcompute holding vm/s"""
    for compute in list_computes():
        if not get_compute_vms_df(compute).empty:
            return compute


def vm_info(vm_id, vms_df):
    """input: vm and a vms df
    output: host string"""
    return vms_df.query(f"vm_id == '{vm_id}'").to_string()


def vm_df(vm_id, vms_df):
    """input: vm and a vms df
    output: host string"""
    return vms_df.query(f"vm_id == '{vm_id}'")


def vm_floating_ip(vm_id):
    """input: vm_id
    output it's floating ip"""

    vm = nova.get_server(vm_id)
    floating_ip = nova.list_server_ip_addresses(
        vm, address_type='floating').first
    return floating_ip


def check_ping_vm_fip(fip):
    ping.ping_until_received(fip).assert_replied()


def check_df_vms_ping(df):
    """input: dataframe with vms_ids
    try to ping all vms in df"""

    for vm_id in df.vm_id.to_list():
        check_ping_vm_fip(vm_floating_ip(vm_id))


def vm_location(vm_id, vms_df):
    """input: vm and a vms df
    output: host string"""
    return vms_df.query(f"vm_id == '{vm_id}'")['vm_host'].to_string(
            index=False)


def check_vm_evacuations(vms_df_old=None, compute_host=None, timeout=600,
                         interval=2, check_no_evacuation=False):
    """check evacuation of vms
    input: old and new vms_state_tables dfs"""
    failures = []
    start = time.time()

    while time.time() - start < timeout:
        failures = []
        vms_df_new = get_compute_vms_df(compute_host)
        for vm_id in vms_df_old.vm_id.to_list():
            old_bm_host = vm_location(vm_id, vms_df_old)
            new_vm_host = vm_location(vm_id, vms_df_new)

            if check_no_evacuation:
                cond = bool(old_bm_host != new_vm_host)
            else:
                cond = bool(old_bm_host == new_vm_host)

            if cond:
                failures.append(
                    'failed vm evacuations: {}\n\n'.format(vm_info(vm_id,
                                                           vms_df_old)))
            if failures:
                LOG.info('Failed nova evacuation:\n {}'.format(failures))
                LOG.info('Not all nova vms evacuated ..')
                LOG.info('Retrying , timeout at: {}'
                         .format(timeout-(time.time() - start)))
                time.sleep(interval)
            else:
                LOG.info(vms_df_old.to_string())
                LOG.info('All vms were evacuated!')
                return
    # exhausted all retries
    if failures:
        tobiko.fail(
            'failed vm evacuations:\n{!s}', '\n'.join(failures))


def get_stack_server_id(stack):
    return stack.server_details.id


def get_fqdn_from_topology_node(topology_node):
    return sh.execute("hostname -f", ssh_client=topology_node.ssh_client,
                      expect_exit_status=None).stdout.strip()


def check_vm_running_via_virsh(topology_compute, vm_id):
    """check that a vm is in running state via virsh command,
    return false if not"""
    if vm_id in get_vm_uuid_list_running_via_virsh(topology_compute):
        return True
    else:
        return False


def get_vm_uuid_list_running_via_virsh(topology_compute):
    if overcloud.has_overcloud():
        container_runtime = containers.get_container_runtime_name()
        nova_libvirt = containers.get_libvirt_container_name()
        command = f"sudo {container_runtime} exec {nova_libvirt} " \
                  f"sh -c 'for i in `virsh list --name --state-running` " \
                  f";do virsh domuuid $i;done'"
    else:
        command = "for i in `sudo virsh list --name --state-running` " \
                  ";do virsh domuuid $i;done'"
    return sh.execute(command,
                      ssh_client=topology_compute.ssh_client).stdout.split()


def check_computes_vms_running_via_virsh():
    """check all vms are running via virsh list command"""
    for compute in topology.list_openstack_nodes(group='compute'):
        hostname = get_fqdn_from_topology_node(compute)
        retry = tobiko.retry(timeout=120, interval=5)
        vms_df = get_compute_vms_df(hostname)
        for vm_id in vms_df.vm_id.to_list():
            for _ in retry:
                if check_vm_running_via_virsh(compute, vm_id):
                    LOG.info(f"{vm_id} is running ok on "
                             f"{compute.hostname}")
                    break
                else:
                    LOG.info(f"{vm_id} is not in running state on "
                             f"{compute.hostname}")


def get_nova_server_floating_ip():
    """get an a running's vm floating_ip"""
    return tobiko.setup_fixture(
           stacks.CirrosServerStackFixture).floating_ip_address


# Test is inteded for D/S env
@tripleo.skip_if_missing_overcloud
def check_or_start_background_vm_ping():
    """Check if process exists, if so stop and check ping health
    if not : start a new separate ping process.
    Executes a Background ping to a vm floating_ip,
    this test is intended to be run and picked up again
    by the next tobiko run. Ping results are parsed
    and a failure is raised if ping failure is above a certain amount"""
    ping_vm_fip = get_nova_server_floating_ip()
    sh.check_or_start_background_process(
        bg_function=ping.write_ping_to_file,
        bg_process_name='tobiko_background_ping',
        check_function=ping.check_ping_statistics,
        ping_ip=ping_vm_fip)


# Test is inteded for D/S env
@tripleo.skip_if_missing_overcloud
def skip_check_or_start_background_vm_ping():
    """Like the above, but skips the ping check, truncates results
    and reexecutes the test"""
    ping_vm_fip = get_nova_server_floating_ip()
    sh.check_or_start_background_process(
        bg_function=ping.write_ping_to_file,
        bg_process_name='tobiko_background_ping',
        check_function=ping.skip_check_ping_statistics,
        ping_ip=ping_vm_fip)


def skip_background_vm_ping_checks(func):
    """Skip ping_check_decorator - to be used when traffic to vm
    must be dropped for the duration of the test - func"""
    @wraps(func)
    def wrapper(*args):  # pylint: disable=W0613
        tobiko.add_cleanup(skip_check_or_start_background_vm_ping)
        check_or_start_background_vm_ping()
        func(*args)
    return wrapper


def skip_background_vm_ping_checks_when_nondvr(func):
    """Similar to skip_background_vm_ping_checks, but the background ping
    checks and the restart of the background ping process is only executed when
    DVR is disabled"""
    @wraps(func)
    def wrapper(*args):  # pylint: disable=W0613
        if not overcloud.is_dvr_enabled():
            tobiko.add_cleanup(skip_check_or_start_background_vm_ping)
            check_or_start_background_vm_ping()
        func(*args)
    return wrapper
