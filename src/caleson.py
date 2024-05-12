#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Caleson, JACK utilities
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
import sys
import shutil
from platform import architecture
import subprocess

from PyQt5.QtCore import (
    QFileSystemWatcher, Qt, QTimer,
    pyqtSlot, pyqtSignal, QSettings)
from PyQt5.QtGui import QIcon, QCloseEvent
from PyQt5.QtWidgets import (
    QApplication, QMainWindow,  QMessageBox)

# Imports (Custom Stuff)

from clickablelabel import ClickableLabel
import force_restart
import systray
import pulse2jack_tool

from alsa_audio_dialog import AlsaAudioDialog
from asio_tools import have_wine, getWineAsioKeyValue, smartHex
from pa_bridge_item import PaBridgeItem
from asoundrc_strs import (
    ASOUNDRC_ALOOP, ASOUNDRC_ALOOP_CHECK,
    ASOUNDRC_JACK, ASOUNDRC_PULSE)
from shared import (
    platform_, VERSION, HOME, getIcon,
    CustomMessageBox, setUpSignals)
from shared_caleson import (
    getProcList, GlobalSettings, AlsaFile,
    startAlsaAudioLoopBridge, wantJackStart)
from shared_canvasjack import (
    jacklib, gDBus, BUFFER_SIZE_LIST)
from shared_i18n import setup_i18n
from system_checks import calesonSystemChecks, initSystemChecks
import jacksettings

import ui_caleson

# Try Import DBus
try:
    import dbus
    from dbus.mainloop.pyqt5 import DBusQtMainLoop as DBusMainLoop
    haveDBus = True
except:
    try:
        # Try falling back to GMainLoop
        from dbus.mainloop.glib import DBusGMainLoop as DBusMainLoop
        haveDBus = True
    except:
        haveDBus = False

_logger = logging.getLogger(__name__)

# Check for PulseAudio
havePulseAudio = bool(shutil.which('pulseaudio'))


class IJackDbus(Enum):
    GRAPH_VERSION = 0
    CLIENT_ID = 1
    CLIENT_NAME = 2
    PORT_ID = 3
    PORT_NAME = 4
    PORT_FLAGS = 5
    PORT_TYPE = 6


global jackClientIdALSA
jackClientIdALSA = -1


def get_architecture():
    return architecture()[0]

def get_haiku_information():
    # TODO
    return ("Haiku OS", "Unknown")

def get_linux_information():
    # TODO informs about Librazik
    if os.path.exists("/etc/lsb-release"):
        distro = subprocess.getoutput(
            ". /etc/lsb-release && echo $DISTRIB_DESCRIPTION")
    elif os.path.exists("/etc/arch-release"):
        distro = "ArchLinux"
    else:
        distro = os.uname()[0]

    kernel = os.uname()[2]

    return (distro, kernel)

def get_mac_information():
    return ("Mac OS", "Unknown")

def get_windows_information():
    major = sys.getwindowsversion()[0]
    minor = sys.getwindowsversion()[1]
    servp = sys.getwindowsversion()[4]

    os = "Windows"
    version = servp

    if major == 4 and minor == 0:
        os = "Windows 95"
        version = "RTM"
    elif major == 4 and minor == 10:
        os = "Windows 98"
        version = "Second Edition"
    elif major == 5 and minor == 0:
        os = "Windows 2000"
    elif major == 5 and minor == 1:
        os = "Windows XP"
    elif major == 5 and minor == 2:
        os = "Windows Server 2003"
    elif major == 6 and minor == 0:
        os = "Windows Vista"
    elif major == 6 and minor == 1:
        os = "Windows 7"
    elif major == 6 and minor == 2:
        os = "Windows 8"

    return (os, version)

# ---------------------------------------------------------------------

def isAlsaAudioBridged():
    global jackClientIdALSA
    return bool(jackClientIdALSA != -1)


