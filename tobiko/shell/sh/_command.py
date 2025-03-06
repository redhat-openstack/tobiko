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

import re
import shlex
import typing


ShellCommandType = typing.Union['ShellCommand', str, typing.Iterable]


class ShellCommand(tuple):

    def __repr__(self) -> str:
        return f"ShellCommand({str(self)!r})"

    def __str__(self) -> str:
        return join(self)

    def __add__(self, other: ShellCommandType) -> 'ShellCommand':
        return shell_command(tuple(self) + shell_command(other))

    def __contains__(self, item) -> bool:
        return item in str(self)

    def as_list(self):
        return str(self).split(" ")


def shell_command(command: ShellCommandType,
                  **shlex_params) -> ShellCommand:
    if isinstance(command, ShellCommand):
        return command
    elif isinstance(command, str):
        return split(command, **shlex_params)
    else:
        return ShellCommand(str(a) for a in command)


_find_unsafe = re.compile(r'[^\w@&%+=:,.;<>/\-()\[\]|*~]', re.ASCII).search

_is_quoted = re.compile(r'(^\'.*\'$)|(^".*"$)', re.ASCII).search


def quote(s: str):
    """Return a shell-escaped version of the string *s*."""
    if not s:
        return "''"

    if _is_quoted(s):
        return s

    if _find_unsafe(s) is None:
        return s

    # use single quotes, and put single quotes into double quotes
    # the string $'b is then quoted as '$'"'"'b'
    return "'" + s.replace("'", "'\"'\"'") + "'"


def join(sequence: typing.Iterable[str]) -> str:
    return ' '.join(quote(s)
                    for s in sequence)


def split(command: str, posix=True, **shlex_params) -> ShellCommand:
    lex = shlex.shlex(command, posix=posix, **shlex_params)
    lex.whitespace_split = True
    return ShellCommand(lex)
