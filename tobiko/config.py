# Copyright 2018 Red Hat
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

import importlib
import itertools
import logging
import os
import typing  # noqa

from oslo_config import cfg
from oslo_log import log

import tobiko


LOG = log.getLogger(__name__)


CONFIG_MODULES = ['tobiko.common._case',
                  'tobiko.openstack.glance.config',
                  'tobiko.openstack.manila.config',
                  'tobiko.openstack.keystone.config',
                  'tobiko.openstack.neutron.config',
                  'tobiko.openstack.nova.config',
                  'tobiko.openstack.octavia.config',
                  'tobiko.openstack.topology.config',
                  'tobiko.shell.ansible.config',
                  'tobiko.shell.ssh.config',
                  'tobiko.shell.ping.config',
                  'tobiko.shell.iperf3.config',
                  'tobiko.shell.sh.config',
                  'tobiko.shiftstack.config',
                  'tobiko.rhosp.config',
                  'tobiko.podified.config',
                  'tobiko.tripleo.config']


LOGGING_CONF_GROUP_NAME = "logging"

LOGGING_OPTIONS = [
    cfg.BoolOpt('capture_log',
                default=True,
                help="Whenever to report debugging log lines"),
    cfg.StrOpt('line_format',
               default=('%(asctime)s.%(msecs)03d %(process)d %(levelname)s '
                        '%(name)s - %(message)s'),
               help='Default logging line format string'),
    cfg.StrOpt('date_format',
               default='%Y-%m-%d %H:%M:%S',
               help='Default logging date format string'),
]

HTTP_CONF_GROUP_NAME = "http"

HTTP_OPTIONS = [
    cfg.StrOpt('http_proxy',
               help="HTTP proxy URL for Rest APIs"),
    cfg.StrOpt('https_proxy',
               help="HTTPS proxy URL for Rest APIs"),
    cfg.StrOpt('no_proxy',
               help="Don't use proxy server to connect to listed hosts")]

TESTCASE_CONF_GROUP_NAME = "testcase"

TESTCASE_OPTIONS = [
    cfg.FloatOpt('timeout',
                 default=None,
                 help=("Timeout (in seconds) used for interrupting test case "
                       "execution")),
    cfg.FloatOpt('test_runner_timeout',
                 default=None,
                 help=("Timeout (in seconds) used for interrupting test "
                       "runner execution"))]

COMMON_GROUP_NAME = 'common'

COMMON_OPTIONS = [
    cfg.StrOpt('shelves_dir',
               default='~/.tobiko/cache/shelves',
               help="Directory where to look for shelves."),
    cfg.StrOpt('lock_dir',
               default='~/.tobiko/cache/lock',
               help="Directory where lock persistent files will be saved"),
]


def workspace_config_files(project=None, prog=None):
    project = project or 'tobiko'
    filenames = []
    if prog is not None:
        filenames.append(prog + '.conf')
    filenames.append(project + '.conf')
    root_dir = os.path.realpath("/")
    current_dir = os.path.realpath(os.getcwd())
    config_files = []
    while current_dir != root_dir:
        for filename in filenames:
            filename = os.path.join(current_dir, filename)
            if os.path.isfile(filename):
                config_files.append(filename)
        current_dir = os.path.dirname(current_dir)
    return config_files


class GlobalConfig(object):

    # this is a singletone
    _instance = None
    _sources = {}  # type: typing.Dict[str, typing.Any]

    def __new__(cls):
        if cls._instance is None:
            cls._instance = object.__new__(cls)
        return cls._instance

    def set_source(self, name, source_conf):
        if source_conf is None:
            raise TypeError("Config source cannot be None")
        actual = self._sources.setdefault(name, source_conf)
        if actual is not source_conf:
            msg = "Config source already registered: {!r}".format(name)
            raise RuntimeError(msg)

    def __getattr__(self, name):
        sources = self._sources.get(name)
        if sources is None:
            msg = "Config source not registered: {!r}".format(name)
            raise NoSuchConfigSource(msg)
        return sources


