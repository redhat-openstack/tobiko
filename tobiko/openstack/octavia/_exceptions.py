# Copyright (c) 2021 Red Hat
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

from octaviaclient.api import exceptions

import tobiko


class RequestException(tobiko.TobikoException):
    message = ("Error while sending request to server "
               "(command was '{command}'): {error}")


class TimeoutException(tobiko.TobikoException):
    message = "Timeout exception: {reason}"


OctaviaClientException = exceptions.OctaviaClientException


class RoundRobinException(tobiko.TobikoException):
    message = "Round robin exception: {reason}"


class TrafficTimeoutError(tobiko.TobikoException):
    message = "Traffic timeout error: {reason}"


class AmphoraMgmtPortNotFound(tobiko.TobikoException):
    message = "Amphora's network management port was not found: {reason}"
