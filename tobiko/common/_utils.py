# Copyright 2020 Red Hat
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

from collections import abc


def get_short_hostname(hostname):
    return hostname.lower().split('.', 1)[0]


def is_collection(variable):
    """Checks if a variable is iterable, excluding string types."""
    if isinstance(variable, (str, bytes, bytearray)):
        return False
    return isinstance(variable, abc.Iterable)
