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

from tobiko.shell.http_ping import _http_ping


http_ping = _http_ping.http_ping
get_log_dir = _http_ping.get_log_dir

check_http_ping_results = _http_ping.check_http_ping_results

start_http_ping_process = _http_ping.start_http_ping_process
stop_http_ping_process = _http_ping.stop_http_ping_process
http_ping_process_alive = _http_ping.http_ping_process_alive