# Main Window
class CalesonMainW(QMainWindow):
    DBusJackServerStartedCallback = pyqtSignal()
    DBusJackServerStoppedCallback = pyqtSignal()
    DBusJackClientAppearedCallback = pyqtSignal(int, str)
    DBusJackClientDisappearedCallback = pyqtSignal(int)
    DBusA2JBridgeStartedCallback = pyqtSignal()
    DBusA2JBridgeStoppedCallback = pyqtSignal()

    SIGTERM = pyqtSignal()
    SIGUSR1 = pyqtSignal()
    SIGUSR2 = pyqtSignal()
    
    pulse_bridges_edited = pyqtSignal()

    def __init__(self, parent=None):
        QMainWindow.__init__(self, parent)
        self.ui = ui_caleson.Ui_CalesonMainW()
        self.ui.setupUi(self)

        self.settings = QSettings("Caleson", "Caleson")
        self.loadSettings(True)

        self.pix_apply = QIcon(getIcon("dialog-ok-apply", 16)).pixmap(16, 16)
        self.pix_cancel = QIcon(getIcon("dialog-cancel", 16)).pixmap(16, 16)
        self.pix_error = QIcon(getIcon("dialog-error", 16)).pixmap(16, 16)
        self.pix_warning = QIcon(getIcon("dialog-warning", 16)).pixmap(16, 16)

        self.m_lastAlsaIndexType = AlsaFile.INVALID

        if jacklib and not jacklib.JACK2:
            self.ui.b_jack_switchmaster.setEnabled(False)

        # -------------------------------------------------------------
        # Set-up GUI (System Information)
        info = platform_.get_info()
        self.ui.label_info_os.setText(info[0])
        self.ui.label_info_version.setText(info[1])
        self.ui.label_info_arch.setText(get_architecture())

        # Set-up GUI (System Status)

        self.m_availGovPath = \
            "/sys/devices/system/cpu/cpu0/cpufreq/scaling_available_governors"
        self.m_curGovPath = \
            "/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor"
        self.m_curGovPaths = list[str]()
        self.m_curGovCPUs = list[int]()

        try:
            fBus = dbus.SystemBus(mainloop=gDBus.loop)
            fProxy = fBus.get_object(
                "com.ubuntu.IndicatorCpufreqSelector",
                "/Selector",
                introspect=False)
            haveFreqSelector = True
        except:
            haveFreqSelector = False

        if (haveFreqSelector
                and os.path.exists(self.m_availGovPath)
                and os.path.exists(self.m_curGovPath)):
            self.m_govWatcher = QFileSystemWatcher(self)
            self.m_govWatcher.addPath(self.m_curGovPath)
            self.m_govWatcher.fileChanged.connect(
                self.slot_governorFileChanged)
            QTimer.singleShot(0, self.slot_governorFileChanged)

            availGovFd = open(self.m_availGovPath, "r")
            availGovRead = availGovFd.read().strip()
            availGovFd.close()

            self.m_availGovList = availGovRead.split(" ")
            for availGov in self.m_availGovList:
                self.ui.cb_cpufreq.addItem(availGov)

            for root, dirs, files in os.walk("/sys/devices/system/cpu/"):
                for dir_ in [dir_ for dir_ in dirs if dir_.startswith("cpu")]:
                    if not dir_.replace("cpu", "", 1).isdigit():
                        continue

                    cpuGovPath = os.path.join(
                        root, dir_, "cpufreq", "scaling_governor")

                    if os.path.exists(cpuGovPath):
                        self.m_curGovPaths.append(cpuGovPath)
                        self.m_curGovCPUs.append(
                            int(dir_.replace("cpu", "", 1)))

            self.ui.cb_cpufreq.setCurrentIndex(-1)

        else:
            self.m_govWatcher = None
            self.ui.cb_cpufreq.setEnabled(False)
            self.ui.label_cpufreq.setEnabled(False)

        # -------------------------------------------------------------
        # Set-up GUI (System Checks)

        for check in calesonSystemChecks:
            if check.get_id() == 'kernel':
                self.ui.labelUsedKernel.setText(check.result)
                if check.moreInfo:
                    self.ui.labelUsedKernel.setToolTip(check.moreInfo)
                widgetIcon = self.ui.labelUsedKernelIcon
                
            elif check.get_id() == 'audio_group':
                self.ui.labelUserInAudioGroup.setText(check.result)
                if check.moreInfo:
                    self.ui.labelUserInAudioGroup.setToolTip(check.moreInfo)
                widgetIcon = self.ui.labelUserInAudioGroupIcon

            if check.icon == check.ICON_ERROR:
                widgetIcon.setPixmap(self.pix_error)
            elif check.icon == check.ICON_WARN:
                widgetIcon.setPixmap(self.pix_warning)
            elif check.icon == check.ICON_OK:
                widgetIcon.setPixmap(self.pix_apply)
            else:
                widgetIcon.setPixmap(self.pix_cancel)

        # -------------------------------------------------------------
        # Set-up GUI (JACK Bridges)
        
        self.pulse_bridges_edited.connect(self.slot_PulseAudioBridgeSetEdited)
        self._pulse_check_timer = QTimer()
        self._pulse_check_timer.setInterval(500)
        self._pulse_check_timer.setSingleShot(True)
        self._pulse_check_timer.timeout.connect(
            self.slot_checkPulseAudioBridges)

        if not havePulseAudio:
            #self.toolBox_pulseaudio.setEnabled(False)
            self.ui.label_bridge_pulse.setText(self.tr("PulseAudio is not installed"))
        
        self._pulse_bridge_dicts = pulse2jack_tool.get_existing_modules_in_dicts()
        for bridge_dict in self._pulse_bridge_dicts:
            if bridge_dict['type'] == 'source':
                source_item = PaBridgeItem(self.ui.listWidgetPulseSources,
                                           self.pulse_bridges_edited, bridge_dict)
                self.ui.listWidgetPulseSources.addItem(source_item)
            else:
                sink_item = PaBridgeItem(self.ui.listWidgetPulseSinks,
                                         self.pulse_bridges_edited, bridge_dict)
                self.ui.listWidgetPulseSinks.addItem(sink_item)
        
        # Not available in cxfreeze builds
        if sys.argv[0].endswith("/caleson"):
            self.ui.cb_jack_autostart.setEnabled(False)

        # -------------------------------------------------------------
        # Set-up GUI (Tweaks)

        self.settings_changed_types = list[str]()
        self.ui.frame_tweaks_settings.setVisible(False)

        for i in range(self.ui.tw_tweaks.rowCount()):
            self.ui.tw_tweaks.item(i, 0).setTextAlignment(Qt.AlignLeft|Qt.AlignVCenter)
            self.ui.tw_tweaks.setRowHeight(i, 60)

        self.ui.tw_tweaks.setCurrentCell(0, 0)

        # -------------------------------------------------------------
        # Set-up GUI (Tweaks, WineASIO)

        if have_wine():
            ins = int(
                getWineAsioKeyValue("Number of inputs", "00000010"), 16)
            outs = int(
                getWineAsioKeyValue("Number of outputs", "00000010"), 16)
            hw = bool(int(
                getWineAsioKeyValue("Connect to hardware", "00000001"), 10))

            autostart = bool(int(
                getWineAsioKeyValue("Autostart server", "00000000"), 10))
            fixed_bsize = bool(int(
                getWineAsioKeyValue("Fixed buffersize", "00000001"), 10))
            prefer_bsize = int(
                getWineAsioKeyValue("Preferred buffersize", "00000400"), 16)

            for bsize in BUFFER_SIZE_LIST:
                self.ui.cb_wineasio_bsizes.addItem(str(bsize))
                if bsize == prefer_bsize:
                    self.ui.cb_wineasio_bsizes.setCurrentIndex(
                        self.ui.cb_wineasio_bsizes.count()-1)

            self.ui.sb_wineasio_ins.setValue(ins)
            self.ui.sb_wineasio_outs.setValue(outs)
            self.ui.cb_wineasio_hw.setChecked(hw)

            self.ui.cb_wineasio_autostart.setChecked(autostart)
            self.ui.cb_wineasio_fixed_bsize.setChecked(fixed_bsize)

        else:
            # No Wine
            self.ui.tw_tweaks.hideRow(2)

        # -------------------------------------------------------------
        # Set-up systray

        self.systray = systray.GlobalSysTray(self, "Caleson", "caleson")

        if haveDBus:
            self.systray.addAction("jack_start", self.tr("Start JACK"))
            self.systray.addAction("jack_stop", self.tr("Stop JACK"))
            self.systray.addAction("jack_configure", self.tr("Configure JACK"))
            self.systray.addSeparator("sep1")

            self.systray.addMenu("pulse", self.tr("PulseAudio Bridge"))
            self.systray.addMenuAction("pulse", "pulse_start", self.tr("Start"))
            self.systray.addMenuAction("pulse", "pulse_stop", self.tr("Stop"))
            self.systray.addMenu("a2j", self.tr("ALSA MIDI Bridge"))
            self.systray.addMenuAction("a2j", "a2j_start", self.tr("Start"))
            self.systray.addMenuAction("a2j", "a2j_stop", self.tr("Stop"))            

            self.systray.setActionIcon("jack_start", "media-playback-start")
            self.systray.setActionIcon("jack_stop", "media-playback-stop")
            self.systray.setActionIcon("jack_configure", "configure")
            self.systray.setActionIcon("pulse_start", "media-playback-start")
            self.systray.setActionIcon("pulse_stop", "media-playback-stop")
            self.systray.setActionIcon("a2j_start", "media-playback-start")
            self.systray.setActionIcon("a2j_stop", "media-playback-stop")

            self.systray.connect("jack_start", self.slot_JackServerStart)
            self.systray.connect("jack_stop", self.slot_JackServerStop)
            self.systray.connect("jack_configure", self.slot_JackServerConfigure)
            self.systray.connect("pulse_start", self.slot_PulseAudioBridgeStart)
            self.systray.connect("pulse_stop", self.slot_PulseAudioBridgeStop)
            self.systray.connect("a2j_start", self.slot_A2JBridgeStart)
            self.systray.connect("a2j_stop", self.slot_A2JBridgeStop)

        self.systray.addAction("app_logs", self.tr("Logs"))
        self.systray.setActionIcon("app_logs", "text-x-log")
        self.systray.addSeparator("sep2")

        self.systray.connect("app_logs", self.func_start_logs)

        self.systray.setToolTip("Caleson")
        self.systray.show()

        # -------------------------------------------------------------
        # Set-up connections

        self.ui.b_jack_start.clicked.connect(self.slot_JackServerStart)
        self.ui.b_jack_stop.clicked.connect(self.slot_JackServerStop)
        self.ui.b_jack_restart.clicked.connect(self.slot_JackServerForceRestart)
        self.ui.b_jack_configure.clicked.connect(self.slot_JackServerConfigure)
        self.ui.b_jack_switchmaster.clicked.connect(self.slot_JackServerSwitchMaster)

        self.ui.b_alsa_start.clicked.connect(self.slot_AlsaBridgeStart)
        self.ui.b_alsa_stop.clicked.connect(self.slot_AlsaBridgeStop)
        self.ui.cb_alsa_type.currentIndexChanged.connect(self.slot_AlsaBridgeChanged)
        self.ui.tb_alsa_options.clicked.connect(self.slot_AlsaAudioBridgeOptions)

        self.ui.b_a2j_start.clicked.connect(self.slot_A2JBridgeStart)
        self.ui.b_a2j_stop.clicked.connect(self.slot_A2JBridgeStop)
        self.ui.b_pulse_apply.clicked.connect(self.slot_PulseAudioBridgeApply)
        self.ui.b_pulse_start.clicked.connect(self.slot_PulseAudioBridgeStart)
        self.ui.b_pulse_stop.clicked.connect(self.slot_PulseAudioBridgeStop)
        self.ui.pushButtonAddPulseSource.clicked.connect(self.slot_PulseAudioBridgeAddSource)
        self.ui.pushButtonAddPulseSink.clicked.connect(self.slot_PulseAudioBridgeAddSink)

        for pic in (self.ui.pic_patchance,
                    self.ui.pic_raysession, 
                    self.ui.pic_logs,
                    self.ui.pic_render):
            pic.clicked.connect(self.func_start_tool_app)

        self.ui.b_tweaks_apply_now.clicked.connect(self.slot_tweaksApply)

        self.ui.sb_wineasio_ins.valueChanged.connect(
            self.slot_tweaksSettingsChanged_wineasio)
        self.ui.sb_wineasio_outs.valueChanged.connect(
            self.slot_tweaksSettingsChanged_wineasio)
        self.ui.cb_wineasio_hw.clicked.connect(
            self.slot_tweaksSettingsChanged_wineasio)
        self.ui.cb_wineasio_autostart.clicked.connect(
            self.slot_tweaksSettingsChanged_wineasio)
        self.ui.cb_wineasio_fixed_bsize.clicked.connect(
            self.slot_tweaksSettingsChanged_wineasio)
        self.ui.cb_wineasio_bsizes.currentIndexChanged[int].connect(
            self.slot_tweaksSettingsChanged_wineasio)

        # org.jackaudio.JackControl
        self.DBusJackServerStartedCallback.connect(
            self.slot_DBusJackServerStartedCallback)
        self.DBusJackServerStoppedCallback.connect(
            self.slot_DBusJackServerStoppedCallback)

        # org.jackaudio.JackPatchbay
        self.DBusJackClientAppearedCallback.connect(
            self.slot_DBusJackClientAppearedCallback)
        self.DBusJackClientDisappearedCallback.connect(
            self.slot_DBusJackClientDisappearedCallback)

        # org.gna.home.a2jmidid.control
        self.DBusA2JBridgeStartedCallback.connect(
            self.slot_DBusA2JBridgeStartedCallback)
        self.DBusA2JBridgeStoppedCallback.connect(
            self.slot_DBusA2JBridgeStoppedCallback)
        self.ui.cb_a2j_autoexport.stateChanged[int].connect(
            self.slot_A2JBridgeExportHW)
        self.ui.cb_a2j_unique_port_names.stateChanged[int].connect(
            self.slot_A2JBridgeUniquePortNames)

        # -------------------------------------------------------------

        self.m_last_dsp_load = None
        self.m_last_xruns = None
        self.m_last_buffer_size = None

        self.m_timer500 = None
        self.m_timer2000 = self.startTimer(2000)

        self.DBusReconnect()

        if haveDBus:
            gDBus.bus.add_signal_receiver(
                self.DBusSignalReceiver,
                destination_keyword='dest',
                path_keyword='path',
                member_keyword='member',
                interface_keyword='interface',
                sender_keyword='sender')

    def DBusReconnect(self):
        if haveDBus:
            try:
                gDBus.jack = gDBus.bus.get_object(
                    "org.jackaudio.service", "/org/jackaudio/Controller")
                gDBus.patchbay = dbus.Interface(
                    gDBus.jack, "org.jackaudio.JackPatchbay")
                jacksettings.initBus(gDBus.bus)
            except:
                gDBus.jack = None
                gDBus.patchbay = None

            try:
                gDBus.a2j = dbus.Interface(
                    gDBus.bus.get_object("org.gna.home.a2jmidid", "/"),
                    "org.gna.home.a2jmidid.control")
            except:
                gDBus.a2j = None

        if gDBus.jack:
            if gDBus.jack.IsStarted():
                # Check for pulseaudio in jack graph
                try:
                    version, groups, conns = gDBus.patchbay.GetGraph(0)
                except:
                    version, groups, conns = (list(), list(), list())

                for group_id, group_name, ports in groups:
                    if group_name == "alsa2jack":
                        global jackClientIdALSA
                        jackClientIdALSA = group_id

                self.jackStarted()

            else:
                self.jackStopped()
                self.ui.label_jack_realtime.setText(
                    self.tr("Yes") if jacksettings.isRealtime() else self.tr("No"))
        else:
            self.jackStopped()
            self.ui.label_jack_status.setText(self.tr("Unavailable"))
            self.ui.label_jack_status_ico.setPixmap(self.pix_error)
            self.ui.label_jack_realtime.setText(self.tr("Unknown"))
            self.ui.label_jack_realtime_ico.setPixmap(self.pix_error)
            self.ui.groupBox_jack.setEnabled(False)
            self.ui.groupBox_jack.setTitle(self.tr("-- jackdbus is not available --"))
            self.ui.b_jack_start.setEnabled(False)
            self.ui.b_jack_stop.setEnabled(False)
            self.ui.b_jack_restart.setEnabled(False)
            self.ui.b_jack_configure.setEnabled(False)
            self.ui.b_jack_switchmaster.setEnabled(False)

        if gDBus.a2j:
            try:
                started = gDBus.a2j.is_started()
            except:
                started = False

            if started:
                self.a2jStarted()
            else:
                self.a2jStopped()
        else:
            self.ui.cb_a2j_autostart.setChecked(False)
            self.ui.cb_a2j_autoexport.setChecked(False)
            self.ui.cb_a2j_unique_port_names.setChecked(False)
            self.ui.label_bridge_a2j.setText(self.tr("ALSA MIDI Bridge is not installed"))
            self.settings.setValue("A2J/AutoStart", False)

        self.updateSystrayTooltip()

    def DBusSignalReceiver(self, *args, **kwds):
        if (kwds['interface'] == "org.freedesktop.DBus"
                and kwds['path'] == "/org/freedesktop/DBus"
                and kwds['member'] == "NameOwnerChanged"):
            appInterface, appId, newId = args

            if not newId:
                # Something crashed
                if appInterface == "org.jackaudio.service":
                    QTimer.singleShot(0, self.slot_handleCrash_jack)
                elif appInterface == "org.gna.home.a2jmidid":
                    QTimer.singleShot(0, self.slot_handleCrash_a2j)

        elif kwds['interface'] == "org.jackaudio.JackControl":
            _logger.debug(
                f"org.jackaudio.JackControl {kwds['member']}" )

            if kwds['member'] == "ServerStarted":
                self.DBusJackServerStartedCallback.emit()
            elif kwds['member'] == "ServerStopped":
                self.DBusJackServerStoppedCallback.emit()

        elif kwds['interface'] == "org.jackaudio.JackPatchbay":
            if gDBus.patchbay and kwds['path'] == gDBus.patchbay.object_path:
                _logger.debug(
                    f"org.jackaudio.JackPatchbay, {kwds['member']}")

                if kwds['member'] == "ClientAppeared":
                    self.DBusJackClientAppearedCallback.emit(
                        args[IJackDbus.CLIENT_ID.value],
                        args[IJackDbus.CLIENT_NAME.value])
                elif kwds['member'] == "ClientDisappeared":
                    self.DBusJackClientDisappearedCallback.emit(
                        args[IJackDbus.CLIENT_ID.value])

        elif kwds['interface'] == "org.gna.home.a2jmidid.control":
            _logger.debug(
                f"org.gna.home.a2jmidid.control {kwds['member']}")

            if kwds['member'] == "bridge_started":
                self.DBusA2JBridgeStartedCallback.emit()
            elif kwds['member'] == "bridge_stopped":
                self.DBusA2JBridgeStoppedCallback.emit()

    def jackStarted(self):
        self.m_last_dsp_load = gDBus.jack.GetLoad()
        self.m_last_xruns = int(gDBus.jack.GetXruns())
        self.m_last_buffer_size = gDBus.jack.GetBufferSize()

        self.ui.b_jack_start.setEnabled(False)
        self.ui.b_jack_stop.setEnabled(True)
        self.ui.b_jack_switchmaster.setEnabled(True)
        self.systray.setActionEnabled("jack_start", False)
        self.systray.setActionEnabled("jack_stop", True)

        self.ui.label_jack_status.setText(self.tr("Started"))
        self.ui.label_jack_status_ico.setPixmap(self.pix_apply)

        if gDBus.jack.IsRealtime():
            self.ui.label_jack_realtime.setText(self.tr("Yes"))
            self.ui.label_jack_realtime_ico.setPixmap(self.pix_apply)
        else:
            self.ui.label_jack_realtime.setText(self.tr("No"))
            self.ui.label_jack_realtime_ico.setPixmap(self.pix_cancel)

        self.ui.label_jack_dsp.setText("%.2f%%" % self.m_last_dsp_load)
        self.ui.label_jack_xruns.setText(str(self.m_last_xruns))
        self.ui.label_jack_bfsize.setText(self.tr("%i samples") % self.m_last_buffer_size)
        self.ui.label_jack_srate.setText("%i Hz" % gDBus.jack.GetSampleRate())
        self.ui.label_jack_latency.setText("%.1f ms" % gDBus.jack.GetLatency())

        self.m_timer500 = self.startTimer(500)
        self.m_timer2000 = self.startTimer(2000)

        if gDBus.a2j and not gDBus.a2j.is_started():
            portsExported = bool(gDBus.a2j.get_hw_export())
            unique_port_names = not bool(gDBus.a2j.get_disable_port_uniqueness())
            if GlobalSettings.value("A2J/AutoStart", True, type=bool):
                if not portsExported and GlobalSettings.value("A2J/AutoExport", True, type=bool):
                    gDBus.a2j.set_hw_export(True)
                    # portsExported = True
                    
                if not unique_port_names:
                    gDBus.a2j.set_disable_port_uniqueness(True)

                gDBus.a2j.start()
            else:
                self.ui.b_a2j_start.setEnabled(True)
                self.systray.setActionEnabled("a2j_start", True)

        self.checkAlsaAudio()
        self.checkPulseAudio()

    def jackStopped(self):
        if self.m_timer500:
            self.killTimer(self.m_timer500)
            self.m_timer500 = None
        if self.m_timer2000:
            self.killTimer(self.m_timer2000)
            self.m_timer2000 = None

        self.m_last_dsp_load = None
        self.m_last_xruns = None
        self.m_last_buffer_size = None

        self.ui.b_jack_start.setEnabled(True)
        self.ui.b_jack_stop.setEnabled(False)
        self.ui.b_jack_switchmaster.setEnabled(False)

        if haveDBus:
            self.systray.setActionEnabled("jack_start", True)
            self.systray.setActionEnabled("jack_stop", False)

        self.ui.label_jack_status.setText(self.tr("Stopped"))
        self.ui.label_jack_status_ico.setPixmap(self.pix_cancel)

        self.ui.label_jack_dsp.setText("---")
        self.ui.label_jack_xruns.setText("---")
        self.ui.label_jack_bfsize.setText("---")
        self.ui.label_jack_srate.setText("---")
        self.ui.label_jack_latency.setText("---")

        if gDBus.a2j:
            self.ui.b_a2j_start.setEnabled(False)
            self.systray.setActionEnabled("a2j_start", False)

        global jackClientIdALSA
        jackClientIdALSA = -1

        if haveDBus:
            self.checkAlsaAudio()
            self.checkPulseAudio()

    def a2jStarted(self):
        self.ui.b_a2j_start.setEnabled(False)
        self.ui.b_a2j_stop.setEnabled(True)
        self.systray.setActionEnabled("a2j_start", False)
        self.systray.setActionEnabled("a2j_stop", True)
        if bool(gDBus.a2j.get_hw_export()):
            self.ui.label_bridge_a2j.setText(
                self.tr("ALSA MIDI Bridge is running, ports are exported"))
        else :
            self.ui.label_bridge_a2j.setText(
                self.tr("ALSA MIDI Bridge is running"))

    def a2jStopped(self):
        jackRunning = bool(gDBus.jack and gDBus.jack.IsStarted())
        self.ui.b_a2j_start.setEnabled(jackRunning)
        self.ui.b_a2j_stop.setEnabled(False)
        self.systray.setActionEnabled("a2j_start", jackRunning)
        self.systray.setActionEnabled("a2j_stop", False)
        self.ui.label_bridge_a2j.setText(self.tr("ALSA MIDI Bridge is stopped"))

    def checkAlsaAudio(self):
        asoundrcFile = os.path.join(HOME, ".asoundrc")

        if not os.path.exists(asoundrcFile):
            self.ui.b_alsa_start.setEnabled(False)
            self.ui.b_alsa_stop.setEnabled(False)
            self.ui.cb_alsa_type.setCurrentIndex(AlsaFile.NONE.value)
            self.ui.tb_alsa_options.setEnabled(False)
            self.ui.label_bridge_alsa.setText(self.tr("No bridge in use"))
            self.m_lastAlsaIndexType = AlsaFile.NULL
            return

        with open(asoundrcFile, "r") as asoundrcFd:
            asoundrcRead = asoundrcFd.read().strip()

        if asoundrcRead.startswith(ASOUNDRC_ALOOP_CHECK):
            if isAlsaAudioBridged():
                self.ui.b_alsa_start.setEnabled(False)
                self.ui.b_alsa_stop.setEnabled(True)
                self.ui.label_bridge_alsa.setText(
                    self.tr("Using Caleson snd-aloop daemon, started"))
            else:
                try:
                    jackRunning = bool(gDBus.jack and gDBus.jack.IsStarted())
                except:
                    jackRunning = False

                self.ui.b_alsa_start.setEnabled(jackRunning)
                self.ui.b_alsa_stop.setEnabled(False)
                self.ui.label_bridge_alsa.setText(
                    self.tr("Using Caleson snd-aloop daemon, stopped"))

            self.ui.cb_alsa_type.setCurrentIndex(AlsaFile.LOOP.value)
            self.ui.tb_alsa_options.setEnabled(True)

        elif asoundrcRead == ASOUNDRC_JACK:
            self.ui.b_alsa_start.setEnabled(False)
            self.ui.b_alsa_stop.setEnabled(False)
            self.ui.cb_alsa_type.setCurrentIndex(AlsaFile.JACK.value)
            self.ui.tb_alsa_options.setEnabled(False)
            self.ui.label_bridge_alsa.setText(
                self.tr("Using JACK plugin bridge (Always on)"))

        elif asoundrcRead == ASOUNDRC_PULSE:
            self.ui.b_alsa_start.setEnabled(False)
            self.ui.b_alsa_stop.setEnabled(False)
            self.ui.cb_alsa_type.setCurrentIndex(AlsaFile.PULSE.value)
            self.ui.tb_alsa_options.setEnabled(False)
            self.ui.label_bridge_alsa.setText(
                self.tr("Using PulseAudio plugin bridge (Always on)"))

        else:
            self.ui.b_alsa_start.setEnabled(False)
            self.ui.b_alsa_stop.setEnabled(False)
            self.ui.cb_alsa_type.addItem(self.tr("Custom"))
            self.ui.cb_alsa_type.setCurrentIndex(AlsaFile.MAX.value)
            self.ui.tb_alsa_options.setEnabled(True)
            self.ui.label_bridge_alsa.setText(
                self.tr("Using custom asoundrc, not managed by Caleson"))

        self.m_lastAlsaIndexType = AlsaFile(
            self.ui.cb_alsa_type.currentIndex())

    def checkPulseAudio(self):
        if not havePulseAudio:
            self.systray.setActionEnabled("pulse_start", False)
            self.systray.setActionEnabled("pulse_stop", False)
            return

        mess = ""

        if "pulseaudio" in getProcList():
            if self._pulse_bridge_dicts:
                self.ui.b_pulse_start.setEnabled(False)
                self.ui.b_pulse_stop.setEnabled(True)
                self.systray.setActionEnabled("pulse_start", False)
                self.systray.setActionEnabled("pulse_stop", True)
                mess = self.tr("PulseAudio is started and bridged to JACK")
            else:
                jackRunning = bool(gDBus.jack and gDBus.jack.IsStarted())
                self.ui.b_pulse_start.setEnabled(jackRunning)
                self.ui.b_pulse_stop.setEnabled(False)
                self.systray.setActionEnabled("pulse_start", jackRunning)
                self.systray.setActionEnabled("pulse_stop", False)
                if jackRunning:
                    mess = self.tr("PulseAudio is started but not bridged")
                else:
                    mess = self.tr("PulseAudio is started but JACK is stopped")
        else:
            jackRunning = bool(gDBus.jack and gDBus.jack.IsStarted())
            self.ui.b_pulse_start.setEnabled(jackRunning)
            self.ui.b_pulse_stop.setEnabled(False)
            self.systray.setActionEnabled("pulse_start", jackRunning)
            self.systray.setActionEnabled("pulse_stop", False)
            if jackRunning:
                mess = self.tr("PulseAudio is not started")
            else:
                mess = self.tr("PulseAudio is not started, nor is JACK")

        self.ui.label_bridge_pulse.setText(mess)

    def updateSystrayTooltip(self):
        systrayText = "Caleson\n"
        systrayText += "%s: %s\n" % (self.tr("JACK Status"), self.ui.label_jack_status.text())
        systrayText += "%s: %s\n" % (self.tr("Realtime"), self.ui.label_jack_realtime.text())
        systrayText += "%s: %s\n" % (self.tr("DSP Load"), self.ui.label_jack_dsp.text())
        systrayText += "%s: %s\n" % (self.tr("Xruns"), self.ui.label_jack_xruns.text())
        systrayText += "%s: %s\n" % (self.tr("Buffer Size"), self.ui.label_jack_bfsize.text())
        systrayText += "%s: %s\n" % (self.tr("Sample Rate"), self.ui.label_jack_srate.text())
        systrayText += "%s: %s" % (self.tr("Block Latency"), self.ui.label_jack_latency.text())

        self.systray.setToolTip(systrayText)

    @pyqtSlot()
    def func_start_tool_app(self):
        sender: ClickableLabel = self.sender()
        
        if sender is self.ui.pic_patchance:
            subprocess.Popen(['patchance'])
        elif sender is self.ui.pic_raysession:
            subprocess.Popen(['raysession'])
        elif sender is self.ui.pic_logs:
            subprocess.Popen(['caleson-logs'])
        elif sender is self.ui.pic_render:
            subprocess.Popen(['qjackcapture'])
        else:
            _logger.warning('unknown sender for starting a tool app')

    @pyqtSlot()
    def func_start_logs(self):
        subprocess.Popen(['caleson-logs'])

    @pyqtSlot()
    def func_start_render(self):
        subprocess.Popen(['qjackcapture'])

    def func_settings_changed(self, stype):
        if stype not in self.settings_changed_types:
            self.settings_changed_types.append(stype)
        self.ui.frame_tweaks_settings.setVisible(True)

    @pyqtSlot()
    def slot_DBusJackServerStartedCallback(self):
        self.jackStarted()

    @pyqtSlot()
    def slot_DBusJackServerStoppedCallback(self):
        self.jackStopped()

    @pyqtSlot(int, str)
    def slot_DBusJackClientAppearedCallback(self, group_id, group_name):
        if group_name == "alsa2jack":
            global jackClientIdALSA
            jackClientIdALSA = group_id
            self.checkAlsaAudio()

        self._pulse_check_timer.start()

    @pyqtSlot(int)
    def slot_DBusJackClientDisappearedCallback(self, group_id):
        global jackClientIdALSA
        if group_id == jackClientIdALSA:
            jackClientIdALSA = -1
            self.checkAlsaAudio()
        
        self._pulse_check_timer.start()

    @pyqtSlot()
    def slot_DBusA2JBridgeStartedCallback(self):
        self.a2jStarted()

    @pyqtSlot()
    def slot_DBusA2JBridgeStoppedCallback(self):
        self.a2jStopped()

    @pyqtSlot()
    def slot_checkPulseAudioBridges(self):
        self._pulse_bridge_dicts = pulse2jack_tool.get_existing_modules_in_dicts()
        self.ui.listWidgetPulseSources.clear()
        self.ui.listWidgetPulseSinks.clear()
        
        for b_dict in self._pulse_bridge_dicts:
            if b_dict['type'] == 'sink':
                sink_item = PaBridgeItem(
                    self.ui.listWidgetPulseSinks, self.pulse_bridges_edited, b_dict)
                self.ui.listWidgetPulseSinks.addItem(sink_item)
            else:
                source_item = PaBridgeItem(
                    self.ui.listWidgetPulseSources, self.pulse_bridges_edited, b_dict)
                self.ui.listWidgetPulseSources.addItem(source_item)
        
        self.ui.b_pulse_apply.setEnabled(False)
        self.checkPulseAudio()

    @pyqtSlot()
    def slot_JackServerStart(self):
        self.saveSettings()
        try:
            gDBus.jack.StartServer()
        except:
            QMessageBox.warning(
                self,
                self.tr("Warning"),
                self.tr("Failed to start JACK, please check the logs for more information."))

    @pyqtSlot()
    def slot_JackServerStop(self):
        if gDBus.a2j and bool(gDBus.a2j.is_started()):
            gDBus.a2j.stop()
        try:
            gDBus.jack.StopServer()
        except:
            QMessageBox.warning(
                self,
                self.tr("Warning"),
                self.tr("Failed to stop JACK, please check the logs for more information."))

    @pyqtSlot()
    def slot_JackServerForceRestart(self):
        if gDBus.jack.IsStarted():
            ask = CustomMessageBox(
                self, QMessageBox.Warning, self.tr("Warning"),
                self.tr("This will force kill all JACK applications!<br>Make sure to save your projects before continue."),
                self.tr("Are you sure you want to force the restart of JACK?"))

            if ask != QMessageBox.Yes:
                return

        if self.m_timer500:
            self.killTimer(self.m_timer500)
            self.m_timer500 = None
        
        if self.m_timer2000:
            self.killTimer(self.m_timer2000)
            self.m_timer2000 = None

        self.saveSettings()
        force_restart.ForceWaitDialog(self).exec_()

    @pyqtSlot()
    def slot_JackServerConfigure(self):
        jacksettingsW = jacksettings.JackSettingsW(self)
        jacksettingsW.exec_()
        del jacksettingsW

    @pyqtSlot()
    def slot_JackServerSwitchMaster(self):
        try:
            gDBus.jack.SwitchMaster()
        except:
            QMessageBox.warning(
                self,
                self.tr("Warning"),
                self.tr("Failed to switch JACK master, please check the logs for more information."))
            return

        self.jackStarted()

    @pyqtSlot()
    def slot_JackClearXruns(self):
        if gDBus.jack:
            gDBus.jack.ResetXruns()

    @pyqtSlot()
    def slot_AlsaBridgeStart(self):
        self.slot_AlsaBridgeStop()
        startAlsaAudioLoopBridge()

    @pyqtSlot()
    def slot_AlsaBridgeStop(self):
        checkFile = "/tmp/.caleson-aloop-daemon.x"
        if os.path.exists(checkFile):
            os.remove(checkFile)

    @pyqtSlot(int)
    def slot_AlsaBridgeChanged(self, index: int):
        try:
            alsa_index = AlsaFile(index)
        except:
            _logger.error(
                f"Caleson::AlsaBridgeChanged({index}) - invalid index")
            return
        
        if self.m_lastAlsaIndexType in (AlsaFile.INVALID,  alsa_index):
            return

        if self.m_lastAlsaIndexType is AlsaFile.MAX:
            ask = CustomMessageBox(
                self, 
                QMessageBox.Warning, self.tr("Warning"),
                self.tr(""
                    "You're using a custom ~/.asoundrc file not managed by Caleson.<br/>"
                    "By choosing to use a Caleson ALSA-Audio bridge, <b>the file will be replaced</b>."
                    ""),
                self.tr("Are you sure you want to do this?"))

            if ask == QMessageBox.Yes:
                self.ui.cb_alsa_type.blockSignals(True)
                self.ui.cb_alsa_type.removeItem(AlsaFile.MAX.value)
                self.ui.cb_alsa_type.setCurrentIndex(index)
                self.ui.cb_alsa_type.blockSignals(False)
            else:
                self.ui.cb_alsa_type.blockSignals(True)
                self.ui.cb_alsa_type.setCurrentIndex(AlsaFile.MAX.value)
                self.ui.cb_alsa_type.blockSignals(False)
                return

        asoundrcFile = os.path.join(HOME, ".asoundrc")

        if alsa_index is AlsaFile.NONE:
            os.remove(asoundrcFile)

        elif alsa_index is AlsaFile.LOOP:
            with open(asoundrcFile, "w") as asoundrcFd:                
                asoundrcFd.write(ASOUNDRC_ALOOP+"\n")

        elif alsa_index is AlsaFile.JACK:
            with open(asoundrcFile, "w") as asoundrcFd:
                asoundrcFd.write(ASOUNDRC_JACK+"\n")

        elif alsa_index is AlsaFile.PULSE:
            with open(asoundrcFile, "w") as asoundrcFd:
                asoundrcFd.write(ASOUNDRC_PULSE+"\n")

        self.checkAlsaAudio()

    @pyqtSlot()
    def slot_AlsaAudioBridgeOptions(self):
        AlsaAudioDialog(
            self,
            (self.ui.cb_alsa_type.currentIndex() != AlsaFile.LOOP.value)).exec_()

    @pyqtSlot()
    def slot_A2JBridgeStart(self):
        gDBus.a2j.start()

    @pyqtSlot()
    def slot_A2JBridgeStop(self):
        gDBus.a2j.stop()

    @pyqtSlot(int)
    def slot_A2JBridgeExportHW(self, state):
        a2jWasStarted = bool(gDBus.a2j.is_started())

        if a2jWasStarted:
            gDBus.a2j.stop()

        gDBus.a2j.set_hw_export(bool(state))

        if a2jWasStarted:
            gDBus.a2j.start()

    @pyqtSlot(int)
    def slot_A2JBridgeUniquePortNames(self, state: int):
        a2j_was_started = bool(gDBus.a2j.is_started())
        
        if a2j_was_started:
            gDBus.a2j.stop()
            
        gDBus.a2j.set_disable_port_uniqueness(not bool(state))
        
        if a2j_was_started:
            gDBus.a2j.start()

    @pyqtSlot()
    def slot_PulseAudioBridgeApply(self):
        bridge_dicts = []
        for i in range(self.ui.listWidgetPulseSources.count()):
            item = self.ui.listWidgetPulseSources.item(i)
            bridge_dicts.append(item.get_current_dict())
        for i in range(self.ui.listWidgetPulseSinks.count()):
            item = self.ui.listWidgetPulseSinks.item(i)
            bridge_dicts.append(item.get_current_dict())
        
        GlobalSettings.setValue('PulseAudio_bridges', bridge_dicts)
        
        pulse2jack_tool.replace_hotly(bridge_dicts)
        
    @pyqtSlot()
    def slot_PulseAudioBridgeStart(self):
        bridge_dicts = GlobalSettings.value('PulseAudio_bridges', type=list)
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
    
    @pyqtSlot()
    def slot_PulseAudioBridgeStop(self):
        os.system("pulseaudio -k")

    @pyqtSlot()
    def slot_PulseAudioBridgeSetEdited(self):
        self.ui.b_pulse_apply.setEnabled(True)

    @pyqtSlot()
    def slot_PulseAudioBridgeAddSource(self):
        bridge_name = "PulseAudio JACK Source"
        i = 2
        
        while True:
            for j in range(self.ui.listWidgetPulseSources.count()):
                item: PaBridgeItem = self.ui.listWidgetPulseSources.item(j)
                if item.get_current_dict()['name'] == bridge_name:
                    break
            else:
                break
            
            if bridge_name.endswith(')'):
                bridge_name = "%s%i)" % (bridge_name[:-2], i)
            else:
                bridge_name += ' (%i)' % i
            i += 1
        
        self.ui.listWidgetPulseSources.addItem(
            PaBridgeItem(
                self.ui.listWidgetPulseSources,
                self.pulse_bridges_edited,
                {"type": "source",
                 "name": bridge_name,
                 "channels": 2,
                 "connected": True}))

        self.pulse_bridges_edited.emit()
                
    @pyqtSlot()
    def slot_PulseAudioBridgeAddSink(self):
        bridge_name = "PulseAudio JACK Sink"
        i = 2
        
        while True:
            for j in range(self.ui.listWidgetPulseSinks.count()):
                item: PaBridgeItem = self.ui.listWidgetPulseSinks.item(j)
                if item.get_current_dict()['name'] == bridge_name:
                    break
            else:
                break
            
            if bridge_name.endswith(')'):
                bridge_name = "%s%i)" % (bridge_name[:-2], i)
            else:
                bridge_name += ' (%i)' % i
            i += 1
        
        self.ui.listWidgetPulseSinks.addItem(
            PaBridgeItem(
                self.ui.listWidgetPulseSinks,
                self.pulse_bridges_edited,
                {"type": "sink",
                 "name": bridge_name,
                 "channels": 2,
                 "connected": True}))
        
        self.pulse_bridges_edited.emit()

    @pyqtSlot()
    def slot_handleCrash_jack(self):
        self.DBusReconnect()

    @pyqtSlot()
    def slot_handleCrash_a2j(self):
        pass

    @pyqtSlot(str)
    def slot_changeGovernorMode(self, newMode):
        bus = dbus.SystemBus(mainloop=gDBus.loop)
        #proxy = bus.get_object("org.caleson.CpufreqSelector", "/Selector", introspect=False)
        proxy = bus.get_object(
            "com.ubuntu.IndicatorCpufreqSelector", "/Selector",
            introspect=False)
        proxy.SetGovernor(
            self.m_curGovCPUs, newMode,
            dbus_interface="com.ubuntu.IndicatorCpufreqSelector")

    @pyqtSlot()
    def slot_governorFileChanged(self):
        curGovFd = open(self.m_curGovPath, "r")
        curGovRead = curGovFd.read().strip()
        curGovFd.close()

        customTr = self.tr("Custom")

        if self.ui.cb_cpufreq.currentIndex() == -1:
            # First init
            self.ui.cb_cpufreq.currentIndexChanged[str].connect(
                self.slot_changeGovernorMode)

        self.ui.cb_cpufreq.blockSignals(True)

        if curGovRead in self.m_availGovList:
            self.ui.cb_cpufreq.setCurrentIndex(
                self.m_availGovList.index(curGovRead))

            if customTr in self.m_availGovList:
                self.m_availGovList.remove(customTr)
        else:
            if customTr not in self.m_availGovList:
                self.ui.cb_cpufreq.addItem(customTr)
                self.m_availGovList.append(customTr)

            self.ui.cb_cpufreq.setCurrentIndex(len(self.m_availGovList)-1)

        self.ui.cb_cpufreq.blockSignals(False)

    @pyqtSlot()
    def slot_tweaksApply(self):
        if "wineasio" in self.settings_changed_types:
            REGFILE = 'REGEDIT4\n'
            REGFILE += '\n'
            REGFILE += '[HKEY_CURRENT_USER\Software\Wine\WineASIO]\n'
            REGFILE += '"Autostart server"=dword:0000000%i\n' % int(
                1 if self.ui.cb_wineasio_autostart.isChecked() else 0)
            REGFILE += '"Connect to hardware"=dword:0000000%i\n' % int(
                1 if self.ui.cb_wineasio_hw.isChecked() else 0)
            REGFILE += '"Fixed buffersize"=dword:0000000%i\n' % int(
                1 if self.ui.cb_wineasio_fixed_bsize.isChecked() else 0)
            REGFILE += '"Number of inputs"=dword:000000%s\n' % smartHex(
                self.ui.sb_wineasio_ins.value(), 2)
            REGFILE += '"Number of outputs"=dword:000000%s\n' % smartHex(
                self.ui.sb_wineasio_outs.value(), 2)
            REGFILE += '"Preferred buffersize"=dword:0000%s\n' % smartHex(
                int(self.ui.cb_wineasio_bsizes.currentText()), 4)

            writeFile = open("/tmp/caleson-wineasio.reg", "w")
            writeFile.write(REGFILE)
            writeFile.close()

            os.system("regedit /tmp/caleson-wineasio.reg")

        self.settings_changed_types.clear()
        self.ui.frame_tweaks_settings.setVisible(False)

    @pyqtSlot()
    def slot_tweaksSettingsChanged_wineasio(self):
        self.func_settings_changed("wineasio")

    def saveSettings(self):
        self.settings.setValue("Geometry", self.saveGeometry())

        GlobalSettings.setValue(
            "JACK/AutoStart", self.ui.cb_jack_autostart.isChecked())
        GlobalSettings.setValue(
            "ALSA-Audio/BridgeIndexType", self.ui.cb_alsa_type.currentIndex())
        GlobalSettings.setValue(
            "A2J/AutoStart", self.ui.cb_a2j_autostart.isChecked())
        GlobalSettings.setValue(
            "A2J/AutoExport", self.ui.cb_a2j_autoexport.isChecked())
        GlobalSettings.setValue(
            "A2J/UniquePortNames", self.ui.cb_a2j_unique_port_names.isChecked())
        GlobalSettings.setValue(
            "Pulse2JACK/AutoStart",
            (havePulseAudio and self.ui.cb_pulse_autostart.isChecked()))

    def loadSettings(self, geometry):
        if geometry:
            self.restoreGeometry(self.settings.value("Geometry", b""))

        usingAlsaLoop = bool(
            GlobalSettings.value(
                "ALSA-Audio/BridgeIndexType", AlsaFile.NONE.value, type=int)
            == AlsaFile.LOOP.value)

        self.ui.cb_jack_autostart.setChecked(
            GlobalSettings.value("JACK/AutoStart", wantJackStart, type=bool))
        self.ui.cb_a2j_autostart.setChecked(
            GlobalSettings.value("A2J/AutoStart", True, type=bool))
        self.ui.cb_a2j_autoexport.setChecked(
            GlobalSettings.value("A2J/AutoExport", True, type=bool))
        self.ui.cb_a2j_unique_port_names.setChecked(
            GlobalSettings.value("A2J/UniquePortNames", True, type=bool))
        self.ui.cb_pulse_autostart.setChecked(
            GlobalSettings.value("Pulse2JACK/AutoStart", havePulseAudio
                                 and not usingAlsaLoop, type=bool))

    def timerEvent(self, event):
        if event.timerId() == self.m_timer500:
            if gDBus.jack and self.m_last_dsp_load != None:
                next_dsp_load = gDBus.jack.GetLoad()
                next_xruns = int(gDBus.jack.GetXruns())
                needUpdateTip = False

                if self.m_last_dsp_load != next_dsp_load:
                    self.m_last_dsp_load = next_dsp_load
                    self.ui.label_jack_dsp.setText("%.2f%%" % self.m_last_dsp_load)
                    needUpdateTip = True

                if self.m_last_xruns != next_xruns:
                    self.m_last_xruns = next_xruns
                    self.ui.label_jack_xruns.setText(str(self.m_last_xruns))
                    needUpdateTip = True

                if needUpdateTip:
                    self.updateSystrayTooltip()

        elif event.timerId() == self.m_timer2000:
            if gDBus.jack and self.m_last_buffer_size != None:
                next_buffer_size = gDBus.jack.GetBufferSize()

                if self.m_last_buffer_size != next_buffer_size:
                    self.m_last_buffer_size = next_buffer_size
                    self.ui.label_jack_bfsize.setText(
                        self.tr("%i samples") % self.m_last_buffer_size)
                    self.ui.label_jack_latency.setText(
                        "%.1f ms" % gDBus.jack.GetLatency())

            else:
                self.update()

        QMainWindow.timerEvent(self, event)

    def closeEvent(self, event: QCloseEvent):
        self.saveSettings()
        self.systray.handleQtCloseEvent(event)


#--------------- main ------------------
if __name__ == '__main__':
    # App initialization
    app = QApplication(sys.argv)
    app.setApplicationName("Caleson")
    app.setApplicationVersion(VERSION)
    app.setOrganizationName("Caleson")
    app.setWindowIcon(QIcon(":/scalable/caleson.svg"))
    setup_i18n()

    if haveDBus:
        gDBus.loop = DBusMainLoop(set_as_default=True)
        gDBus.bus = dbus.SessionBus(mainloop=gDBus.loop)

    initSystemChecks(platform_)

    # Show GUI
    gui = CalesonMainW()

    # Set-up custom signal handling
    setUpSignals(gui)

    if "--minimized" in app.arguments():
        gui.hide()
        gui.systray.setActionText("show", gui.tr("Restore"))
        app.setQuitOnLastWindowClosed(False)
    else:
        gui.show()

    # Exit properly
    sys.exit(gui.systray.exec_(app))
