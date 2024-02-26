from __future__ import absolute_import

import enum
import io
import time

from oslo_log import log
import pandas

import tobiko
from tobiko import config
from tobiko.tripleo import overcloud
from tobiko.shell import sh
from tobiko.shell import ssh
from tobiko.openstack import topology


CONF = config.CONF
LOG = log.getLogger(__name__)

GALERA_RESOURCE = "galera-bundle"
HAPROXY_RESOURCE = "haproxy-bundle"
OVN_DBS_RESOURCE = "ovn-dbs-bundle"


class PcsResourceException(tobiko.TobikoException):
    message = "pcs cluster is not in a healthy state"


def get_pcs_resources_table(timeout=720, interval=2) -> pandas.DataFrame:
    """
    get pcs status from a controller and parse it
    to have it's resources states in check
       returns :
       rabbitmq-bundle-0    (ocf::heartbeat:rabbitmq-cluster):      Started con
       troller-0
     ip-10.0.0.101  (ocf::heartbeat:IPaddr2):       Started controller-1
       openstack-cinder-volume-docker-0     (ocf::heartbeat:docker):        Sta
       rted controller-0

    :return: dataframe of pcs resources stats table
    """
    # prevent pcs table read failure while pacemaker is starting
    for attempt in tobiko.retry(timeout=timeout,
                                interval=interval):
        try:
            output = run_pcs_status(options=['resources'], grep_str='ocf')
            # remove the first column when it only includes '*' characters
            output = output.replace('*', '').strip()
            stream = io.StringIO(output)
            table: pandas.DataFrame = pandas.read_csv(
                stream, delim_whitespace=True, header=None)
            table.columns = ['resource', 'resource_type', 'resource_state',
                             'overcloud_node']
        except (ValueError, sh.ShellCommandFailed, sh.ShellTimeoutExpired):
            if attempt.is_last:
                raise
            LOG.exception('Failed to obtain pcs status table - Retrying...')
        else:
            break

    LOG.debug("Got pcs status :\n%s", table)
    return table


def get_pcs_prefix_and_status_values():
    if topology.verify_osp_version('17.0', lower=True):
        ocf_prefix = "ocf::"
        promoted_status_str = "Master"
        unpromoted_status_str = "Slave"
    else:
        ocf_prefix = "ocf:"
        promoted_status_str = "Promoted"
        unpromoted_status_str = "Unpromoted"
    return ocf_prefix, promoted_status_str, unpromoted_status_str


