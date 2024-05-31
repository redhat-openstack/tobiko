# Copyright 2019 Red Hat
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

import contextlib
import io
import os
import tempfile
import time
import typing  # noqa

from oslo_log import log
import requests

import tobiko
from tobiko.config import get_bool_env
from tobiko.openstack.glance import _client
from tobiko.openstack.glance import _io
from tobiko.openstack import keystone
from tobiko.shell import sh


LOG = log.getLogger(__name__)


class HasImageMixin(_client.HasGlanceClientMixin):

    @property
    def image_id(self):
        raise NotImplementedError

    @property
    def image(self):
        return self.get_image(image_id=self.image_id)


class GlanceImageStatus(object):

    #: The Image service reserved an image ID for the image in the catalog but
    # did not yet upload any image data.
    QUEUED = u'queued'

    #: The Image service is in the process of saving the raw data for the
    # image into the backing store.
    SAVING = u'saving'

    #: The image is active and ready for consumption in the Image service.
    ACTIVE = u'active'

    #: An image data upload error occurred.
    KILLED = u'killed'

    #: The Image service retains information about the image but the image is
    # no longer available for use.
    DELETED = u'deleted'

    #: Similar to the deleted status. An image in this state is not
    # recoverable.
    PENDING_DELETE = u'pending_delete'

    #: The image data is not available for use.
    DEACTIVATED = u'deactivated'

    #: Data has been staged as part of the interoperable image import process.
    # It is not yet available for use. (Since Image API 2.6)
    UPLOADING = u'uploading'

    #: The image data is being processed as part of the interoperable image
    # import process, but is not yet available for use. (Since Image API 2.6)
    IMPORTING = u'importing'


@keystone.skip_unless_has_keystone_credentials()
class GlanceImageFixture(_client.HasGlanceClientMixin, tobiko.SharedFixture):

    image_name: typing.Optional[str] = None
    username: typing.Optional[str] = None
    password: typing.Optional[str] = None
    disabled_algorithms: typing.Optional[typing.Dict[str, typing.Any]] = None
    image = None
    wait_interval = 5.

    def __init__(self,
                 image_name: typing.Optional[str] = None,
                 username: typing.Optional[str] = None, password:
                 typing.Optional[str] = None):
        super(GlanceImageFixture, self).__init__()

        if image_name:
            self.image_name = image_name
        elif not self.image_name:
            self.image_name = self.fixture_name
        tobiko.check_valid_type(self.image_name, str)

        if username:
            self.username = username

        if password:
            self.password = password

    def setup_fixture(self):
        self.setup_image()

    def cleanup_fixture(self):
        self.delete_image()

    def setup_image(self):
        return self.wait_for_image_active()

    def get_image(self, image_id=None, **params):
        if image_id or params:
            image = super(GlanceImageFixture, self).get_image(
                image_id=image_id, **params)
        else:
            image = self.find_image(name=self.image_name, default=None)
        self.image = image
        return image

    def delete_image(self, image_id=None):
        if not image_id:
            image_id = self.image_id
            self.image = None
        LOG.debug('Deleting Glance image %r (%r)...', self.image_name,
                  image_id)
        if _client.delete_image(image_id=image_id, client=self.glance_client):
            LOG.debug('Deleted Glance image %r (%r).', self.image_name,
                      image_id)

    @property
    def image_id(self):
        image = self.image or self.get_image()
        return image and image.id or None

    @property
    def image_status(self):
        image = self.image or self.get_image()
        return image and image.status or GlanceImageStatus.DELETED

    def wait_for_image_active(self, check=True):
        return self.wait_for_image_status(
            expected_status={GlanceImageStatus.ACTIVE}, check=check)

    def wait_for_image_deleted(self, check=True):
        return self.wait_for_image_status(
            expected_status={GlanceImageStatus.DELETED}, check=check)

    def wait_for_getting_active_image(self, check=True):
        return self.wait_for_image_status(
            expected_status=GETTING_ACTIVE_STATUS, check=check)

    def wait_for_image_status(self, expected_status, check=True):
        """Waits for the image to reach the given status."""
        image = self.image or self.get_image()
        while (image and image.status not in expected_status and
               is_image_status_changing(image)):

            LOG.debug("Waiting for %r (id=%r) stack status "
                      "(observed=%r, expected=%r)", self.image_name,
                      image.id, image.status, expected_status)
            time.sleep(self.wait_interval)
            image = self.get_image()

        if check:
            self.check_image_status(image, expected_status)
        return image

    def check_image_status(self, image, expected_status):
        image_status = image and image.status or GlanceImageStatus.DELETED
        if image_status not in expected_status:
            image_id = image and image.id or None
            raise InvalidGlanceImageStatus(image_name=self.image_name,
                                           image_id=image_id,
                                           actual_status=image_status,
                                           expected_status=expected_status)


