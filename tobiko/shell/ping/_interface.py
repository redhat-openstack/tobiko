# Copyright (c) 2019 Red Hat, Inc.
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


from oslo_log import log
from neutron_lib import constants

import tobiko
from tobiko.shell.ping import _exception
from tobiko.shell.ping import _parameters
from tobiko.shell import sh


LOG = log.getLogger(__name__)


def get_ping_command(parameters, ssh_client):
    interface = get_ping_interface(ssh_client=ssh_client)
    return interface.get_ping_command(parameters)


def get_ping_interface(ssh_client):
    manager = tobiko.setup_fixture(PingInterfaceManager)
    interface = manager.get_ping_interface(ssh_client=ssh_client)
    tobiko.check_valid_type(interface, PingInterface)
    return interface


def has_fragment_ping_option(ssh_client=None):
    interface = get_ping_interface(ssh_client=ssh_client)
    return interface.has_fragment_option


skip_if_missing_fragment_ping_option = tobiko.skip_unless(
    "requires (don't) fragment Ping option",
    has_fragment_ping_option)


class PingInterfaceManager(tobiko.SharedFixture):

    def __init__(self):
        super(PingInterfaceManager, self).__init__()
        self.client_interfaces = {}
        self.interfaces = []
        self.default_interface = PingInterface()

    def add_ping_interface(self, interface):
        LOG.debug('Register ping interface %r', interface)
        self.interfaces.append(interface)

    def get_ping_interface(self, ssh_client):
        try:
            return self.client_interfaces[ssh_client]
        except KeyError:
            pass

        LOG.debug('Looking for ping interface for SSH client %s', ssh_client)
        usage = get_ping_usage(ssh_client)
        interface = find_ping_interface(usage=usage,
                                        interfaces=self.interfaces)
        if not interface:
            LOG.error('Ping interface not found: using the default one')
            interface = self.default_interface
        LOG.debug('Assign Ping interface %r to SSH client %r',
                  interface, ssh_client)
        self.client_interfaces[ssh_client] = interface
        return interface


def get_ping_usage(ssh_client):
    result = sh.execute('ping --help', expect_exit_status=None,
                        ssh_client=ssh_client)
    usage = ((result.stdout and str(result.stdout)) or
             (result.stderr and str(result.stderr)) or "").strip()
    if result.exit_status != 0 and 'command not found' in usage.lower():
        raise tobiko.SkipException(
            'ping command not installed on this instance')
    if usage:
        LOG.debug('Got ping usage text')
    else:
        raise ValueError("Unable to get usage message from ping command:\n"
                         "%s" % result.details)
    return usage


def find_ping_interface(usage, interfaces):
    if usage:
        for interface in interfaces:
            if interface.match_ping_usage(usage):
                return interface

    LOG.warning("No such ping interface class from usage message:\n"
                "%r", usage)
    return None


def ping_interface(interface_class):
    assert issubclass(interface_class, PingInterface)
    manager = tobiko.setup_fixture(PingInterfaceManager)
    manager.add_ping_interface(interface=interface_class())
    return interface_class


