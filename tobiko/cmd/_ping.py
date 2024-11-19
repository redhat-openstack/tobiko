# Copyright (c) 2024 Red Hat, Inc.
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

import sys

from cliff import command
from oslo_log import log as logging

from tobiko.shell import ping

LOG = logging.getLogger(__name__)


class TobikoPing(command.Command):

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument(
            'server',
            help='Address of the server to ping'
        )
        parser.add_argument(
            '--result-file',
            default='tobiko_ping_results',
            help='Name of the directory where ping log files are '
                 'stored.'
        )
        return parser

    def take_action(self, parsed_args):
        error_code = 0
        try:
            LOG.debug("Starting ping server: %s", parsed_args.server)
            ping.write_ping_to_file(ping_ip=parsed_args.server,
                                    output_dir=parsed_args.result_file)
            LOG.debug("Finished ping server: %s", parsed_args.server)
        except Exception as e:
            if hasattr(e, 'errno'):
                error_code = e.errno
            else:
                error_code = 1
            LOG.error("Failed to ping server '%s'. Error: %s",
                      parsed_args.server, e)
        if error_code:
            sys.exit(error_code)
