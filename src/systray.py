#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# KDE, App-Indicator or Qt Systray
# Copyright (C) 2011-2018 Filipe Coelho <falktx@falktx.com>
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

import logging
from typing import TYPE_CHECKING, Callable, Optional
from dataclasses import dataclass

from PyQt5.QtCore import QTimer
from PyQt5.QtGui import QIcon, QCloseEvent
from PyQt5.QtWidgets import (
    QApplication, QAction, QMainWindow, QMenu, QSystemTrayIcon)


if TYPE_CHECKING:
    from caleson import CalesonMainW


_logger = logging.getLogger(__name__)


# Get Icon from user theme, using our own as backup (Oxygen)
def getIcon(icon, size=16):
    return QIcon.fromTheme(icon, QIcon(":/%ix%i/%s.png" % (size, size, icon)))


@dataclass()
class ActData:
    name_id: str
    widget: QAction
    parent_menu_id: Optional[str]
    func: Optional[Callable]


@dataclass()
class SepData:
    name_id: str
    widget: QAction
    parent_menu_id: Optional[str]
    

@dataclass()
class MenuData:
    name_id: str
    widget: QMenu
    parent_menu_id: int


class GlobalSysTray:
    def __init__(self, parent: 'CalesonMainW', name: str, icon: str):
        self._app: Optional[QApplication] = None
        self._parent = parent
        self._gtk_running = False
        self._quit_added = False

        self.acts = list[ActData]()
        self.seps = list[SepData]()
        self.menus = list[MenuData]()

        self.menu = QMenu(parent)
        self.tray = QSystemTrayIcon(getIcon(icon))
        self.tray.setContextMenu(self.menu)
        self.tray.setParent(parent)
        self.tray.activated.connect(self.qt_systray_clicked)

    def addAction(self, act_name_id: str, act_name_string: str,
                  is_check=False):
        act_widget = QAction(act_name_string, self.menu)
        act_widget.setCheckable(is_check)
        self.menu.addAction(act_widget)

        self.acts.append(
            ActData(act_name_id, act_widget, None, None))

    def addSeparator(self, sep_name_id: str):
        sep_widget = self.menu.addSeparator()
        self.seps.append(SepData(sep_name_id, sep_widget, None))

    def addMenu(self, menu_name_id, menu_name_string):
        menu_widget = QMenu(menu_name_string, self.menu)
        self.menu.addMenu(menu_widget)
        self.menus.append(MenuData(menu_name_id, menu_widget, None))

    def addMenuAction(self, menu_name_id, act_name_id,
                      act_name_string, is_check=False):
        i = self.get_menu_index(menu_name_id)
        if i < 0: return

        menu_widget = self.menus[i].widget

        act_widget = QAction(act_name_string, menu_widget)
        act_widget.setCheckable(is_check)
        menu_widget.addAction(act_widget)

        self.acts.append(ActData(act_name_id, act_widget, menu_name_id, None))

    def addMenuSeparator(self, menu_name_id, sep_name_id):
        i = self.get_menu_index(menu_name_id)
        if i < 0: return

        menu_widget = self.menus[i].widget
        sep_widget = menu_widget.addSeparator()

        self.seps.append(SepData(sep_name_id, sep_widget, menu_name_id))

    # ---------------------------------------------------------------

    def connect(self, act_name_id, act_func):
        i = self.get_act_index(act_name_id)
        if i < 0: return

        act_widget = self.acts[i].widget
        act_widget.triggered.connect(act_func)

        self.acts[i].func = act_func

    # ---------------------------------------------------------------

    def setActionEnabled(self, act_name_id, yesno):
        i = self.get_act_index(act_name_id)
        if i < 0: return

        act_widget = self.acts[i].widget
        act_widget.setEnabled(yesno)

    def setActionIcon(self, act_name_id, icon):
        i = self.get_act_index(act_name_id)
        if i < 0: return

        act_widget = self.acts[i].widget
        act_widget.setIcon(getIcon(icon))

    def setActionText(self, act_name_id, text):
        i = self.get_act_index(act_name_id)
        if i < 0: return

        act_widget = self.acts[i].widget
        act_widget.setText(text)

    def setIcon(self, icon):
        self.tray.setIcon(getIcon(icon))

    def setToolTip(self, text):
        self.tray.setToolTip(text)

    def isTrayAvailable(self):
        return QSystemTrayIcon.isSystemTrayAvailable()

    def handleQtCloseEvent(self, event: QCloseEvent):
        if self.isTrayAvailable() and self._parent.isVisible():
            event.accept()
            self.__hideShowCall()
            return

        self.close()
        QMainWindow.closeEvent(self._parent, event)

    # -------------------------------------------------------------------------------------------

    def show(self):
        if not self._quit_added:
            self._quit_added = True

            self.addSeparator("_quit")
            self.addAction("show", self._parent.tr("Hide"))
            self.addAction("quit", self._parent.tr("Quit"))
            self.setActionIcon("quit", "application-exit")
            self.connect("show", self.__hideShowCall)
            self.connect("quit", self.__quitCall)

        self.tray.show()

    def hide(self):
        self.tray.hide()

    def close(self):
        self.menu.close()

    def exec_(self, app: QApplication):
        self._app = app
        return app.exec_()

    # -------------------------------------------------------------------------------------------

    def get_act_index(self, act_name_id):
        for i in range(len(self.acts)):
            if self.acts[i].name_id == act_name_id:
                return i
        else:
            _logger.error(f"Failed to get action index for {act_name_id}")
            return -1

    def get_sep_index(self, sep_name_id):
        for i in range(len(self.seps)):
            if self.seps[i].name_id == sep_name_id:
                return i
        else:
            _logger.error(f"Failed to get separator index for {sep_name_id}")
            return -1

    def get_menu_index(self, menu_name_id):
        for i in range(len(self.menus)):
            if self.menus[i].name_id == menu_name_id:
                return i
        else:
            _logger.error(f"Failed to get menu index for {menu_name_id}")
            return -1

    # -------------------------------------------------------------------------------------------

    def gtk_call_func(self, gtkmenu, act_name_id):
        i = self.get_act_index(act_name_id)
        if i < 0: return None

        return self.acts[i].func

    def qt_systray_clicked(self, reason):
        if reason in (QSystemTrayIcon.DoubleClick, QSystemTrayIcon.Trigger):
            self.__hideShowCall()

    # -------------------------------------------------------------------------------------------

    def __hideShowCall(self):
        if self._parent.isVisible():
            self.setActionText("show", self._parent.tr("Restore"))
            self._parent.hide()

            if self._app:
                self._app.setQuitOnLastWindowClosed(False)

        else:
            self.setActionText("show", self._parent.tr("Minimize"))

            if self._parent.isMaximized():
                self._parent.showMaximized()
            else:
                self._parent.showNormal()

            if self._app:
                self._app.setQuitOnLastWindowClosed(True)

            QTimer.singleShot(500, self.__raiseWindow)

    def __quitCall(self):
        if self._app:
            self._app.setQuitOnLastWindowClosed(True)

        self._parent.hide()
        self._parent.close()

        if self._app:
            self._app.quit()

    def __raiseWindow(self):
        self._parent.activateWindow()
        self._parent.raise_()
