# Copyright (c) 2022 Red Hat, Inc.
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
import typing

from oslo_log import log

import tobiko
from tobiko.shell import sh
from tobiko.shell import ssh


LOG = log.getLogger(__name__)


class AnsiblePlaybook(tobiko.SharedFixture):

    def __init__(self,
                 command: sh.ShellCommandType = 'ansible-playbook',
                 inventory_filenames: typing.Iterable[str] = None,
                 playbook: str = 'main',
                 playbook_dirname: str = None,
                 requirement_files: typing.Iterable[str] = None,
                 roles_path: typing.Iterable[str] = None,
                 ssh_client: ssh.SSHClientType = None,
                 verbosity: int = None,
                 work_dir: str = None):
        super(AnsiblePlaybook, self).__init__()
        self._command = sh.shell_command(command)
        if inventory_filenames is None:
            inventory_filenames = []
        self._inventory_filenames = list(inventory_filenames)
        self._playbook = playbook
        self._playbook_dirname = playbook_dirname
        if requirement_files is None:
            requirement_files = []
        self._requirement_files = list(requirement_files)
        self._roles_path = roles_path
        self._ssh_client = ssh_client
        self._verbosity = verbosity
        self._work_dir = work_dir
        self._work_files: typing.Dict[str, str] = {}

    @property
    def ssh_client(self) -> ssh.SSHClientType:
        return self._ssh_client

    _connection: typing.Optional[sh.ShellConnection] = None

    @property
    def connection(self) -> sh.ShellConnection:
        if self._connection is None:
            self._connection = sh.shell_connection(self.ssh_client)
        return self._connection

    @property
    def work_dir(self) -> str:
        if self._work_dir is None:
            self._work_dir = self.connection.make_temp_dir(auto_clean=False)
            self._work_files = {}
        return self._work_dir

    @property
    def playbook_dirname(self) -> str:
        return tobiko.check_valid_type(self._playbook_dirname, str)

    @property
    def roles_path(self) -> typing.List[str]:
        roles_path = self._roles_path
        if roles_path is None:
            if roles_path is None:
                roles_path = []
            else:
                roles_path = list(roles_path)
            playbook_dirname = self._playbook_dirname
            if playbook_dirname is not None:
                playbook_roles_dir = os.path.join(playbook_dirname, 'roles')
                roles_path = ([playbook_roles_dir] +
                              roles_path +
                              [playbook_dirname])
            self._roles_path = roles_path
        return list(roles_path)

    @property
    def verbosity(self) -> typing.Optional[int]:
        if self._verbosity is None:
            self._verbosity = tobiko.tobiko_config().ansible.verbosity
        return self._verbosity

    def _ensure_inventory_files(self, *inventory_filenames: str) \
            -> typing.List[str]:
        filenames = list(inventory_filenames)
        filenames.extend(self._inventory_filenames)
        filenames.extend(tobiko.tobiko_config().ansible.inventory_files)
        existing_filenames = []
        for filename in sorted(filenames):
            filename = tobiko.tobiko_config_path(filename)
            if (filename not in existing_filenames and
                    os.path.isfile(filename)):
                existing_filenames.append(filename)
        if existing_filenames:
            self._ensure_work_files(*existing_filenames, sub_dir='inventory')
            return [os.path.join(self.work_dir, 'inventory')]
        dump_filenames = '  \n'.join(filenames)
        LOG.warning("Any Ansible inventory file(s) found:\n"
                    f"  {dump_filenames}\n")
        return []

    def _get_playbook_filename(self,
                               basename: str = None,
                               dirname: str = None) -> str:
        if basename is None:
            basename = self._playbook
        if dirname is None:
            dirname = self.playbook_dirname
        return os.path.join(dirname, basename)

    def _ensure_roles(self, roles: typing.Iterable[str],
                      dirname: str = None,
                      roles_path: typing.Iterable[str] = None) \
            -> typing.List[str]:
        role_dirs = []
        for role in roles:
            if roles_path is None:
                roles_path = self.roles_path
            else:
                roles_path = list(roles_path)
            if dirname is not None:
                dirname = os.path.realpath(dirname)
                roles_path = ([os.path.join(dirname, 'roles')] +
                              roles_path +
                              [dirname])
            for roles_dir in roles_path:
                role_dir = os.path.join(roles_dir, role)
                if os.path.isdir(role_dir):
                    role_dirs.append(role_dir)
                    break
            else:
                raise ValueError(
                    f'Role {role} not found in directories {self.roles_path}')
        return self._ensure_work_files(*role_dirs, sub_dir='roles')

    def _ensure_playbook_files(self,
                               playbook_files: typing.Iterable[str],
                               sub_dir: str = None,
                               dirname: str = None) -> typing.List[str]:
        work_filenames = []
        for playbook_file in playbook_files:
            filename = self._get_playbook_filename(basename=playbook_file,
                                                   dirname=dirname)
            if sub_dir is None and dirname is not None:
                if filename.startswith(dirname):
                    sub_dir = os.path.relpath(os.path.dirname(filename),
                                              dirname)

            work_filename = self._ensure_work_file(filename=filename,
                                                   sub_dir=sub_dir)
            work_filenames.append(work_filename)
        return work_filenames

    def _ensure_work_file(self, filename: str, sub_dir: str = None) -> str:
        filename = os.path.realpath(filename)
        work_filename = self._work_files.get(filename)
        if work_filename is None:
            if sub_dir is not None:
                work_filename = os.path.join(
                    self.work_dir, sub_dir, os.path.basename(filename))
            else:
                work_filename = os.path.join(
                    self.work_dir, os.path.basename(filename))
            if sub_dir is not None:
                self.connection.make_dirs(os.path.dirname(work_filename))
            self.connection.put_file(filename, work_filename)
            self._work_files[filename] = work_filename
        return work_filename

    def _ensure_work_files(self, *filenames: str, sub_dir: str = None) \
            -> typing.List[str]:
        missing_filenames = set()
        work_filenames = set()
        for filename in filenames:
            filename = os.path.realpath(filename)
            work_filename = self._work_files.get(filename)
            if work_filename is None:
                missing_filenames.add(filename)
            else:
                work_filenames.add(work_filename)
        if missing_filenames:
            if sub_dir is None:
                work_dir = self.work_dir
            else:
                work_dir = os.path.join(self.work_dir, sub_dir)
            self.connection.put_files(*sorted(missing_filenames),
                                      remote_dir=work_dir)
            for filename in filenames:
                work_filename = os.path.join(
                    work_dir, os.path.basename(filename))
                self._work_files[filename] = work_filename
                work_filenames.add(work_filename)
        return sorted(work_filenames)

    def cleanup_fixture(self):
        self._connection = None
        self._work_files = None
        if self._work_dir is not None:
            self.connection.remove_files(self._work_dir)
            self._work_dir = None

    def _get_command(self,
                     command: sh.ShellCommandType = None,
                     playbook: str = None,
                     playbook_dirname: str = None,
                     playbook_filename: str = None,
                     inventory_filenames: typing.Iterable[str] = None,
                     playbook_files: typing.Iterable[str] = None,
                     requirements_files: typing.Iterable[str] = None,
                     roles: typing.Iterable[str] = None,
                     roles_path: typing.Iterable[str] = None,
                     verbosity: int = None) -> \
            sh.ShellCommand:
        # ensure command
        if command is None:
            command = self._command
        assert isinstance(command, sh.ShellCommand)

        if verbosity is None:
            verbosity = self.verbosity
        if verbosity is not None and verbosity > 0:
            command += '-' + ('v' * verbosity)

        # ensure inventory
        if inventory_filenames is None:
            inventory_filenames = []

        for inventory_work_file in self._ensure_inventory_files(*list(
                inventory_filenames)):
            command += ['-i', inventory_work_file]

        # ensure playbook file
        if playbook_filename is None:
            playbook_filename = self._get_playbook_filename(
                basename=playbook, dirname=playbook_dirname)
        else:
            playbook_filename = os.path.realpath(playbook_filename)
        playbook_dirname = os.path.dirname(playbook_filename)
        command += [self._ensure_work_file(playbook_filename)]

        if playbook_files is not None:
            self._ensure_playbook_files(playbook_files=playbook_files,
                                        dirname=playbook_dirname)

        if roles is not None:
            self._ensure_roles(roles=roles,
                               dirname=playbook_dirname,
                               roles_path=roles_path)

        self._ensure_collections(requirements_files=requirements_files,
                                 dirname=playbook_dirname)
        return command

    def _ensure_collections(self,
                            requirements_files: typing.Iterable[str] = None,
                            dirname: str = None):
        work_files = self._ensure_requirements_files(
            requirements_files=requirements_files,
            dirname=dirname)
        if work_files:
            collections_dirname = os.path.join(self.work_dir, 'collections')
            command = sh.shell_command('ansible-galaxy collection install')
            command += ['-p', collections_dirname]
            for work_file in work_files:
                command += ['-r', work_file]
            self.connection.execute(command=command)

    def _ensure_requirements_files(
            self,
            requirements_files: typing.Iterable[str] = None,
            dirname: str = None) \
            -> typing.List[str]:
        if requirements_files is None:
            requirements_files = []
        else:
            requirements_files = list(requirements_files)
        for filename in self._requirement_files:
            if filename not in requirements_files:
                requirements_files.append(filename)
        if requirements_files:
            return self._ensure_playbook_files(
                playbook_files=requirements_files,
                sub_dir='requirements',
                dirname=dirname)
        else:
            return []

    def run_playbook(self,
                     command: sh.ShellCommand = None,
                     playbook: str = None,
                     playbook_dirname: str = None,
                     playbook_filename: str = None,
                     inventory_filenames: typing.Iterable[str] = None,
                     playbook_files: typing.Iterable[str] = None,
                     requirements_files: typing.Iterable[str] = None,
                     roles: typing.Iterable[str] = None,
                     roles_path: typing.Iterable[str] = None,
                     verbosity: int = None):
        tobiko.setup_fixture(self)
        command = self._get_command(command=command,
                                    playbook=playbook,
                                    playbook_dirname=playbook_dirname,
                                    playbook_filename=playbook_filename,
                                    inventory_filenames=inventory_filenames,
                                    playbook_files=playbook_files,
                                    requirements_files=requirements_files,
                                    roles=roles,
                                    roles_path=roles_path,
                                    verbosity=verbosity)
        return self.connection.execute(command, current_dir=self.work_dir)