class PingInterface(object):

    ping_usage = None

    def match_ping_usage(self, usage):
        # pylint: disable=unused-argument
        return False

    def get_ping_command(self, parameters):
        host = parameters.host
        if not host:
            raise ValueError(f"Invalid destination host: '{host}'")

        command = sh.shell_command([self.get_ping_executable(parameters)] +
                                   self.get_ping_options(parameters) +
                                   [host])
        LOG.debug('Got ping command from interface %r for host %r: %r',
                  self, host, command)
        return command

    def get_ping_executable(self, parameters):
        ip_version = _parameters.get_ping_ip_version(parameters)
        if ip_version == constants.IP_VERSION_6:
            return 'ping6'
        else:
            return 'ping'

    def get_ping_options(self, parameters):
        options = []

        ip_version = _parameters.get_ping_ip_version(parameters)
        if ip_version == constants.IP_VERSION_4:
            options += self.get_ipv4_option()
        elif ip_version == constants.IP_VERSION_6:
            options += self.get_ipv6_option()
        elif ip_version is not None:
            message = 'Invalid IP version: {!r}'.format(ip_version)
            raise ValueError(message)

        interface = parameters.source
        if interface:
            options += self.get_interface_option(interface)

        deadline = parameters.deadline
        if deadline > 0:
            options += self.get_deadline_option(parameters)

        count = parameters.count
        if count > 0:
            options += self.get_count_option(count)

        size = _parameters.get_ping_payload_size(parameters)
        if size:
            options += self.get_size_option(size)

        interval = parameters.interval
        if interval > 1:
            if self.has_interval_option:
                options += self.get_interval_option(interval)
            else:
                LOG.warning(f'Interval option with value {interval} ignored '
                            f'because not supported by ping interface {self}')

        fragment = parameters.fragmentation
        if fragment is not None:
            options += self.get_fragment_option(fragment=fragment)

        return options

    def get_ipv4_option(self):
        return []

    def get_ipv6_option(self):
        return []

    def get_interface_option(self, interface):
        return ['-I', interface]

    def get_deadline_option(self, parameters):
        return ['-w', parameters.deadline,
                '-W', parameters.deadline]

    def get_count_option(self, count):
        return ['-c', int(count)]

    def get_size_option(self, size):
        return ['-s', int(size)]

    has_interval_option = False

    def get_interval_option(self, interval):
        details = ("{!r} ping implementation doesn't support "
                   "'interval={!r}' option").format(self, interval)
        raise _exception.UnsupportedPingOption(details=details)

    has_fragment_option = False

    def get_fragment_option(self, fragment):
        details = ("{!r} ping implementation doesn't support "
                   "'fragment={!r}' option").format(self, fragment)
        raise _exception.UnsupportedPingOption(details=details)


class IpVersionPingInterface(PingInterface):

    def get_ping_executable(self, parameters):
        # pylint: disable=unused-argument
        return 'ping'

    def get_ipv4_option(self):
        return ['-4']

    def get_ipv6_option(self):
        return ['-6']


IPUTILS_PING_USAGE = """
ping: invalid option -- '-'
Usage: ping [-aAbBdDfhLnOqrRUvV] [-c count] [-i interval] [-I interface]
            [-m mark] [-M pmtudisc_option] [-l preload] [-p pattern] [-Q tos]
            [-s packetsize] [-S sndbuf] [-t ttl] [-T timestamp_option]
            [-w deadline] [-W timeout] [hop1 ...] destination
""".strip()


@ping_interface
class IpUtilsPingInterface(PingInterface):

    def match_ping_usage(self, usage):
        return usage.startswith(IPUTILS_PING_USAGE)

    has_interval_option = True

    def get_interval_option(self, interval):
        return ['-i', int(interval)]

    has_fragment_option = True

    def get_fragment_option(self, fragment):
        if fragment:
            return ['-M', 'dont']
        else:
            return ['-M', 'do']


IP_VERSION_IPUTILS_PING_USAGE = """
ping: invalid option -- '-'
Usage: ping [-aAbBdDfhLnOqrRUvV64] [-c count] [-i interval] [-I interface]
            [-m mark] [-M pmtudisc_option] [-l preload] [-p pattern] [-Q tos]
            [-s packetsize] [-S sndbuf] [-t ttl] [-T timestamp_option]
            [-w deadline] [-W timeout] [hop1 ...] destination
Usage: ping -6 [-aAbBdDfhLnOqrRUvV] [-c count] [-i interval] [-I interface]
             [-l preload] [-m mark] [-M pmtudisc_option]
             [-N nodeinfo_option] [-p pattern] [-Q tclass] [-s packetsize]
             [-S sndbuf] [-t ttl] [-T timestamp_option] [-w deadline]
             [-W timeout] destination
""".strip()


@ping_interface
class IpUtilsIpVersionPingInterface(IpUtilsPingInterface,
                                    IpVersionPingInterface):

    def match_ping_usage(self, usage):
        return usage.startswith(IP_VERSION_IPUTILS_PING_USAGE)


