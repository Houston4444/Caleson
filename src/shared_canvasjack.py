#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Common/Shared code related to Canvas and JACK
# Copyright (C) 2010-2018 Filipe Coelho <falktx@falktx.com>
# Copyright (C) 2023-2024 Houston4444 <picotmathieu@gmail.com>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# For a full copy of the GNU General Public License see the COPYING file


# Imports (Custom Stuff)
import logging
from typing import TYPE_CHECKING

from shared import cString
from jacklib_helpers import jacklib

if TYPE_CHECKING:
    import dbus


_logger = logging.getLogger(__name__)


# Have JACK2 ?
if jacklib and jacklib.JACK2:
    _logger.debug(
        f"Using JACK2, version {cString(jacklib.get_version_string())}")


BUFFER_SIZE_LIST = (16, 32, 64, 128, 256, 512, 1024, 2048, 4096, 8192)
SAMPLE_RATE_LIST = (22050, 32000, 44100, 48000, 88200, 96000, 192000)


class DBusObject:
    loop = None
    bus: 'dbus.SessionBus' = None
    a2j: 'dbus.Interface' = None
    jack: 'dbus.Interface' = None
    patchbay: 'dbus.Interface' = None


class JackObject:
    client = None


gDBus = DBusObject()
gJack = JackObject()