class PacemakerResourcesStatus(object):
    """
    class to handle pcs resources checks
    """
    def __init__(self):
        self.pcs_df = get_pcs_resources_table()
        (self.ocf_prefix,
         self.promoted_status_str,
         self.unpromoted_status_str) = get_pcs_prefix_and_status_values()

    def container_runtime(self):

        if not self.pcs_df[(self.pcs_df['resource_type'] ==
                            f"({self.ocf_prefix}heartbeat:docker):")].empty:
            return 'docker'
        if not self.pcs_df[(self.pcs_df['resource_type'] ==
                            f"({self.ocf_prefix}heartbeat:podman):")].empty:
            return 'podman'

    def resource_count(self, resource_type):
        return self.pcs_df[(self.pcs_df['resource_type'] == resource_type)][
            'resource_state'].count()

    def resource_count_in_state(self, resource_type, resource_state):
        return self.pcs_df[(self.pcs_df['resource_type'] ==
                            resource_type) & (self.pcs_df['resource_state'] ==
                                              resource_state)][
            'resource_state'].count()

    def rabbitmq_resource_healthy(self):
        rabbitmq_resource_str = \
            f"({self.ocf_prefix}heartbeat:rabbitmq-cluster):"
        nodes_num = self.resource_count(rabbitmq_resource_str)
        started_num = self.resource_count_in_state(
            rabbitmq_resource_str, "Started")
        if nodes_num == started_num and nodes_num > 0:
            LOG.info("pcs status check: resource rabbitmq is in healthy state")
            return True
        else:
            LOG.info("pcs status check: resource rabbitmq not in healthy "
                     "state")
            return False

    def galera_resource_healthy(self):
        galera_resource_str = f"({self.ocf_prefix}heartbeat:galera):"
        nodes_num = self.resource_count(galera_resource_str)
        master_num = self.resource_count_in_state(
            galera_resource_str, self.promoted_status_str)
        if nodes_num == master_num and nodes_num > 0:
            LOG.info("pcs status check: resource galera is in healthy state")
            return True
        else:
            LOG.info("pcs status check: resource galera not in healthy state")
            return False

    def redis_resource_healthy(self):
        redis_resource_str = f"({self.ocf_prefix}heartbeat:redis):"
        if not overcloud.is_redis_expected():
            LOG.info("redis resource not expected on OSP 17 "
                     "and later releases by default")
            return self.pcs_df.query(
                f'resource_type == "{redis_resource_str}"').empty
        nodes_num = self.resource_count(redis_resource_str)
        master_num = self.resource_count_in_state(
            redis_resource_str, self.promoted_status_str)
        slave_num = self.resource_count_in_state(
            redis_resource_str, self.unpromoted_status_str)
        if (master_num == 1) and (slave_num == nodes_num - master_num):
            LOG.info("pcs status check: resource redis is in healthy state")
            return True
        else:
            LOG.info("pcs status check: resource redis not in healthy state")
            return False

    def vips_resource_healthy(self):
        if CONF.tobiko.rhosp.has_external_load_balancer:
            LOG.info("external load balancer used - "
                     "we can skip vips_resource sanity")
            return True
        else:
            vips_resource_str = f"({self.ocf_prefix}heartbeat:IPaddr2):"
            nodes_num = self.resource_count(vips_resource_str)
            started_num = self.resource_count_in_state(
                vips_resource_str, "Started")
            if nodes_num == started_num and nodes_num > 0:
                LOG.info("pcs status check: resources vips are "
                         "in healthy state")
                return True
            else:
                LOG.info(
                    "pcs status check: resources"
                    " vips are not in healthy state")
                return False

    def ha_proxy_cinder_healthy(self):
        if CONF.tobiko.rhosp.has_external_load_balancer:
            LOG.info("external load balancer used "
                     "- we can skip ha_proxy_resource sanity")
            return True
        else:
            ha_proxy_resource_str = (f"({self.ocf_prefix}heartbeat:"
                                     f"{self.container_runtime()}):")
            nodes_num = self.resource_count(ha_proxy_resource_str)
            started_num = self.resource_count_in_state(
                ha_proxy_resource_str, "Started")
            if nodes_num == started_num and nodes_num > 0:
                LOG.info("pcs status check: resources ha_proxy and"
                         " cinder are in healthy state")
                return True
            else:
                LOG.info(
                    "pcs status check: resources ha_proxy and cinder "
                    "are not in healthy state")
                return False

    def ovn_resource_healthy(self):
        ovn_resource_str = f"({self.ocf_prefix}ovn:ovndb-servers):"
        if self.pcs_df.query(
                f'resource_type == "{ovn_resource_str}"').empty:
            LOG.info('pcs status check: ovn is not deployed, skipping ovn '
                     'resource check')
            return True
        nodes_num = self.resource_count(ovn_resource_str)
        master_num = self.resource_count_in_state(
            ovn_resource_str, self.promoted_status_str)
        slave_num = self.resource_count_in_state(
            ovn_resource_str, self.unpromoted_status_str)
        if (master_num == 1) and (slave_num == nodes_num - master_num):
            LOG.info(
                "pcs status check: resource ovn is in healthy state")
            return True
        else:
            LOG.info(
                "pcs status check: resource ovn is in not in "
                "healthy state")
            return False

    @property
    def all_healthy(self):
        """
        check if each resource is in healthy order
        and return a global healthy status
        :return: Bool
        """
        for attempt_number in range(360):

            try:

                if all([
                   self.rabbitmq_resource_healthy(),
                   self.galera_resource_healthy(),
                   self.redis_resource_healthy(),
                   self.vips_resource_healthy(),
                   self.ha_proxy_cinder_healthy(),
                   self.ovn_resource_healthy()
                   ]):
                    LOG.info("pcs status checks: all resources are"
                             " in healthy state")
                    return True
                else:

                    LOG.info("pcs status check: not all resources are "
                             "in healthy "
                             "state")
                    raise PcsResourceException()
            except PcsResourceException:
                # reread pcs status
                LOG.info('Retrying pacemaker resource checks attempt '
                         '{} of 360'.format(attempt_number))
                time.sleep(1)
                self.pcs_df = get_pcs_resources_table()
        # exhausted all retries
        tobiko.fail('pcs cluster is not in a healthy state')


def get_overcloud_nodes_running_pcs_resource(resource=None,
                                             resource_type=None,
                                             resource_state=None):
    """
    Check what nodes are running the specified resource/type/state
    resource/type/state: exact str of a resource name as seen in pcs status
    :return: list of overcloud nodes
    """
    # pylint: disable=no-member
    pcs_df = get_pcs_resources_table()
    if resource:
        pcs_df_query_resource = pcs_df.query('resource=="{}"'.format(
                                        resource))
        return pcs_df_query_resource['overcloud_node'].unique().tolist()

    if resource_type and resource_state:
        pcs_df_query_resource_type_state = pcs_df.query(
            'resource_type=="{}" and resource_state=="{}"'.format(
                resource_type, resource_state))
        return pcs_df_query_resource_type_state[
            'overcloud_node'].unique().tolist()

    if resource_type and not resource_state:
        pcs_df_query_resource_type = pcs_df.query(
            'resource_type=="{}"'.format(resource_type))
        return pcs_df_query_resource_type['overcloud_node'].unique().tolist()