BUSYBOX_PING_USAGE = """
ping: unrecognized option `--usage'
BusyBox v1.23.2 (2017-11-20 02:37:12 UTC) multi-call binary.

Usage: ping [OPTIONS] HOST

Send ICMP ECHO_REQUEST packets to network hosts

        -4,-6          Force IP or IPv6 name resolution
        -c CNT         Send only CNT pings
        -s SIZE        Send SIZE data bytes in packets (default:56)
        -t TTL         Set TTL
        -I IFACE/IP    Use interface or IP address as source
        -W SEC         Seconds to wait for the first response (default:10)
                       (after all -c CNT packets are sent)
        -w SEC         Seconds until ping exits (default:infinite)
                       (can exit earlier with -c CNT)
        -q             Quiet, only display output at start
                       and when finished
        -p             Pattern to use for payload
""".strip()


@ping_interface
class BusyBoxPingInterface(IpVersionPingInterface):

    def match_ping_usage(self, usage):
        return usage.startswith("BusyBox")


INET_TOOLS_PING_USAGE = """
Usage: ping [OPTION...] HOST ...
Send ICMP ECHO_REQUEST packets to network hosts.

 Options controlling ICMP request types:
      --address              send ICMP_ADDRESS packets (root only)
      --echo                 send ICMP_ECHO packets (default)
      --mask                 same as --address
      --timestamp            send ICMP_TIMESTAMP packets
  -t, --type=TYPE            send TYPE packets

 Options valid for all request types:

  -c, --count=NUMBER         stop after sending NUMBER packets
  -d, --debug                set the SO_DEBUG option
  -i, --interval=NUMBER      wait NUMBER seconds between sending each packet
  -n, --numeric              do not resolve host addresses
  -r, --ignore-routing       send directly to a host on an attached network
      --ttl=N                specify N as time-to-live
  -T, --tos=NUM              set type of service (TOS) to NUM
  -v, --verbose              verbose output
  -w, --timeout=N            stop after N seconds
  -W, --linger=N             number of seconds to wait for response

 Options valid for --echo requests:

  -f, --flood                flood ping (root only)
      --ip-timestamp=FLAG    IP timestamp of type FLAG, which is one of
                             "tsonly" and "tsaddr"
  -l, --preload=NUMBER       send NUMBER packets as fast as possible before
                             falling into normal mode of behavior (root only)
  -p, --pattern=PATTERN      fill ICMP packet with given pattern (hex)
  -q, --quiet                quiet output
  -R, --route                record route
  -s, --size=NUMBER          send NUMBER data octets

  -?, --help                 give this help list
      --usage                give a short usage message
  -V, --version              print program version
""".strip()


@ping_interface
class InetToolsPingInterface(PingInterface):

    def match_ping_usage(self, usage):
        return usage.startswith(INET_TOOLS_PING_USAGE)

    def get_deadline_option(self, parameters):
        ip_version = _parameters.get_ping_ip_version(parameters)
        if ip_version == constants.IP_VERSION_6:
            return ['-w', parameters.deadline]
        else:
            return ['-w', parameters.deadline,
                    '-W', parameters.deadline]


@ping_interface
class BsdPingInterface(PingInterface):

    def match_ping_usage(self, usage):
        return usage.startswith(BSD_PING_USAGE)

    has_fragment_option = False

    def get_deadline_option(self, parameters):
        return ['-t', parameters.deadline]


BSD_PING_USAGE = """
ping: unrecognized option `--help'
usage: ping [-AaDdfnoQqRrv] [-c count] [-G sweepmaxsize]
            [-g sweepminsize] [-h sweepincrsize] [-i wait]
            [-l preload] [-M mask | time] [-m ttl] [-p pattern]
            [-S src_addr] [-s packetsize] [-t timeout][-W waittime]
            [-z tos] host
       ping [-AaDdfLnoQqRrv] [-c count] [-I iface] [-i wait]
            [-l preload] [-M mask | time] [-m ttl] [-p pattern] [-S src_addr]
            [-s packetsize] [-T ttl] [-t timeout] [-W waittime]
            [-z tos] mcast-group
""".strip()
