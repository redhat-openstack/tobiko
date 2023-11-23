#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
from __future__ import absolute_import


import functools
import subprocess
import os

from oslo_log import log
import podman


import tobiko
from tobiko.podman import _exception
from tobiko.podman import _podman1
from tobiko.podman import _shell
from tobiko.shell import ssh
from tobiko.shell import sh

LOG = log.getLogger(__name__)


def get_podman_client(ssh_client=None):
    return PodmanClientFixture(ssh_client=ssh_client)


def list_podman_containers(client=None, **kwargs):
    try:
        containers = podman_client(client).containers.list(**kwargs)
    except _exception.PodmanSocketNotFoundError:
        return tobiko.Selection()
    else:
        return tobiko.select(containers)


PODMAN_CLIENT_CLASSES = \
    _podman1.Client, podman.PodmanClient  # pylint: disable=E1101


def podman_client(obj=None):
    if obj is None:
        obj = get_podman_client()

    if tobiko.is_fixture(obj):
        obj = tobiko.setup_fixture(obj).client

    if isinstance(obj, PODMAN_CLIENT_CLASSES):
        return obj

    raise TypeError('Cannot obtain a Podman client from {!r}'.format(obj))


@functools.lru_cache()
def podman_version_3():
    try:
        stdout = sh.execute('rpm -q podman').stdout
    except sh.ShellCommandFailed:
        return False

    podman_ver = stdout.split('-')[1].split('.')[0]
    if int(podman_ver) >= 3:
        return True
    else:
        return False


class PodmanClientFixture(tobiko.SharedFixture):

    client = None
    ssh_client = None

    def __init__(self, ssh_client=None):
        super(PodmanClientFixture, self).__init__()
        if ssh_client:
            self.ssh_client = ssh_client

    def setup_fixture(self):
        self.setup_ssh_client()
        self.setup_client()

    def setup_ssh_client(self):
        ssh_client = self.ssh_client
        if ssh_client is None:
            self.ssh_client = ssh_client = ssh.ssh_proxy_client() or False
            if ssh_client:
                tobiko.setup_fixture(ssh_client)
        return ssh_client

    def setup_client(self):
        # podman ver3 (osp>=16.2) has different service / socket paths
        if podman_version_3():
            podman_service = 'podman.socket'
            podman_socket_file = '/run/podman/podman.sock'
        else:
            podman_service = 'io.podman.socket'
            podman_socket_file = '/run/podman/io.podman'

        username = self.ssh_client.get_connect_parameters()['username']
        podman_client_check_status_cmds = (
            "sudo test -f /var/podman_client_access_setup && "
            f"sudo grep {username} /etc/tmpfiles.d/podman.conf")
        podman_client_setup_cmds = \
            f"""sudo groupadd -f podman &&  \
            sudo usermod -a -G podman {username} && \
            sudo chmod -R o=wxr /etc/tmpfiles.d && \
            sudo echo 'd /run/podman 0770 root {username}' >  \
            /etc/tmpfiles.d/podman.conf && \
            sudo cp /lib/systemd/system/{podman_service} \
            /etc/systemd/system/{podman_service} && \
            sudo crudini --set /etc/systemd/system/{podman_service} Socket  \
            SocketMode 0660 && \
            sudo crudini --set /etc/systemd/system/{podman_service} Socket  \
            SocketGroup podman && \
            sudo systemctl daemon-reload && \
            sudo systemd-tmpfiles --create && \
            sudo systemctl enable --now {podman_service} && \
            sudo chmod 777 /run/podman && \
            sudo chown -R root: /run/podman && \
            sudo chmod g+rw {podman_socket_file} && \
            sudo chmod 777 {podman_socket_file} && \
            sudo setenforce 0 && \
            sudo systemctl restart {podman_service} && \
            sudo touch /var/podman_client_access_setup"""

        # check whether client setup was already executed or not
        status_result = sh.execute(podman_client_check_status_cmds,
                                   ssh_client=self.ssh_client,
                                   expect_exit_status=None)
        if status_result.exit_status != 0:
            LOG.debug('executing podman client setup script for user %s',
                      username)
            sh.execute(podman_client_setup_cmds, ssh_client=self.ssh_client)
        else:
            LOG.debug('podman client setup was already completed for user %s',
                      username)

        client = self.client
        if client is None:
            self.client = client = self.create_client()
        return client

    def create_client(self):  # noqa: C901
        for _ in tobiko.retry(timeout=60., interval=5.):
            try:
                podman_remote_socket = self.discover_podman_socket()
                username = self.ssh_client.connect_parameters['username']
                host = self.ssh_client.connect_parameters["hostname"]
                key_files = self.ssh_client.connect_parameters.get(
                    'key_filename', [])
                key_file = key_files[0] if len(key_files) > 0 else None
                socket = podman_remote_socket
                # replace : with . in case of IPv6 addresses
                podman_socket_file = (
                    f'/tmp/podman.sock_{host.replace(":", ".")}')
                podman_remote_socket_uri = f'unix:{podman_socket_file}'

                remote_uri = f'ssh://{username}@{host}{socket}'

                if podman_version_3():
                    # check if a ssh tunnel exists, if not create one
                    psall = str(subprocess.check_output(('ps', '-ef')))
                    if f'ssh -L {podman_socket_file}' not in psall:
                        if os.path.exists(podman_socket_file):
                            subprocess.call(
                                ['rm', '-f', podman_socket_file])
                        # start a background  ssh tunnel with the remote host
                        command = [
                            'ssh', '-o', 'strictHostKeyChecking=no', '-L',
                            f'{podman_socket_file}:/run/podman/podman.sock',
                            '-l', username, host, '-N', '-f']
                        if key_file:
                            command += ['-i', key_file]
                        subprocess.call(command)
                        for _ in tobiko.retry(timeout=60., interval=1.):
                            if os.path.exists(podman_socket_file):
                                break
                    client = podman.PodmanClient(
                        base_url=podman_remote_socket_uri)
                    if client.ping():
                        LOG.info('container_client is online')

                else:
                    client = _podman1.Client(  # pylint: disable=E1101
                        uri=podman_remote_socket_uri,
                        remote_uri=remote_uri,
                        identity_file='~/.ssh/id_rsa')
                    if client.system.ping():
                        LOG.info('container_client is online')
                return client
            except (ConnectionRefusedError, ConnectionResetError):
                # retry
                self.create_client()

    def connect(self):
        return tobiko.setup_fixture(self).client

    def discover_podman_socket(self):
        return _shell.discover_podman_socket(ssh_client=self.ssh_client)