def get_resource_master_node(resource_type=None):
    get_overcloud_nodes_running_pcs_resource(
        resource_type=resource_type, resource_state='Master')


def get_ovn_db_master_node():
    ocf_prefix, promoted_status_str, _ = get_pcs_prefix_and_status_values()
    return get_overcloud_nodes_running_pcs_resource(
        resource_type=f'({ocf_prefix}ovn:ovndb-servers):',
        resource_state=promoted_status_str)


def get_overcloud_resource(resource_type=None,
                           resource_state=None):
    """
    Check what nodes are running the specified resource/type/state
    resource/type/state: exact str of a resource name as seen in pcs status
    :return: list of overcloud nodes
    """
    pcs_df = get_pcs_resources_table()

    if resource_type and resource_state:
        pcs_df_query_resource_type_state = pcs_df.query(
            'resource_type=="{}" and resource_state=="{}"'.format(
                resource_type, resource_state))
        return pcs_df_query_resource_type_state[
            'resource'].unique().tolist()

    if resource_type and not resource_state:
        # pylint: disable=no-member
        pcs_df_query_resource_type = pcs_df.query(
            'resource_type=="{}"'.format(resource_type))
        return pcs_df_query_resource_type['resource'].unique().tolist()


def instanceha_deployed():
    """check IHA deployment
    checks for existence of the nova-evacuate resource"""
    if overcloud.has_overcloud():
        return get_overcloud_nodes_running_pcs_resource(
            resource='nova-evacuate')
    else:
        return False


skip_if_instanceha_not_delpoyed = tobiko.skip_unless(
    'instanceha not delpoyed', instanceha_deployed)


def fencing_deployed():
    """check fencing deployment
    checks for existence of the stonith-fence type resources"""
    fencing_output = run_pcs_status(grep_str="stonith:fence_ipmilan")

    if fencing_output:
        return True
    else:
        return False


skip_if_fencing_not_deployed = tobiko.skip_unless(
    'fencing not delpoyed', fencing_deployed)


def run_pcs_status(ssh_client: ssh.SSHClientFixture = None,
                   options: list = None,
                   grep_str: str = None) -> str:
    command_args = ['status']
    command_args += options or []

    output = execute_pcs(command_args,
                         ssh_client=ssh_client,
                         sudo=True)

    if not grep_str:
        return output

    output_ocf_lines = []
    for line in output.splitlines():
        if grep_str in line:
            output_ocf_lines.append(line)

    return '\n'.join(output_ocf_lines)


class PcsResourceOperation(enum.Enum):
    DISABLE = "disable"
    ENABLE = "enable"
    RESTART = "restart"
    SHOW = "show"

    def __init__(self, pcsoperation: str):
        self.pcsoperation = pcsoperation


DISABLE = PcsResourceOperation.DISABLE
ENABLE = PcsResourceOperation.ENABLE
RESTART = PcsResourceOperation.RESTART
SHOW = PcsResourceOperation.SHOW


def run_pcs_resource_operation(resource: str,
                               operation: PcsResourceOperation,
                               ssh_client: ssh.SSHClientFixture = None,
                               node: str = None,
                               operation_wait: int = 60,
                               retry_timeout: float = 180.,
                               retry_interval: float = 5.) -> str:
    tobiko.check_valid_type(operation, PcsResourceOperation)

    command_args = ['resource', operation.pcsoperation, resource]
    if node is not None:
        command_args.append(node)

    command_args.append(f'--wait={operation_wait}')

    # add stderr to the output if the operation is disable or enable
    add_stderr = operation in (DISABLE, ENABLE)
    # execute the command with retries
    for attempt in tobiko.retry(timeout=retry_timeout,
                                interval=retry_interval):
        try:
            output = execute_pcs(command_args,
                                 ssh_client=ssh_client,
                                 add_stderr=add_stderr,
                                 timeout=operation_wait + 10.,
                                 sudo=True)
        except sh.ShellCommandFailed as exc:
            if attempt.is_last:
                raise exc
            else:
                LOG.info('the pcs command failed - retrying...')
                continue
        break
    return output


PCS_COMMAND = sh.shell_command(['pcs'])


def execute_pcs(command_args: list,
                ssh_client: ssh.SSHClientFixture = None,
                pcs_command: sh.ShellCommand = None,
                add_stderr: bool = False,
                timeout: float = 40.,
                **execute_params) -> str:
    if ssh_client is None:
        ssh_client = topology.find_openstack_node(
            group='controller').ssh_client

    if pcs_command:
        pcs_command = sh.shell_command(pcs_command)
    else:
        pcs_command = PCS_COMMAND

    command = pcs_command + command_args
    result = sh.execute(
        command, ssh_client=ssh_client, stdin=False, stdout=True, stderr=True,
        timeout=timeout, **execute_params)

    if add_stderr:
        output = '\n'.join([result.stdout, result.stderr])
    else:
        output = result.stdout
    return output
