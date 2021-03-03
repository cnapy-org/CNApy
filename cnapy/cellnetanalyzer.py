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
"""The CellNetAnalyzer class"""
import configparser
import sys

import cobra
from qtpy.QtGui import QColor
from qtpy.QtWidgets import QApplication

from cnapy.cnadata import CnaData
from cnapy.gui_elements.mainwindow import MainWindow
from cnapy.legacy import try_matlab_engine, try_octave_engine


class CellNetAnalyzer:
    def __init__(self):
        self.qapp = QApplication(sys.argv)
        self.appdata = CnaData()
        self.qapp.setStyle("fusion")
        self.window = MainWindow(self.appdata)
        self.appdata.window = self.window

        configParser = configparser.RawConfigParser()
        configParser.read(self.appdata.conf_path)

        version = "unknown"
        try:
            version = configParser.get('cnapy-config', 'version')
        except:
            print("Could not read version in cnapy-config.txt")

        if version != self.appdata.version:
            self.window.show_config_dialog()
        else:
            self.config_app()

        self.window.disable_enable_dependent_actions()
        self.window.save_project_action.setEnabled(False)
        self.window.resize(800, 600)
        self.window.show()

        # Execute application

        self.qapp.aboutToQuit.connect(
            self.window.centralWidget().shutdown_kernel)
        sys.exit(self.qapp.exec_())

    def model(self):
        return self.appdata.project.cobra_py_model

    def set_model(self, model: cobra.Model):
        self.appdata.project.cobra_py_model = model

    def config_app(self):

        configParser = configparser.RawConfigParser()
        configParser.read(self.appdata.conf_path)

        self.appdata.matlab_engine = try_matlab_engine()

        try:
            self.appdata.matlab_path = configParser.get(
                'cnapy-config', 'matlab_path')
        except:
            self.appdata.matlab_path = ""
        try:
            self.appdata.octave_executable = configParser.get(
                'cnapy-config', 'OCTAVE_EXECUTABLE')
        except:
            self.appdata.octave_executable = ""
        self.appdata.octave_engine = try_octave_engine(
            self.appdata.octave_executable)
        try:
            selected_engine = configParser.get(
                'cnapy-config', 'selected_engine')
            self.appdata.selected_engine = selected_engine
        except:
            print("Could not read selected_engine in cnapy-config.txt")
            self.appdata.selected_engine = None

        self.appdata.select_engine()

        try:
            self.appdata.cna_path = configParser.get(
                'cnapy-config', 'cna_path')
        except:
            self.appdata.cna_path = ""

        try:
            color = configParser.get(
                'cnapy-config', 'scen_color')
            self.appdata.Scencolor = QColor.fromRgb(int(color))
        except:
            print("Could not read scen_color in cnapy-config.txt")
            self.appdata.Scencolor = QColor.fromRgb(4278230527)
        try:
            color = configParser.get(
                'cnapy-config', 'comp_color')
            self.appdata.Compcolor = QColor.fromRgb(int(color))
        except:
            print("Could not read comp_color in cnapy-config.txt")
            self.appdata.Compcolor = QColor.fromRgb(4290369023)
        try:
            color = configParser.get(
                'cnapy-config', 'spec1_color')
            self.appdata.SpecialColor1 = QColor.fromRgb(int(color))
        except:
            print("Could not read spec1_color in cnapy-config.txt")
            self.appdata.SpecialColor1 = QColor.fromRgb(4294956551)
        try:
            color = configParser.get(
                'cnapy-config', 'spec2_color')
            self.appdata.SpecialColor2 = QColor.fromRgb(int(color))
        except:
            print("Could not read spec2_color in cnapy-config.txt")
            self.appdata.SpecialColor2 = QColor.fromRgb(
                4289396480)  # for bounds excluding 0
        try:
            color = configParser.get(
                'cnapy-config', 'default_color')
            self.appdata.Defaultcolor = QColor.fromRgb(int(color))
        except:
            print("Could not read default_color in cnapy-config.txt")
            self.appdata.Defaultcolor = QColor.fromRgb(
                4288716964)
        try:
            rounding = configParser.get(
                'cnapy-config', 'rounding')
            self.appdata.rounding = int(rounding)
        except:
            print("Could not read rounding in cnapy-config.txt")
            self.appdata.rounding = 3
        try:
            abs_tol = configParser.get(
                'cnapy-config', 'abs_tol')
            self.appdata.abs_tol = float(abs_tol)
        except:
            print("Could not read abs_tol in cnapy-config.txt")
            self.appdata.abs_tol = 0.000000001
