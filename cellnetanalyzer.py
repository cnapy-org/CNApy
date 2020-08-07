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
import cobra

import sys
from cnadata import CnaData
from gui_elements.mainwindow import MainWindow

from PySide2.QtWidgets import QApplication


class CellNetAnalyzer:

    def __init__(self):
        self.qapp = QApplication(sys.argv)
        self.appdata = CnaData()
        self.window = MainWindow(self.appdata)
        self.window.resize(800, 600)
        self.window.show()

        # Execute application
        sys.exit(self.qapp.exec_())

    def model(self):
        return self.appdata.project.cobra_py_model

    def set_model(self, model: cobra.Model):
        self.appdata.project.cobra_py_model = model
