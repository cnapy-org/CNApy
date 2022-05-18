#!/usr/bin/env python3
#
# Copyright 2019 PSB & ST
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
import configparser
import io
import os
import sys
import traceback
from configparser import NoOptionError, NoSectionError
from pathlib import Path

import cobra
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor
from qtpy.QtWidgets import QApplication, QMessageBox

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
    # exstr = output.getvalue()
    exstr = ''.join(traceback.format_exception(None, exception, exception.__traceback__))
    utils.show_unknown_error_box(exstr)
    excepthook2(cls, exception, tb)


excepthook2 = sys.excepthook
sys.excepthook = excepthook


class Application:
    '''The Application class'''

    def __init__(self):
        self.qapp = QApplication(sys.argv)
        self.appdata = AppData()
        self.qapp.setStyle("fusion")
        self.window = MainWindow(self.appdata)
        self.appdata.window = self.window
        self.window.recreate_maps()
        self.window.resize(1200, 1000)
        self.window.save_project_action.setEnabled(False)
        self.window.show()

        config_file_version = self.read_config()
        if sys.platform == "win32":  # CNApy running on Windows
            # on Windows disable multiprocessing in COBRApy because of performance issues
            cobra.Configuration().processes = 1
        self.read_cobrapy_config()

        # Execute application

        self.qapp.aboutToQuit.connect(
            self.window.centralWidget().shutdown_kernel)
        sys.exit(self.qapp.exec_())

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