CONF = GlobalConfig()


class InitConfigFixture(tobiko.SharedFixture):

    def setup_fixture(self):
        init_tobiko_config()
        init_environ_config()


def init_config():
    tobiko.setup_fixture(InitConfigFixture)


def get_version():
    from tobiko import version
    return version.release


def init_tobiko_config(default_config_dirs=None, default_config_files=None,
                       project=None, prog=None, product_name=None,
                       version=None):

    if project is None:
        project = 'tobiko'

    if product_name is None:
        product_name = 'tobiko'

    if version is None:
        version = get_version()

    if default_config_dirs is None:
        default_config_dirs = cfg.find_config_dirs(project=project, prog=prog)
    if default_config_files is None:
        default_config_files = (cfg.find_config_files(project=project,
                                                      prog=prog) +
                                workspace_config_files(project=project,
                                                       prog=prog))

    # Register configuration options
    conf = cfg.ConfigOpts()
    log.register_options(conf)
    register_tobiko_options(conf=conf)

    # Initialize Tobiko configuration object
    conf(args=[],
         project='tobiko',
         validate_default_values=True,
         default_config_dirs=default_config_dirs,
         default_config_files=default_config_files)
    CONF.set_source('tobiko', conf)

    # expand and normalize log_file and log_dir names
    conf.config_dir = os.path.realpath(conf.find_file('.'))
    log_dir = conf.log_dir or conf.config_dir
    log_file = conf.log_file or 'tobiko.log'
    log_path = os.path.realpath(os.path.expanduser(
        os.path.join(log_dir, log_file)))
    conf.log_dir = os.path.dirname(log_path)
    conf.log_file = os.path.basename(log_path)

    # setup final configuration
    log.setup(conf=conf, product_name=product_name, version=version)
    setup_tobiko_config(conf=conf)
    LOG.debug("Configuration setup using parameters:\n"
              " - product_name: %r\n"
              " - version: %r\n"
              " - default_config_dirs: %r\n"
              " - default_config_files: %r\n"
              " - log_file: %r\n",
              product_name,
              version,
              default_config_dirs,
              default_config_files,
              os.path.join(log_dir, log_file))


def register_tobiko_options(conf):

    conf.register_opts(
        group=cfg.OptGroup(LOGGING_CONF_GROUP_NAME), opts=LOGGING_OPTIONS)

    conf.register_opts(
        group=cfg.OptGroup(HTTP_CONF_GROUP_NAME), opts=HTTP_OPTIONS)

    conf.register_opts(
        group=cfg.OptGroup(TESTCASE_CONF_GROUP_NAME), opts=TESTCASE_OPTIONS)

    conf.register_opts(
        group=cfg.OptGroup(COMMON_GROUP_NAME), opts=COMMON_OPTIONS)

    for module_name in CONFIG_MODULES:
        module = importlib.import_module(module_name)
        if hasattr(module, 'register_tobiko_options'):
            module.register_tobiko_options(conf=conf)


def list_http_options():
    return [
        (HTTP_CONF_GROUP_NAME, itertools.chain(HTTP_OPTIONS))
    ]


def list_testcase_options():
    return [
        (TESTCASE_CONF_GROUP_NAME, itertools.chain(TESTCASE_OPTIONS))
    ]


def list_common_options():
    return [
        (COMMON_GROUP_NAME, itertools.chain(COMMON_OPTIONS))
    ]


def list_tobiko_options():
    all_options = (list_http_options() +
                   list_testcase_options() +
                   list_common_options())

    for module_name in CONFIG_MODULES:
        module = importlib.import_module(module_name)
        if hasattr(module, 'list_options'):
            all_options += module.list_options()
    return all_options