def local_ansible_playbook() -> 'AnsiblePlaybook':
    return tobiko.get_fixture(AnsiblePlaybook)


def ansible_playbook(ssh_client: ssh.SSHClientType = None,
                     manager: 'AnsiblePlaybookManager' = None) -> \
        'AnsiblePlaybook':
    return ansible_playbook_manager(manager).get_ansible_playbook(
        ssh_client=ssh_client)


def register_ansible_playbook(playbook: 'AnsiblePlaybook',
                              manager: 'AnsiblePlaybookManager' = None) -> \
        None:
    tobiko.check_valid_type(playbook, AnsiblePlaybook)
    ansible_playbook_manager(manager).register_ansible_playbook(playbook)


def ansible_playbook_manager(manager: 'AnsiblePlaybookManager' = None) -> \
        'AnsiblePlaybookManager':
    if manager is None:
        return tobiko.setup_fixture(AnsiblePlaybookManager)
    else:
        tobiko.check_valid_type(manager, AnsiblePlaybookManager)
        return manager


AnsiblePlaybookKey = typing.Optional[ssh.SSHClientFixture]


class AnsiblePlaybookManager(tobiko.SharedFixture):

    def __init__(self):
        super(AnsiblePlaybookManager, self).__init__()
        self._host_playbooks: typing.Dict['AnsiblePlaybookKey',
                                          'AnsiblePlaybook'] = {}

    def get_ansible_playbook(self,
                             ssh_client: ssh.SSHClientType) -> \
            'AnsiblePlaybook':
        ssh_client = ssh.ssh_client_fixture(ssh_client)
        playbook = self._host_playbooks.get(ssh_client)
        if playbook is None:
            playbook = self._init_ansible_playbook(ssh_client=ssh_client)
            self._host_playbooks[ssh_client] = playbook
        return playbook

    def register_ansible_playbook(self, playbook: 'AnsiblePlaybook'):
        ssh_client = ssh.ssh_client_fixture(playbook.ssh_client)
        self._host_playbooks[ssh_client] = playbook

    @staticmethod
    def _init_ansible_playbook(ssh_client: ssh.SSHClientFixture = None) \
            -> 'AnsiblePlaybook':
        if ssh_client is None:
            return local_ansible_playbook()
        else:
            return tobiko.get_fixture(AnsiblePlaybook(ssh_client=ssh_client))


def run_playbook(command: sh.ShellCommand = None,
                 playbook: str = None,
                 playbook_dirname: str = None,
                 playbook_filename: str = None,
                 inventory_filenames: typing.Iterable[str] = None,
                 playbook_files: typing.Iterable[str] = None,
                 roles: typing.Iterable[str] = None,
                 roles_path: typing.Iterable[str] = None,
                 verbosity: int = None,
                 ssh_client: ssh.SSHClientType = None,
                 manager: AnsiblePlaybookManager = None) \
        -> sh.ShellExecuteResult:
    return ansible_playbook(ssh_client=ssh_client,
                            manager=manager).run_playbook(
                            command=command,
                            inventory_filenames=inventory_filenames,
                            playbook=playbook,
                            playbook_dirname=playbook_dirname,
                            playbook_filename=playbook_filename,
                            playbook_files=playbook_files,
                            roles=roles,
                            roles_path=roles_path,
                            verbosity=verbosity)
