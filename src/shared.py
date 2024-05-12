#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Common/Shared code
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

# Imports (Global)

from enum import Enum
import logging
import os
import subprocess
import sys
from typing import TYPE_CHECKING, Optional, Union

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QMessageBox


if TYPE_CHECKING:
    from logs import LogsW
    from caleson import CalesonMainW


_logger = logging.getLogger(__name__)


class Platform(Enum):
    HAIKU = 0
    LINUX = 1
    MACOS = 2
    WINDOWS = 3
        
    @staticmethod
    def this() -> 'Platform':
        if sys.platform == 'darwin':
            return Platform.MACOS
        if 'haiku' in sys.platform:
            return Platform.HAIKU
        if 'linux' in sys.platform:
            return Platform.LINUX
        if sys.platform in ('win32', 'win64', 'cygwin'):
            return Platform.WINDOWS
    
    def get_info(self) -> tuple[str, str]:
        if self is Platform.HAIKU:
            return ("Haiku OS", "Unknown")
        
        if self is Platform.LINUX:
            if os.path.exists("/etc/lsb-release"):
                distro = subprocess.getoutput(
                    ". /etc/lsb-release && echo $DISTRIB_DESCRIPTION")
            elif os.path.exists("/etc/arch-release"):
                distro = "ArchLinux"
            else:
                distro = os.uname()[0]

            kernel = os.uname()[2]

            return (distro, kernel)
        
        if self is self.MACOS:
            return ("Mac OS", "Unknown")
        
        if self is self.WINDOWS:
            major = sys.getwindowsversion()[0]
            minor = sys.getwindowsversion()[1]
            servp = sys.getwindowsversion()[4]

            wos = "Windows"
            version = servp

            if major == 4 and minor == 0:
                wos = "Windows 95"
                version = "RTM"
            elif major == 4 and minor == 10:
                wos = "Windows 98"
                version = "Second Edition"
            elif major == 5 and minor == 0:
                wos = "Windows 2000"
            elif major == 5 and minor == 1:
                wos = "Windows XP"
            elif major == 5 and minor == 2:
                wos = "Windows Server 2003"
            elif major == 6 and minor == 0:
                wos = "Windows Vista"
            elif major == 6 and minor == 1:
                wos = "Windows 7"
            elif major == 6 and minor == 2:
                wos = "Windows 8"

            return (wos, version)    

platform_ = Platform.this()


# Try Import Signal
try:
    from signal import signal, SIGINT, SIGTERM, SIGUSR1, SIGUSR2
    haveSignal = True
except:
    haveSignal = False

# Safe exception hook, needed for PyQt5
def sys_excepthook(typ, value, tback):
    return sys.__excepthook__(typ, value, tback)

sys.excepthook = sys_excepthook

# Set Version
VERSION = "0.9.0"

# Global variables
global gGui
gGui: 'Optional[Union[CalesonMainW, LogsW]]' = None

# Set TMP
TMP = os.getenv("TMP")

if TMP is None:
    if platform_ is Platform.WINDOWS:
        _logger.warning("TMP variable not set")
    #     TMP = os.path.join(WINDIR, "temp")
    # else:
        TMP = "/tmp"

# Set HOME
HOME = os.getenv("HOME")
if HOME is None:
    HOME = os.path.expanduser("~")

    if platform_ is not Platform.WINDOWS:
        _logger.warning("HOME variable not set")

if not os.path.exists(HOME):
    _logger.warning("HOME does not exist")
    HOME = TMP

# Set PATH
PATH = os.getenv("PATH")

if PATH is None:
    _logger.warning("PATH variable not set")

    if platform_ is Platform.MACOS:
        PATH = ("/opt/local/bin", "/usr/local/bin", "/usr/bin", "/bin")
    elif platform_ is Platform.WINDOWS:
        PATH = (os.path.join(WINDIR, "system32"), WINDIR)
    else:
        PATH = ("/usr/local/bin", "/usr/bin", "/bin")

else:
    PATH = PATH.split(os.pathsep)

# Convert a ctypes c_char_p into a python string
def cString(value: Union[str, bytes]) -> str:
    if not value:
        return ""
    if isinstance(value, str):
        return value
    return value.decode("utf-8", errors="ignore")

# Get Icon from user theme, using our own as backup (Oxygen)
def getIcon(icon, size=16) -> QIcon:
    return QIcon.fromTheme(icon, QIcon(":/%ix%i/%s.png" % (size, size, icon)))

# Custom MessageBox
def CustomMessageBox(self_: 'CalesonMainW', icon: QIcon,
                     title: str, text: str, extraText="",
                     buttons=QMessageBox.Yes|QMessageBox.No,
                     defButton=QMessageBox.No) -> QMessageBox:
    msgBox = QMessageBox(self_)
    msgBox.setIcon(icon)
    msgBox.setWindowTitle(title)
    msgBox.setText(text)
    msgBox.setInformativeText(extraText)
    msgBox.setStandardButtons(buttons)
    msgBox.setDefaultButton(defButton)
    return msgBox.exec_()

# Signal handler
def setUpSignals(gui: 'Union[CalesonMainW, LogsW]'):
    global gGui

    if gGui is None:
        gGui = gui

    if not haveSignal:
        return

    signal(SIGINT,  signalHandler)
    signal(SIGTERM, signalHandler)
    signal(SIGUSR1, signalHandler)
    signal(SIGUSR2, signalHandler)

    gGui.SIGTERM.connect(closeWindowHandler)
    gGui.SIGUSR2.connect(showWindowHandler)

def signalHandler(sig, frame):
    global gGui

    if gGui is None:
        return

    if sig in (SIGINT, SIGTERM):
        gGui.SIGTERM.emit()
    elif sig == SIGUSR1:
        gGui.SIGUSR1.emit()
    elif sig == SIGUSR2:
        gGui.SIGUSR2.emit()

def closeWindowHandler():
    global gGui

    if gGui is None:
        return

    gGui.hide()
    gGui.close()
    QApplication.instance().quit()

    gGui = None

def showWindowHandler():
    global gGui

    if gGui is None:
        return

    if gGui.isMaximized():
        gGui.showMaximized()
    else:
        gGui.showNormal()