def setup_tobiko_config(conf):
    # Redirect all warnings to logging library
    logging.captureWarnings(True)
    warnings_logger = log.getLogger('py.warnings')
    if conf.debug:
        if not warnings_logger.isEnabledFor(log.WARNING):
            # Print Python warnings
            warnings_logger.logger.setLevel(log.WARNING)
    elif warnings_logger.isEnabledFor(log.WARNING):
        # Silence Python warnings
        warnings_logger.logger.setLevel(log.ERROR)

    tobiko.setup_fixture(HttpProxyFixture)

    for module_name in CONFIG_MODULES:
        module = importlib.import_module(module_name)
        if hasattr(module, 'setup_tobiko_config'):
            module.setup_tobiko_config(conf=conf)


class HttpProxyFixture(tobiko.SharedFixture):
    """Make sure we have http proxy environment variables defined when required
    """

    http_proxy = None
    https_proxy = None
    no_proxy = None
    source = None

    def setup_fixture(self):
        source = None
        http_proxy = os.environ.get('http_proxy')
        https_proxy = os.environ.get('https_proxy')
        no_proxy = os.environ.get('no_proxy')
        if http_proxy or https_proxy:
            source = 'environment'
        else:
            http_conf = CONF.tobiko.http
            http_proxy = http_conf.http_proxy
            https_proxy = http_conf.https_proxy
            no_proxy = http_conf.no_proxy
            if http_proxy:
                os.environ['http_proxy'] = http_proxy
            if https_proxy:
                os.environ['https_proxy'] = https_proxy
            if no_proxy:
                os.environ['no_proxy'] = no_proxy
            if http_proxy or https_proxy or no_proxy:
                source = 'tobiko.conf'

        if source:
            LOG.info("Using HTTP proxy configuration defined in %s:\n"
                     "  http_proxy: %r\n"
                     "  https_proxy: %r\n"
                     "  no_proxy: %r",
                     source, os.environ.get('http_proxy'),
                     os.environ.get('https_proxy'), os.environ.get('no_proxy'))
        else:
            LOG.debug("Connecting to REST API services without a proxy "
                      "server")

        self.source = source
        self.http_proxy = os.environ.get('http_proxy')
        self.https_proxy = os.environ.get('https_proxy')
        self.no_proxy = os.environ.get('no_proxy')


def init_environ_config():
    CONF.set_source('environ', EnvironConfig())


class EnvironConfig(object):

    def __getattr__(self, name):
        value = get_env(name)
        if value is None:
            msg = "Environment variable not defined: {!r}".format(name)
            raise cfg.NoSuchOptError(msg)
        return value


class NoSuchConfigSource(AttributeError):
    pass


def get_any_option(*sources, **kwargs):
    default = kwargs.get('default', None)
    for source in sources:
        value = CONF
        for name in source.split('.'):
            try:
                value = getattr(value, name)
            except (NoSuchConfigSource,
                    cfg.NoSuchOptError,
                    cfg.NoSuchGroupError) as ex:
                LOG.debug("No such option value for %r: %s", source, ex)
                break
        else:
            if value != default:
                return value
    return default


def get_env(name):
    value = os.environ.get(name)
    if value:
        return value
    else:
        LOG.debug("Environment variable %r is not defined", name)
        return None


def get_int_env(name):
    value = get_env(name)
    if value:
        try:
            return int(value)
        except TypeError:
            LOG.exception("Environment variable %r is not an integer: %r",
                          name, value)
    return None


def get_bool_env(name):
    value = get_env(name)
    if value:
        value = str(value).lower()
        if value in ['true', '1', 'yes']:
            return True
        elif value in ['false', '0', 'no']:
            return False
        else:
            LOG.exception("Environment variable %r is not a boolean: %r",
                          name, value)
    return None


def get_list_env(name, separator=','):
    value = get_env(name)
    if value:
        return value.split(separator)
    else:
        return []


def is_prevent_create() -> bool:
    return get_bool_env('TOBIKO_PREVENT_CREATE') is True


def skip_if_prevent_create(reason='TOBIKO_PREVENT_CREATE is True'):
    return tobiko.skip_if(reason=reason,
                          predicate=is_prevent_create)


def skip_unless_prevent_create(reason='TOBIKO_PREVENT_CREATE is False'):
    return tobiko.skip_unless(reason=reason,
                              predicate=is_prevent_create)
