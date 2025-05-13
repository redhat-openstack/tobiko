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

from datetime import datetime
import os
import typing

import netaddr
import requests

from tobiko.shell import sh

TIMEOUT = 2  # seconds

RESULT_OK = "OK"
RESULT_FAILED = "FAILED"


def get_log_dir():
    log_dir = f"{sh.get_user_home_dir()}/tobiko_http_ping_results"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    return log_dir


def http_ping(
        server_ip: typing.Union[str, netaddr.IPAddress]) -> dict:
    headers = {"connection": "close"}
    result = {'time': str(datetime.now())}
    url = f"http://{server_ip}"
    try:
        response = requests.head(url, headers=headers, timeout=TIMEOUT)
        if (response.status_code >= requests.codes.ok and  # noqa; pylint: disable=no-member
                response.status_code < requests.codes.bad):  # noqa; pylint: disable=no-member
            result['response'] = RESULT_OK
        else:
            result['response'] = RESULT_FAILED
    except requests.exceptions.RequestException:
        result['response'] = RESULT_FAILED
    return result