class UploadGlanceImageFixture(GlanceImageFixture):

    disk_format = "raw"
    container_format = "bare"
    create_image_retries = None
    tags: typing.List[str] = []

    def __init__(self, disk_format=None, container_format=None, tags=None,
                 **kwargs):
        super(UploadGlanceImageFixture, self).__init__(**kwargs)

        if container_format:
            self.container_format = container_format
        tobiko.check_valid_type(self.container_format, str)

        if disk_format:
            self.disk_format = disk_format
        tobiko.check_valid_type(self.disk_format, str)

        self.tags = list(tags or self.tags)
        tobiko.check_valid_type(self.tags, list)

        self.prevent_image_create = get_bool_env('TOBIKO_PREVENT_CREATE')

    def setup_image(self):
        self.create_image()

    def create_image(self, retries=None):
        with self._cleanup_image_ids() as cleanup_image_ids:
            retries = retries or self.create_image_retries or 1
            while retries >= 0:
                image = self.wait_for_getting_active_image(
                    check=(not retries))
                if is_image_getting_active(image):
                    break
                retries -= 1

                if not self.prevent_image_create:
                    if image:
                        LOG.debug('Delete existing image: %r (id=%r)',
                                  self.image_name, image.id)
                        self.delete_image(image.id)
                        self.wait_for_image_deleted()

                    # Cleanup cached objects
                    self.image = image = None

                    LOG.debug('Creating Glance image %r '
                              '(re-tries left %d)...',
                              self.image_name, retries)
                    image_id = _client.create_image(
                        **self.create_image_parameters)['id']

                    cleanup_image_ids.add(image_id)
                    LOG.debug('Created image %r (id=%r)...',
                              self.image_name, image_id)

            if image:
                if image.id in cleanup_image_ids:
                    LOG.debug('Image created: %r (id=%r)',
                              self.image_name, image.id)
                    self.upload_image()
                else:
                    LOG.debug('Existing image found: %r (id=%r)',
                              self.image_name, image.id)

            image = self.wait_for_image_active()
            if image and image.id in cleanup_image_ids:
                # Having an active image we can remove image created from this
                # process from cleanup image list so that it is not going to
                # be deleted
                cleanup_image_ids.remove(image.id)

        return image

    @property
    def create_image_parameters(self):
        return dict(client=self.glance_client,
                    name=self.image_name,
                    disk_format=self.disk_format,
                    container_format=self.container_format,
                    tags=self.tags)

    @contextlib.contextmanager
    def _cleanup_image_ids(self):
        created_image_ids = set()
        try:
            yield created_image_ids
        finally:
            for image_id in created_image_ids:
                LOG.warning("Delete duplicate image %r (id=%r).",
                            self.image_name, image_id)
                try:
                    self.delete_image(image_id)
                except Exception:
                    LOG.exception('Error deleting image %r (%r)',
                                  self.image_name, image_id)

    def upload_image(self):
        self.check_image_status(self.image, {GlanceImageStatus.QUEUED})
        image_data, image_size = self.get_image_data()
        with image_data:
            _client.upload_image(image_id=self.image_id,
                                 image_data=image_data,
                                 image_size=image_size)
            LOG.debug("Image uploaded %r", self.image_name)

    def get_image_data(self):
        raise NotImplementedError


class FileGlanceImageFixture(UploadGlanceImageFixture):

    image_file = None
    image_dir = None
    compression_type = None

    def __init__(self, image_file=None, image_dir=None, **kwargs):
        super(FileGlanceImageFixture, self).__init__(**kwargs)

        if image_file:
            self.image_file = image_file
        elif not self.image_file:
            self.image_file = self.fixture_name
        tobiko.check_valid_type(self.image_file, str)

        if image_dir:
            self.image_dir = image_dir
        elif not self.image_dir:
            from tobiko import config
            CONF = config.CONF
            self.image_dir = CONF.tobiko.glance.image_dir or "."
        tobiko.check_valid_type(self.image_dir, str)

    @property
    def real_image_dir(self):
        return os.path.realpath(os.path.expanduser(self.image_dir))

    @property
    def real_image_file(self):
        if '/' in self.image_file:
            return os.path.expanduser(self.image_file)
        return os.path.join(self.real_image_dir, self.image_file)

    def get_image_data(self):
        return self.get_image_file(image_file=self.real_image_file)

    def get_image_file(self, image_file: str):
        image_file = self.customize_image_file(base_file=image_file)
        image_size = os.path.getsize(image_file)
        LOG.debug('Uploading image %r data from file %r (%d bytes)',
                  self.image_name, image_file, image_size)
        image_data = _io.open_image_file(
            filename=image_file, mode='rb',
            compression_type=self.compression_type)
        return image_data, image_size

    def customize_image_file(self, base_file: str) -> str:
        return base_file


