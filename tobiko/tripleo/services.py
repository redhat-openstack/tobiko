from __future__ import absolute_import

import typing

from oslo_log import log

import tobiko
from tobiko.tripleo import overcloud
from tobiko.shell import sh
from tobiko.shell import ssh


LOG = log.getLogger(__name__)


class OvercloudServiceException(tobiko.TobikoException):
    message = "not all overcloud nodes services are in active state"


def get_overcloud_node_services_table(ssh_client: ssh.SSHClientType):
    """
    get services table from overcloud node

       returns :
auditd.service|loaded|active|running|SecurityAuditingService
auth-rpcgss-module.service|loaded|inactivedead|KernelModulesupportingRPCSEC_GSS
blk-availability.service|loaded|active|exited|Availabilityofblockdevices
brandbot.service|loaded|inactivedead|FlexibleBrandingService
certmonger.service|loaded|active|running|CertificatemonitoringandPKIenrollment
cinder-lvm-losetup.service|loaded|inactivedead|CinderLVMlosetup
cloud-config.service|loaded|active|exited|Applythesettingsspecifiedincloud-con
cloud-final.service|loaded|active|exited|Executeclouduser/finalscripts
cloud-init-local.service|loaded|active|exited|Initialcloud-initjob(pre-network)
cloud-init.service|loaded|active|exited|Initialcloud-initjob(metadataservicecr)

    :return: TableData of overcloud node services
    """
    units = sh.list_systemd_units(all=True,
                                  ssh_client=ssh_client).without_attributes(
        load='not-found')

    data: typing.Dict[str, list] = {'UNIT': [],
                                    'loaded_state': [],
                                    'active_state': [],
                                    'low_level_state': [],
                                    'UNIT_DESCRIPTION': []}
    for unit in units:
        data['UNIT'].append(unit.unit)
        data['loaded_state'].append(unit.load)
        data['active_state'].append(unit.active)
        data['low_level_state'].append(unit.sub)
        data['UNIT_DESCRIPTION'].append(unit.description)
    table = tobiko.TableData.from_dict(data)
    table.replace(to_replace=' ', value="", regex=True, inplace=True)
    # Add hostname to each row
    hostname = sh.get_hostname(ssh_client=ssh_client)
    for row in table:
        row['overcloud_node'] = hostname

    LOG.debug("Got overcloud nodes services status :\n%s", table)
    return table


def get_overcloud_nodes_running_service(service):
    """
    Check what nodes are running the specified service or unit
    process: exact str of a process name as seen in systemctl -a
    :return: list of overcloud nodes
    """
    oc_procs_td = overcloud.get_overcloud_nodes_tabledata(
                                            get_overcloud_node_services_table)
    # remove the ".service" suffix
    oc_procs_td.replace(to_replace={'UNIT': '.service'},
                        value='',
                        regex=True, inplace=True)
    oc_nodes_running_service = oc_procs_td.query(
        'UNIT=="{}"'.format(service))['overcloud_node'].unique()
    return oc_nodes_running_service


class OvercloudServicesStatus(tobiko.SharedFixture):
    """
    class to handle services checks,
    checks that all of these are running in the overcloud:
    'corosync.service','iptables.service','network.service','ntpd.service',
    'pacemaker.service','rpcbind.service','sshd.service'

    """

    SERVICES_TO_CHECK: typing.List[str] = [
        'corosync.service',
        'iptables.service',
        'network.service',
        # Not found on OSP 16
        # 'ntpd.service',
        'pacemaker.service',
        'rpcbind.service',
        'sshd.service']

    def __init__(self,
                 services_to_check: typing.List[str] = None):
        super().__init__()
        if services_to_check is None:
            services_to_check = self.SERVICES_TO_CHECK
        self.services_to_check = services_to_check

    oc_services_td: typing.Any

    def setup_fixture(self):
        self.oc_services_td = overcloud.get_overcloud_nodes_tabledata(
            get_overcloud_node_services_table)

    @property
    def basic_overcloud_services_running(self):
        """
        Checks that the oc_services tabledata has all of the list services
        running
        :return: Bool
        """
        tobiko.setup_fixture(self)
        for service_name in self.services_to_check:
            if not self.oc_services_td.query('UNIT=="{}"'.format(
                    service_name)).empty:
                LOG.info("overcloud processes status checks: process {} is  "
                         "in running state".format(service_name))
                continue
            else:
                LOG.info("Failure : overcloud processes status checks: "
                         "process {} is not running ".format(service_name))
                raise OvercloudServiceException()
        return True
