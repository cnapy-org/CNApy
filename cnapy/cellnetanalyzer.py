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
from PySide2.QtWidgets import QApplication

from cnapy.cnadata import CnaData
from cnapy.gui_elements.mainwindow import MainWindow
from cnapy.legacy import is_matlab_ready, is_octave_ready, restart_cna
from PySide2.QtGui import QColor


class CellNetAnalyzer:

    def __init__(self):
        self.qapp = QApplication(sys.argv)
        self.appdata = CnaData()
        self.window = MainWindow(self.appdata)
        self.appdata.window = self.window

        self.window.efm_action.setEnabled(False)
        self.window.mcs_action.setEnabled(False)

        configParser = configparser.RawConfigParser()
        configFilePath = r'cnapy-config.txt'
        configParser.read(configFilePath)

        try:
            self.appdata.cna_path = configParser.get(
                'cnapy-config', 'cna_path')
        except:
            print("CNA not found please check the cna_path in cnapy-config.txt")
        else:
            if is_matlab_ready():
                self.window.efm_action.setEnabled(True)
                self.window.mcs_action.setEnabled(True)

            if is_octave_ready():
                self.window.efm_action.setEnabled(True)
                self.window.mcs_action.setEnabled(True)

            if not restart_cna(self.appdata.cna_path):
                self.window.efm_action.setEnabled(False)
                self.window.mcs_action.setEnabled(False)

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

        self.window.save_project_action.setEnabled(False)
        self.window.resize(800, 600)
        self.window.show()

        # Execute application
        sys.exit(self.qapp.exec_())

    def model(self):
        return self.appdata.project.cobra_py_model

    def set_model(self, model: cobra.Model):
        self.appdata.project.cobra_py_model = model
