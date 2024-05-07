#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Common/Shared code for Caleson
# Copyright (C) 2012-2018 Filipe Coelho <falktx@falktx.com>
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

# Imports (Global)

from enum import Enum
import os
import time

from PyQt5.QtCore import QProcess, QSettings

# Imports (Custom Stuff)

from shared import (HOME, HAIKU, LINUX, MACOS)


def get_default_path(plugin_format: str) -> list:
    return ':'.join(['%s/.%s' % (HOME, plugin_format),
                     '/usr/local/lib/%s' % plugin_format,
                     '/usr/lib/%s' % plugin_format])


class AlsaFile(Enum):
    INVALID = -2
    NULL = -1
    NONE = 0
    LOOP = 1
    JACK = 2
    PULSE = 3
    MAX = 4


GlobalSettings = QSettings("Caleson", "GlobalSettings")

# KXStudio Check
wantJackStart = os.path.exists(
    "/usr/share/kxstudio/config/config/Caleson/GlobalSettings.conf")

# Get Process list
def getProcList():
    retProcs = []

    if HAIKU or LINUX or MACOS:
        process = QProcess()
        process.start("ps", ["-u", str(os.getuid())])
        process.waitForFinished()

        processDump = process.readAllStandardOutput().split("\n")

        for i in range(len(processDump)):
            if (i == 0):
                continue

            dumpTest = str(
                processDump[i], encoding="utf-8").rsplit(":", 1)[-1].split(" ")
            if len(dumpTest) > 1 and dumpTest[1]:
                retProcs.append(dumpTest[1])

    else:
        print("getProcList() - Not supported in this system")

    return retProcs

# Start ALSA-Audio Bridge, reading its settings
def startAlsaAudioLoopBridge():
    channels = GlobalSettings.value(
        "ALSA-Audio/BridgeChannels", 2, type=int)
    useZita = bool(
        GlobalSettings.value(
            "ALSA-Audio/BridgeTool", "alsa_in", type=str)
        == "zita")

    os.system(
        "caleson-aloop-daemon --channels=%i %s &" % (
            channels, "--zita" if useZita else ""))

# Stop all audio processes, used for force-restart
def waitProcsEnd(procs, tries):
    for x in range(tries):
        procsList = getProcList()
        for proc in procs:
            if proc in procsList:
                break
            else:
                time.sleep(0.1)
        else:
            break

# Cleanly close the jack dbus service
def tryCloseJackDBus() -> bool:
    try:
        import dbus
        bus = dbus.SessionBus()
        jack = bus.get_object(
            "org.jackaudio.service", "/org/jackaudio/Controller")
        jack.Exit()
    except:
        print("tryCloseJackDBus() failed")
        return False
    
    return True

# Stop all audio processes, used for force-restart
def stopAllAudioProcesses(tryCloseJack = True):
    if tryCloseJack:
        tryCloseJackDBus()

    if not (HAIKU or LINUX or MACOS):
        print("stopAllAudioProcesses() - Not supported in this system")
        return

    process = QProcess()

    # Tell pulse2jack script to create files, prevents pulseaudio respawn
    process.start("caleson-pulse2jack", ["--dummy"])
    process.waitForFinished()

    procsTerm = ["a2j", "a2jmidid", "artsd", "jackd",
                 "jackdmp", "knotify4", "jmcore"]
    procsKill = ["jackdbus", "pulseaudio"]
    tries = 20

    process.start("killall", procsTerm)
    process.waitForFinished()
    waitProcsEnd(procsTerm, tries)

    process.start("killall", ["-KILL"] + procsKill)
    process.waitForFinished()
    waitProcsEnd(procsKill, tries)
