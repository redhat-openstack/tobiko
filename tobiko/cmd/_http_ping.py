# Copyright (c) 2025 Red Hat, Inc.
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

import time

from cliff import command
from oslo_log import log as logging
from oslo_serialization import jsonutils

from tobiko.shell import http_ping


LOG = logging.getLogger(__name__)


class TobikoHttpPing(command.Command):

    def get_parser(self, prog_name):
        parser = super().get_parser(prog_name)
        parser.add_argument(
            'server_ip',
            help='IP address of the server to send requests to'
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=5,
            help='Interval of the HTTP requests.'
        )
        return parser

    def take_action(self, parsed_args):
        try:
            LOG.debug("Starting sending HTTP requests to the server: %s",
                      parsed_args.server_ip)
            output_filename = f'http_ping_{parsed_args.server_ip}.log'
            result_file_path = \
                f"{http_ping.get_log_dir()}/{output_filename}"
            while True:
                with open(result_file_path, "a") as result_file:
                    iteration_start_time = time.time()
                    ping_result = http_ping.http_ping(parsed_args.server_ip)
                    result_file.write(jsonutils.dumps(ping_result) + "\n")
                    LOG.info("%s response from %s %s",
                             ping_result['time'], parsed_args.server_ip,
                             ping_result['response'])
                    elapsed = time.time() - iteration_start_time
                    if elapsed < parsed_args.interval:
                        time.sleep(parsed_args.interval - elapsed)
        except Exception as e:
            LOG.error("Failed to send http request to the server '%s'. "
                      "Error: %s", parsed_args.server_ip, e)