class URLGlanceImageFixture(FileGlanceImageFixture):

    image_url: str

    def __init__(self,
                 image_url: str = None,
                 **kwargs):
        super().__init__(**kwargs)
        if image_url is None:
            image_url = self.image_url
        else:
            self.image_url = image_url
        tobiko.check_valid_type(image_url, str)

    def get_image_file(self, image_file: str):
        # pylint: disable=missing-timeout
        http_request = requests.get(self.image_url, stream=True)
        expected_size = int(http_request.headers.get('content-length', 0))
        chunks = http_request.iter_content(chunk_size=io.DEFAULT_BUFFER_SIZE)
        try:
            http_request.raise_for_status()
        except requests.exceptions.HTTPError:
            error_content = b''.join(chunks).decode()
            LOG.exception("Error getting image file from URL: "
                          f"{self.image_url}:\n"
                          f"{error_content}")
            raise

        download_image = True
        if expected_size:
            try:
                actual_size = os.path.getsize(image_file)
            except Exception as ex:
                LOG.debug("Unable to get image %r data from file %r: %s",
                          self.image_name, image_file, ex)
            else:
                if actual_size == expected_size:
                    LOG.debug("Cached image %r file %r found (%d bytes)",
                              self.image_name, image_file, actual_size)
                    download_image = False

        if download_image:
            LOG.debug("Downloading image %r from URL %r to file %r "
                      "(%d bytes)", self.image_name, self.image_url,
                      image_file, expected_size)
            self._download_image_file(image_file=image_file,
                                      chunks=chunks,
                                      expected_size=expected_size)
        return super(URLGlanceImageFixture, self).get_image_file(
            image_file=image_file)

    def _download_image_file(self, image_file, chunks, expected_size):
        image_dir = os.path.dirname(image_file)
        LOG.debug('Ensure image directory exists: %r', image_dir)
        tobiko.makedirs(image_dir)

        fd, temp_file = tempfile.mkstemp(dir=image_dir)
        with io.open(fd, 'wb', io.DEFAULT_BUFFER_SIZE) as image_data:
            for chunk in chunks:
                image_data.write(chunk)

        actual_size = os.path.getsize(temp_file)
        LOG.debug('Downloaded image %r from URL %r to file %r (%d bytes)',
                  self.image_name, self.image_url, image_file,
                  actual_size)

        if expected_size and actual_size != expected_size:
            message = "Download file size mismatch: {!s} != {!r}".format(
                expected_size, actual_size)
            raise RuntimeError(message)
        os.rename(temp_file, image_file)


class CustomizedGlanceImageFixture(FileGlanceImageFixture):

    @property
    def firstboot_commands(self) -> typing.List[str]:
        return []

    @property
    def install_packages(self) -> typing.List[str]:
        return []

    @property
    def run_commands(self) -> typing.List[str]:
        return []

    @property
    def write_files(self) -> typing.Dict[str, str]:
        return {}

    username: str = ''
    password: str = ''

    def _get_customized_suffix(self) -> str:
        return 'customized'

    def customize_image_file(self, base_file: str) -> str:
        customized_file = f'{base_file}-{self._get_customized_suffix()}'
        if os.path.isfile(customized_file):
            if (os.stat(base_file).st_mtime_ns <
                    os.stat(customized_file).st_mtime_ns):
                LOG.debug(f"Image file is up to date '{customized_file}'")
                return customized_file
            else:
                LOG.debug(f"Remove obsolete image file '{customized_file}'")
                os.remove(customized_file)
        work_file = sh.execute('mktemp').stdout.strip()
        try:
            LOG.debug(f"Copy base image file: '{base_file}' to '{work_file}'")
            sh.put_file(base_file, work_file)

            options = self.get_virt_customize_options()
            if options:
                command = sh.shell_command(['LIBGUESTFS_BACKEND=direct',
                                            'virt-customize',
                                            '-a',
                                            work_file])
                sh.execute(command + options)

            sh.get_file(work_file, customized_file)
            return customized_file
        finally:
            sh.execute(['rm', '-f', work_file])

    def get_virt_customize_options(self) -> sh.ShellCommand:
        options = sh.ShellCommand()

        firstboot_commands = self.firstboot_commands
        if firstboot_commands:
            for cmd in firstboot_commands:
                options += ['--firstboot-command', cmd]

        install_packages = self.install_packages
        if install_packages:
            options += ['--install', ','.join(install_packages)]

        username = self.username
        password = self.password
        if username and password:
            options += f'--password "{username}:password:{password}"'

        run_commands = self.run_commands
        if run_commands:
            for cmd in run_commands:
                options += ['--run-command', cmd]

        write_files = self.write_files
        if write_files:
            for filename, content in write_files.items():
                options += ['--write', f'{filename}:{content}']

        return options


class InvalidGlanceImageStatus(tobiko.TobikoException):
    message = ("Invalid image {image_name!r} (id {image_id!r}) status: "
               "{actual_status!r} not in {expected_status!r}")


class GlanceImageCreationFailed(tobiko.TobikoException):
    message = ("Failed creating image {image_name!r}: status "
               "({observed!r}) not in ({expected!r})")


CHANGING_STATUS = {GlanceImageStatus.QUEUED,
                   GlanceImageStatus.IMPORTING,
                   GlanceImageStatus.PENDING_DELETE,
                   GlanceImageStatus.SAVING,
                   GlanceImageStatus.UPLOADING}


def is_image_status_changing(image):
    return image and image.status in CHANGING_STATUS


GETTING_ACTIVE_STATUS = {GlanceImageStatus.QUEUED,
                         GlanceImageStatus.SAVING,
                         GlanceImageStatus.ACTIVE}


def is_image_getting_active(image):
    return image and image.status in GETTING_ACTIVE_STATUS
