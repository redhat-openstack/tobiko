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

from tobiko.shell.custom_script import _constants
from tobiko.shell.custom_script import _custom_script


RESULT_OK = _constants.RESULT_OK
RESULT_FAILED = _constants.RESULT_FAILED
LOG_TIME_FORMAT = _constants.LOG_TIME_FORMAT
LOG_RESULT_FORMAT = _constants.LOG_RESULT_FORMAT

ensure_script_is_on_server = _custom_script.ensure_script_is_on_server
get_log_dir = _custom_script.get_log_dir
get_log_files = _custom_script.get_log_files
copy_log_file = _custom_script.copy_log_file
get_process_pid = _custom_script.get_process_pid
get_process_pids = _custom_script.get_process_pids
check_results = _custom_script.check_results

start_script = _custom_script.start_script
stop_script = _custom_script.stop_script
