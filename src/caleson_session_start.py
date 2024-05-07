#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Imports (Global)
import os
import sys
import time

import dbus
from PyQt5.QtCore import QCoreApplication

# Imports (Custom Stuff)
import pulse2jack_tool
from shared_caleson import (
    QSettings, stopAllAudioProcesses, HOME, wantJackStart, AlsaFile,
    startAlsaAudioLoopBridge)
from shared import VERSION


# Caleson Global Settings
GlobalSettings = QSettings("Caleson", "GlobalSettings")

# DBus
class dBus(object):
    __slots__ = [
      'bus',
      'a2j',
      'jack'
    ]
DBus = dBus()

def forceReset():
    # Kill all audio processes
    stopAllAudioProcesses()

    # Remove configs
    configFiles = (
        # Caleson GlobalSettings
        os.path.join(HOME, ".asoundrc"),
        # ALSA settings
        os.path.join(HOME, ".config", "Caleson", "GlobalSettings.conf"),
        # JACK2 settings
        os.path.join(HOME, ".config", "jack", "conf.xml"),
        # JACK1 settings
        os.path.join(HOME, ".config", "jack", "conf-jack1.xml")
    )

    for config in configFiles:
        if os.path.exists(config):
            os.remove(config)

# Start JACK, A2J and Pulse, according to user settings
def startSession(systemStarted, secondSystemStartAttempt) -> bool:
    # Check if JACK is set to auto-start
    if (systemStarted
            and not GlobalSettings.value(
                "JACK/AutoStart", wantJackStart, type=bool)):
        print("JACK is set to NOT auto-start on login")
        return True

    # Called via autostart desktop file
    if systemStarted and secondSystemStartAttempt:
        tmp_bus  = dbus.SessionBus()
        tmp_jack = tmp_bus.get_object(
            "org.jackaudio.service", "/org/jackaudio/Controller")
        started  = bool(tmp_jack.IsStarted())

        # Cleanup
        del tmp_bus, tmp_jack

        # If already started, do nothing
        if started:
            return True

    # Kill all audio processes first
    stopAllAudioProcesses()

    # Connect to DBus
    DBus.bus  = dbus.SessionBus()
    DBus.jack = DBus.bus.get_object(
        "org.jackaudio.service", "/org/jackaudio/Controller")
    
    try:
        DBus.a2j = dbus.Interface(
            DBus.bus.get_object("org.gna.home.a2jmidid", "/"),
            "org.gna.home.a2jmidid.control")
    except:
        DBus.a2j = None

    
    try:
        startJack()
    except dbus.exceptions.DBusException as e:
        sys.stderr.write(str(e) + '\n')
        sys.stderr.write('First attempt to start JACK failed, retry one time\n')
        # with some configs, it is possible that jack start failed this firt time
        # but perfectly works the second time
        # So, startJack failed, but we try one more time.
        startJack()

    if not bool(DBus.jack.IsStarted()):
        print("JACK Failed to Start")
        return False

    # Start bridges according to user settings

    # ALSA-Audio
    if (GlobalSettings.value(
                "ALSA-Audio/BridgeIndexType", AlsaFile.NONE.value, type=int)
            == AlsaFile.LOOP.value):
        startAlsaAudioLoopBridge()
        time.sleep(0.5)

    # ALSA-MIDI
    if (GlobalSettings.value("A2J/AutoStart", True, type=bool)
            and DBus.a2j and not bool(DBus.a2j.is_started())):
        a2jExportHW = GlobalSettings.value(
            "A2J/ExportHW", True, type=bool)
        a2j_unique_port_names = GlobalSettings.value(
            "A2J/UniquePortNames", True, type=bool)
        DBus.a2j.set_hw_export(a2jExportHW)
        DBus.a2j.set_disable_port_uniqueness(not a2j_unique_port_names)
        DBus.a2j.start()

    # PulseAudio
    if GlobalSettings.value("Pulse2JACK/AutoStart", True, type=bool):
        bridge_dicts = GlobalSettings.value("PulseAudio_bridges", type=list)
        if not bridge_dicts:
            bridge_dicts = [
                {"type": "source",
                "name": "PulseAudio JACK Source",
                "channels": 2,
                "connected": True},
                {"type": "sink",
                "name": "PulseAudio JACK Sink",
                "channels": 2,
                "connected": True}]
            
        pulse2jack_tool.replace_hotly(bridge_dicts)

    print("JACK Started Successfully")
    return True

def startJack():
    if not bool(DBus.jack.IsStarted()):
        DBus.jack.StartServer()

def printArguments():
    print("\t-s|--start  \tStart session")
    print("\t   --reset  \tForce-reset all JACK daemons and settings "
          "(disables auto-start at login)")
    print("")
    print("\t-h|--help   \tShow this help message")
    print("\t-v|--version\tShow version")

def printError(cmd):
    print("Invalid arguments")
    print("Run '%s -h' for help" % (cmd))

def printHelp(cmd):
    print("Usage: %s [cmd]" % (cmd))
    printArguments()

def printVersion():
    print("Caleson version %s" % (VERSION))
    print("Developed by falkTX and the rest of the KXStudio Team")


if __name__ == '__main__':
    # App initialization
    app = QCoreApplication(sys.argv)
    app.setApplicationName("Caleson")
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("Caleson")

    # Check arguments
    cmd = sys.argv[0]

    if len(app.arguments()) == 1:
        printHelp(cmd)
    elif len(app.arguments()) == 2:
        arg = app.arguments()[1]

        if arg == "--reset":
            forceReset()
        elif arg in ("--system-start", "--system-start-desktop"):
            sys.exit(0 if startSession(True, arg == "--system-start-desktop")
                     else 1)
        elif arg in ("-s", "--s", "-start", "--start"):
            sys.exit(0 if startSession(False, False) else 1)
        elif arg in ("-h", "--h", "-help", "--help"):
            printHelp(cmd)
        elif arg in ("-v", "--v", "-version", "--version"):
            printVersion()
        else:
            printError(cmd)
    else:
        printError(cmd)

    # Exit
    sys.exit(0)
