#!/usr/bin/env python3
#
# Copyright 2022 CNApy organization
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""The Application class"""
import ast
import configparser
import io
import sys
import traceback
from configparser import NoOptionError, NoSectionError
from pathlib import Path

import cobra
from qtpy.QtCore import Qt, QLocale
from qtpy.QtGui import QColor, QPalette
from qtpy.QtWidgets import QApplication
from qtpy.QtWidgets import QMessageBox

# Necessary on some systems so that, e.g., the in/put metabolite flux visualization in the ipython console can run
import nest_asyncio
nest_asyncio.apply()

# ensuring compatibility with high resolution displays
if hasattr(Qt, 'AA_EnableHighDpiScaling'):
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
if hasattr(Qt, 'AA_UseHighDpiPixmaps'):
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)

from cnapy.appdata import AppData
from cnapy.gui_elements.main_window import MainWindow
import cnapy.utils as utils

def excepthook(cls, exception, tb):
    output = io.StringIO()
    traceback.print_exception(cls, exception, tb, file=output)
    traceback.print_tb(tb, file=output)
    exstr = ''.join(traceback.format_exception(None, exception, exception.__traceback__))

    # If the exception has a user-readable text message, let's add it in bold
    # at the top of the error message.
    if hasattr(exception, "message"):
        exstr = f"<p><b>{exception.message}</b></p>" + exstr

    utils.show_unknown_error_box(exstr)
    excepthook2(cls, exception, tb)


excepthook2 = sys.excepthook
sys.excepthook = excepthook

class Application:
    '''The Application class'''

    def __init__(
        self,
        project_path: None | str,
        scenario_path: None | str,
    ):
        QLocale.setDefault(QLocale(QLocale.English)) # to set . as decimal point
        self.qapp = QApplication(sys.argv)
        self.appdata = AppData()
        palette = QPalette()
        if not self.appdata.is_in_dark_mode:
            # "Light mode"
            palette.setColor(QPalette.Window, QColor(240, 240, 240))
            palette.setColor(QPalette.WindowText, Qt.black)
            palette.setColor(QPalette.Base, Qt.white)               # e.g. QLineEdit background
            palette.setColor(QPalette.AlternateBase, QColor(225, 225, 225))
            palette.setColor(QPalette.ToolTipBase, Qt.white)
            palette.setColor(QPalette.ToolTipText, Qt.black)
            palette.setColor(QPalette.Text, Qt.black)               # generic text colour
            palette.setColor(QPalette.Button, QColor(240, 240, 240))
            palette.setColor(QPalette.ButtonText, Qt.black)
            palette.setColor(QPalette.BrightText, Qt.red)
            palette.setColor(QPalette.Highlight, QColor(0, 120, 215))
            palette.setColor(QPalette.HighlightedText, Qt.white)
        else:
            # "Dark mode"
            palette.setColor(QPalette.Window, QColor(53, 53, 53)) # Main window background
            palette.setColor(QPalette.WindowText, Qt.white) # Text
            palette.setColor(QPalette.Base, QColor(75, 75, 75)) # Map etc. backgrounds
            palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53)) # Alternate backgrounds in lists/tables
            palette.setColor(QPalette.ToolTipBase, QColor(35, 35, 35)) # Tooltip background
            palette.setColor(QPalette.ToolTipText, Qt.white) # Tooltip text
            palette.setColor(QPalette.Text, Qt.white) # Text color in widgets
            palette.setColor(QPalette.Button, QColor(53, 53, 53)) # Button background
            palette.setColor(QPalette.ButtonText, Qt.white) # Button text
            palette.setColor(QPalette.BrightText, Qt.red) # Highlighted error text
            # Highlights
            palette.setColor(QPalette.Highlight, QColor(142, 45, 197)) # Selection background
            palette.setColor(QPalette.HighlightedText, Qt.white) # Selection text color
            # Disabled state
            palette.setColor(QPalette.Disabled, QPalette.Text, QColor(164, 164, 164))
            palette.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(164, 164, 164))
            palette.setColor(QPalette.Disabled, QPalette.WindowText, QColor(164, 164, 164))
            palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
            palette.setColor(QPalette.Disabled, QPalette.HighlightedText, QColor(164, 164, 164))
        self.qapp.setStyle("fusion")
        self.qapp.setPalette(palette)
        config_file_version = self.read_config()
        font = self.qapp.font()
        font.setPointSizeF(self.appdata.font_size)
        self.qapp.setFont(font)
        self.window = MainWindow(self.appdata, project_path, scenario_path)
        self.appdata.window = self.window
        self.appdata.unsavedScenarioChanges.connect(self.window.update_scenario_file_name)
        self.window.recreate_maps()
        self.window.resize(1200, 1000)
        self.window.save_project_action.setEnabled(False)
        self.window.show()

        # First start-up behaviour (it can also happen whenever the cnapy-config.txt is deleted)
        if config_file_version == "unknown":
            self.first_start_up_message()
        else:
            self.window.build_recent_cna_menu()

        if sys.platform == "win32":  # CNApy running on Windows
            # on Windows disable multiprocessing in COBRApy because of performance issues
            cobra.Configuration().processes = 1
        self.read_cobrapy_config()

        # Execute application
        self.qapp.aboutToQuit.connect(
            self.window.centralWidget().shutdown_kernel
        )
        sys.exit(self.qapp.exec_())

    def first_start_up_message(self):
        msgBox = QMessageBox()
        msgBox.setWindowTitle("First start")
        msgBox.setText(
            "Welcome to CNApy! In the next step, you can choose to download CNApy's "
            "metabolic network example projects.\n"
            "You can also do this later under 'Project->Download CNApy example projects...'.\n"
            "Also, should CNApy's font size be too small or too large, you can change\n"
            "it under 'Config->Configure CNApy...'."
        )
        msgBox.setIcon(QMessageBox.Information)
        msgBox.exec()

        self.window.show_config_dialog(first_start=True)
        self.window.download_examples()

    def model(self):
        return self.appdata.project.cobra_py_model

    def set_model(self, model: cobra.Model):
        self.appdata.project.cobra_py_model = model

    def read_config(self):
        ''' Try to read data from cnapy-config.txt into appdata'''
        config_file_version = "unknown"
        config_parser = configparser.RawConfigParser()
        if len(config_parser.read(self.appdata.conf_path)) == 0:
                print("No cnapy-config.txt file found, using default settings.")
                return config_file_version
        try:
            try:
                config_file_version = config_parser.get('cnapy-config', 'version')
            except (KeyError, NoOptionError):
                print("Could not find version in cnapy-config.txt")

            try:
                self.appdata.work_directory = config_parser.get(
                    'cnapy-config', 'work_directory')
                self.appdata.last_scen_directory = self.appdata.work_directory
            except (KeyError, NoOptionError):
                print("Could not find work_directory in cnapy-config.txt")

            try:
                color = config_parser.get(
                    'cnapy-config', 'scen_color')
                self.appdata.scen_color = QColor.fromRgb(int(color))
            except (KeyError, NoOptionError):
                print("Could not find scen_color in cnapy-config.txt")
            try:
                color = config_parser.get(
                    'cnapy-config', 'comp_color')
                self.appdata.comp_color = QColor.fromRgb(int(color))
            except (KeyError, NoOptionError):
                print("Could not find comp_color in cnapy-config.txt")
            try:
                color = config_parser.get(
                    'cnapy-config', 'spec1_color')
                self.appdata.special_color_1 = QColor.fromRgb(int(color))
            except (KeyError, NoOptionError):
                print("Could not find spec1_color in cnapy-config.txt")
            try:
                color = config_parser.get(
                    'cnapy-config', 'spec2_color')
                self.appdata.special_color_2 = QColor.fromRgb(int(color))
            except (KeyError, NoOptionError):
                print("Could not find spec2_color in cnapy-config.txt")
            try:
                color = config_parser.get(
                    'cnapy-config', 'default_color')
                self.appdata.default_color = QColor.fromRgb(int(color))
            except (KeyError, NoOptionError):
                print("Could not find default_color in cnapy-config.txt")
            try:
                font_size = config_parser.get(
                    'cnapy-config', 'font_size')
                self.appdata.font_size = float(font_size)
            except (KeyError, NoOptionError):
                print("Could not find font_size in cnapy-config.txt")
            try:
                box_width = config_parser.get(
                    'cnapy-config', 'box_width')
                self.appdata.box_width = int(box_width)
            except (KeyError, NoOptionError):
                print("Could not find box_width in cnapy-config.txt")
            try:
                rounding = config_parser.get(
                    'cnapy-config', 'rounding')
                self.appdata.rounding = int(rounding)
            except (KeyError, NoOptionError):
                print("Could not find rounding in cnapy-config.txt")
            try:
                abs_tol = config_parser.get(
                    'cnapy-config', 'abs_tol')
                self.appdata.abs_tol = float(abs_tol)
            except (KeyError, NoOptionError):
                print("Could not find abs_tol in cnapy-config.txt")

            try:
                recent_cna_files = config_parser.get(
                    'cnapy-config', 'recent_cna_files')
                self.appdata.recent_cna_files = ast.literal_eval(recent_cna_files)
            except (KeyError, NoOptionError):
                print("Could not find recent_cna_files in cnapy-config.txt")
                self.appdata.recent_cna_files = []
            
            try:
                is_in_dark_mode = config_parser.get(
                    'cnapy-config', 'is_in_dark_mode')
                if is_in_dark_mode == "False":
                    self.appdata.is_in_dark_mode = False
                else:
                    self.appdata.is_in_dark_mode = True
            except (KeyError, NoOptionError):
                print("Could not find is_in_dark_mode in cnapy-config.txt")

            self.appdata.use_results_cache = config_parser.getboolean('cnapy-config',
                    'use_results_cache', fallback=self.appdata.use_results_cache)
            self.appdata.results_cache_dir = Path(config_parser.get('cnapy-config',
                    'results_cache_directory', fallback=self.appdata.results_cache_dir))

        except NoSectionError:
            print("Could not find section cnapy-config in cnapy-config.txt")
        return config_file_version

    def read_cobrapy_config(self):
        ''' Try to read data from cobrapy-config.txt into appdata'''
        config_parser = configparser.RawConfigParser()
        try:
            if len(config_parser.read(self.appdata.cobrapy_conf_path)) == 0:
                print("No cobrapy-config.txt file found, using COBRApy base settings.")
                return
            try:
                cobra.Configuration().solver = config_parser.get('cobrapy-config', 'solver')
            except Exception as e:
                print("Cannot set solver from cobrapy-config.txt file because:", e,
                      "\nReverting solver to COBRApy base setting.")
            try:
                cobra.Configuration().processes = int(
                    config_parser.get('cobrapy-config', 'processes'))
            except Exception as e:
                print("Cannot set number of processes from cobrapy-config.txt file because:", e,
                      "\nReverting number of processes to COBRApy base setting.")
            try:
                val = float(config_parser.get('cobrapy-config', 'tolerance'))
                if 1e-9 <= val <= 0.1:
                    cobra.Configuration().tolerance = val
                else:
                    raise ValueError
            except Exception as e:
                print(e, "\nCannot set tolerance from cobrapy-config.txt file because it must be a vaule between 1e-9 and 0.1, reverting to COBRApy base setting.")
        except Exception as e:
            print('Could not read', self.appdata.cobrapy_conf_path, 'because:', e)
