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
from __future__ import division

import re

from oslo_log import log
import netaddr

import tobiko


LOG = log.getLogger(__name__)


def parse_ping_statistics(output, begin_interval=None, end_interval=None):
    lines = output.split('\n')
    line_it = iter(lines)
    try:
        source, destination = parse_ping_header(line_it)
    except Exception as ex:
        LOG.debug('Error parsing ping output header: %s', ex)
        source = destination = None

    try:
        transmitted, received, errors = parse_ping_footer(line_it)
    except Exception as ex:
        LOG.debug('Error parsing ping output footer: %s', ex)
        transmitted = received = errors = 0

    return PingStatistics(source=source, destination=destination,
                          transmitted=transmitted, received=received,
                          undelivered=errors, end_interval=end_interval,
                          begin_interval=begin_interval)


def parse_ping_header(line_it):
    for line in line_it:
        if line.startswith('PING '):
            header = line
            break
    else:
        raise ValueError('Ping output header not found')

    header_fields = [f.strip() for f in header.split()]
    header_fields = [(f[:-1] if f.endswith(':') else f)
                     for f in header_fields]
    destination = header_fields[2]
    while destination and destination[0] == '(':
        destination = destination[1:]
    while destination and destination[-1] == ')':
        destination = destination[:-1]
    destination = netaddr.IPAddress(destination)

    field_it = iter(header_fields[3:])
    source = None

    for field in field_it:
        if field == 'from':
            source = next(field_it).strip()
            if source.endswith(':'):
                source = source[:-1]
            source = netaddr.IPAddress(source)
            break

    return source, destination


def parse_ping_footer(line_it):
    for line in line_it:
        if line.startswith('--- ') and line.endswith(' ping statistics ---'):
            # parse footer
            footer = next(line_it).strip()
            break
    else:
        raise ValueError('Ping output footer not found')

    transmitted = received = errors = 0
    for field in footer.split(','):
        try:
            if 'transmitted' in field:
                transmitted = extract_integer(field)
            elif 'received' in field:
                received = extract_integer(field)
            elif 'error' in field:
                errors = extract_integer(field)
        except Exception as ex:
            LOG.exception('Error parsing ping output footer: %s', ex)
    return transmitted, received, errors


MATCH_NUMBERS_RE = re.compile(r'\d+')


def extract_integer(field):
    match = MATCH_NUMBERS_RE.search(field)
    if match:
        return int(match.group())
    raise ValueError("Integer not found in {!r}".format(field))


class PingStatistics(object):
    """Ping command statistics

    """

    def __init__(self,
                 source=None,
                 destination=None,
                 transmitted: int = 0,
                 received: int = 0,
                 undelivered: int = 0,
                 begin_interval=None,
                 end_interval=None):
        self.source = source
        self.destination = destination
        self.transmitted = transmitted
        self.received = received
        self.undelivered = undelivered
        self.begin_interval = begin_interval
        self.end_interval = end_interval

    @property
    def unreceived(self) -> int:
        return max(0, self.transmitted - self.received)

    @property
    def delivered(self) -> int:
        return max(0, self.transmitted - self.undelivered)

    @property
    def loss(self) -> float:
        if self.transmitted > 0:
            return float(self.unreceived) / float(self.transmitted)
        else:
            return 0.

    def __bool__(self):
        return bool(self.received)

    def __add__(self, other):
        begin_interval = min(i for i in [self.begin_interval,
                                         other.begin_interval] if i)
        end_interval = max(i for i in [self.end_interval,
                                       other.end_interval] if i)
        return PingStatistics(
            source=self.source or other.source,
            destination=self.destination or other.destination,
            transmitted=self.transmitted + other.transmitted,
            received=self.received + other.received,
            undelivered=self.undelivered + other.undelivered,
            begin_interval=begin_interval,
            end_interval=end_interval)

    def __repr__(self):
        return "PingStatistics({!s})".format(
            ", ".join("{!s}={!r}".format(k, v)
                      for k, v in self.__dict__.items()))

    def assert_transmitted(self):
        if not self.transmitted:
            tobiko.fail(f"{self.transmitted} package(s) has been transmitted "
                        f"to {self.destination}")

    def assert_not_transmitted(self):
        if self.transmitted:
            tobiko.fail(f"{self.transmitted} package(s) has been "
                        f"transmitted to {self.destination}")

    def assert_replied(self):
        if not self.received:
            tobiko.fail(f"{self.received} reply package(s) has been "
                        f"received from {self.destination}")

    def assert_not_replied(self):
        if self.received:
            tobiko.fail(f"{self.received} reply package(s) has been received "
                        f"from {self.destination}")
