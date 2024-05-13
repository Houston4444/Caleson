

import logging
import tempfile
import subprocess

from PyQt5.QtCore import pyqtSlot, Qt
from PyQt5.QtWidgets import (
    QDialog, QLabel, QRadioButton, QButtonGroup,
    QTableWidgetItem, QDialogButtonBox,
    QMessageBox, QApplication)

from firewire_database import DRIVER_INTERFACES
import ui_firewire

_logger = logging.getLogger()
_translate = QApplication.translate

BLACK_FILE = '/etc/modprobe.d/snd-firewire-modules-blacklist-librazik.conf'

# dict of drivers under the form {'driver_name': blacklisted}
drivers = dict[str, bool]()


def update_from_black_file() -> bool:
    drivers.clear()
    
    try:
        with open(BLACK_FILE, 'r') as f:
            contents = f.read()
    except BaseException as e:
        _logger.error(f"Failed to read firewire blacklist: {str(e)}")

        for driver in DRIVER_INTERFACES.keys():
            drivers[driver] = False

        return False
    
    for line in contents.splitlines():
        line = line.strip()
        commented = line.startswith('#')
        while line.startswith('#'):
            line = line[1:]
        if not line.startswith('blacklist '):
            continue
        
        driver = line.partition(' ')[2]
        if not commented or drivers.get(driver) is None:
            drivers[driver] = not commented
    
    return True

def get_new_blackfile_contents(tmp_drivers: dict[str, bool]) -> str:
    '''returns the contents needed in BLACK_FILE
    to apply blacklists from the drivers dict'''
    try:
        with open(BLACK_FILE, 'r') as f:
            contents = f.read()
    except BaseException as e:
        _logger.error(str(e))
        return ''
    
    new_lines = list[str]()
    blacklist_done = set[str]()
    
    for line in contents.splitlines():
        sline = line.strip()
        while sline.startswith('#'):
            sline = sline[1:]
        
        sline = sline.strip()
        if not sline.startswith('blacklist '):
            new_lines.append(line)
            continue
        
        driver = sline.partition(' ')[2]
        if driver in blacklist_done:
            # double line, do not rewrite it in output
            continue

        if not driver in drivers.keys():
            new_lines.append(line)
            continue
        
        if tmp_drivers[driver]:
            new_lines.append(f'blacklist {driver}')
        else:
            new_lines.append(f'#blacklist {driver}')

        blacklist_done.add(driver)
            
    for driver, blacklisted in tmp_drivers.items():
        if not driver in blacklist_done:
            if blacklisted:
                new_lines.append(f'blacklist {driver}')
            else:
                new_lines.append(f'#blacklist {driver}')
    
    return '\n'.join(new_lines)

def write_tmp_black_file(tmp_drivers: dict[str, bool]) -> str:
    'write contents in a tmp file, and returns the tmp file path as str'
    contents = get_new_blackfile_contents(tmp_drivers)
    if not contents:
        return ''
    
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write(contents)
    
    return f.name


class WidgetsLine:
    def __init__(self, dialog: 'FirewireDialog',
                 name: str, blacklisted: bool):
        self.dialog = dialog
        self.driver_name = name
        self.alsa_btn = QRadioButton()
        self.fw_btn = QRadioButton()
        self.btn_grp = QButtonGroup()
        self.btn_grp.addButton(self.alsa_btn)
        self.btn_grp.addButton(self.fw_btn)
        self.alsa_btn.setChecked(not blacklisted)
        self.fw_btn.setChecked(blacklisted)
        self.alsa_btn.clicked.connect(self.dialog.driver_changed)
        self.fw_btn.clicked.connect(self.dialog.driver_changed)
        
        self.item_label = QTableWidgetItem(name)
        self.item_label.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)

    def is_blacklisted(self) -> bool:
        return self.fw_btn.isChecked()


class FirewireDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.ui = ui_firewire.Ui_Dialog()
        self.ui.setupUi(self)
        
        update_from_black_file()
        
        self.widget_lines = list[WidgetsLine]()

        i = 0
        for driver, blacklisted in drivers.items():
            widgets_line = WidgetsLine(self, driver, blacklisted)
            self.ui.tableWidget.insertRow(i)
            self.ui.tableWidget.setItem(i, 0, widgets_line.item_label)
            self.ui.tableWidget.setCellWidget(i, 1, widgets_line.fw_btn)
            self.ui.tableWidget.setCellWidget(i, 2, widgets_line.alsa_btn)

            self.widget_lines.append(widgets_line)
            i += 1

        self.ui.tableWidget.resizeColumnsToContents()
        width = 0
        for i in range(3):
            width += self.ui.tableWidget.columnWidth(i)
        
        self.ui.tableWidget.setMinimumWidth(width + 6)
        self.ui.tableWidget.currentCellChanged.connect(
            self._current_cell_changed)
        self.ui.lineEditSearch.textEdited.connect(
            self._filter_bar_edited)
        
        self.set_apply_enabled(False)
        self.ui.buttonBox.button(QDialogButtonBox.Apply).clicked.connect(
            self.apply_changes)
    
    def set_apply_enabled(self, enabled: bool):
        self.ui.buttonBox.button(QDialogButtonBox.Apply).setEnabled(enabled)
    
    def apply_changes(self):
        tmp_drivers = dict[str, bool]()
        for widget_lines in self.widget_lines:
            tmp_drivers[widget_lines.driver_name] = widget_lines.is_blacklisted()
        
        tmp_file = write_tmp_black_file(tmp_drivers)
        if not tmp_file:
            return
        
        process = subprocess.run(['pkexec', 'mv', '-f', tmp_file, BLACK_FILE])
        if process.returncode:
            if process.returncode != 127:
                QMessageBox.critical(
                    self,
                    _translate('firewire_driver_chooser',
                               "Operation failed"),
                    _translate('firewire_driver_chooser',
                               "Failed to apply changes, sorry"))
            return
        
        update_from_black_file()
        self.set_apply_enabled(False)
        
        QMessageBox.information(
            self,
            _translate('firewire_driver_chooser',
                       'Operation completed'),
            _translate('firewire_driver_chooser',
                       'Changes have been applied to the system '
                       'but they will be used at next computer startup.'))
    
    @pyqtSlot(bool)
    def driver_changed(self, state: bool):
        for widget_lines in self.widget_lines:
            if (drivers[widget_lines.driver_name]
                    is not widget_lines.is_blacklisted()):
                self.set_apply_enabled(True)
                break
        else:
            self.set_apply_enabled(False)
    
    @pyqtSlot(int, int, int, int)
    def _current_cell_changed(self, row: int, column: int,
                              pv_row: int, pv_col: int):
        driver = self.widget_lines[row].driver_name
        self.ui.labelDriver.setText(driver)
        filter_text = self.ui.lineEditSearch.text().lower()

        if DRIVER_INTERFACES.get(driver) is None:
            self.ui.plainTextInterfaces.setPlainText('')

        elif filter_text:
            self.ui.plainTextInterfaces.setPlainText(
                '\n'.join([ifac for ifac in DRIVER_INTERFACES[driver]
                           if filter_text in ifac.lower()]))
            
        else:
            self.ui.plainTextInterfaces.setPlainText(
                '\n'.join(DRIVER_INTERFACES[driver]))

    @pyqtSlot(str)
    def _filter_bar_edited(self, text: str):
        if not text:
            self.ui.lineEditSearch.setStyleSheet('')
            for row in range(self.ui.tableWidget.rowCount()):
                self.ui.tableWidget.showRow(row)

            self.ui.tableWidget.setCurrentItem(
                self.ui.tableWidget.currentItem())
            return
        
        l_text = text.lower()
        matching_drivers = set[str]()
        for driver, interfaces in DRIVER_INTERFACES.items():
            for interface in interfaces:
                if l_text in interface.lower():
                    matching_drivers.add(driver)
                    break
        
        if matching_drivers:
            self.ui.lineEditSearch.setStyleSheet('')
            
            item_selected = False
            row = 0
            for driver in drivers.keys():
                if driver in matching_drivers:
                    self.ui.tableWidget.showRow(row)
                    if not item_selected:
                        self.ui.tableWidget.setCurrentCell(row, 0)
                        item_selected = True
                else:
                    self.ui.tableWidget.hideRow(row)
                row += 1
        else:
            self.ui.lineEditSearch.setStyleSheet(
                'QLineEdit{background:#40FF0000}')
            for row in range(self.ui.tableWidget.rowCount()):
                self.ui.tableWidget.hideRow(row)
