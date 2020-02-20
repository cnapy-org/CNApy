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
"""The PyNetAnalyzer main"""
import os
import sys

from PySide2.QtCore import Slot
from PySide2.QtWidgets import (QGraphicsItem, QAction, QApplication, QFileDialog,
                               QGraphicsScene, QHBoxLayout, QLineEdit,
                               QMainWindow, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QWidget)
from PySide2.QtSvg import QGraphicsSvgItem

# Internal modules
from gui_elements.about_dialog import AboutDialog
from gui_elements.reactions_list import ReactionList
from gui_elements.species_list import SpeciesList
from gui_elements.map_view import MapView, ReactionBox

import cobra


class PnaData:
    def __init__(self):
        self.cobra_py_model = cobra.Model()


class CentralWidget(QWidget):
    """The PyNetAnalyzer central widget"""

    def __init__(self, appdata):
        QWidget.__init__(self)
        self.appdata = appdata
        tabs = QTabWidget()
        self.reaction_list = ReactionList(self.appdata)
        self.specie_list = SpeciesList(self.appdata)
        tabs.addTab(self.reaction_list, "Reactions")
        tabs.addTab(self.specie_list, "Species")

        self.scene = QGraphicsScene()
        self.view = MapView(self.scene)
        self.view.show()
        tabs.addTab(self.view, "Map")

        layout = QHBoxLayout()
        layout.addWidget(tabs)
        self.setLayout(layout)


class MainWindow(QMainWindow):
    """The PyNetAnalyzer main window"""

    def __init__(self):
        QMainWindow.__init__(self)
        self.setWindowTitle("PyNetAnalyzer")

        # Data
        self.appdata = PnaData()

        # CentralWidget
        central_widget = CentralWidget(self.appdata)
        self.setCentralWidget(central_widget)

        # self.centralWidget().reaction_list.itemActivated.connect(self.reaction_selected)

        # Menu
        self.menu = self.menuBar()
        self.file_menu = self.menu.addMenu("File")

        new_project_action = QAction("New project...", self)
        self.file_menu.addAction(new_project_action)

        open_project_action = QAction("Import SBML...", self)
        self.file_menu.addAction(open_project_action)
        open_project_action.triggered.connect(self.open_project)

        save_project_action = QAction("Save project...", self)
        self.file_menu.addAction(save_project_action)

        save_as_project_action = QAction("Save project as...", self)
        self.file_menu.addAction(save_as_project_action)

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        self.file_menu.addAction(exit_action)
        exit_action.triggered.connect(self.exit_app)

        self.edit_menu = self.menu.addMenu("Edit")
        network_compose_action = QAction("Network composer...", self)
        self.edit_menu.addAction(network_compose_action)

        self.find_menu = self.menu.addMenu("Find")
        find_reaction_action = QAction("Find reaction...", self)
        self.find_menu.addAction(find_reaction_action)

        self.analysis_menu = self.menu.addMenu("Analysis")
        fba_action = QAction("Flux Balance Analysis (FBA)...", self)
        self.analysis_menu.addAction(fba_action)
        fva_action = QAction("Flux Variability Analysis (FVA)...", self)
        self.analysis_menu.addAction(fva_action)

        self.help_menu = self.menu.addMenu("Help")
        about_action = QAction("About PyNetAnalyzer...", self)
        self.help_menu.addAction(about_action)
        about_action.triggered.connect(self.show_about)

    @Slot()
    def exit_app(self, _checked):
        QApplication.quit()

    @Slot()
    def show_about(self, _checked):
        dialog = AboutDialog()
        dialog.exec_()

    @Slot()
    def open_project(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.xml")

        self.appdata.cobra_py_model = cobra.io.read_sbml_model(filename[0])

        self.update_view()

    # def reaction_selected(self, item, _column):
    #     # print("something something itemActivated", item, column)
    #     print(item.data(2, 0).name)

    def update_view(self):
        self.centralWidget().reaction_list.update()
        self.centralWidget().specie_list.update()

        # draw a map
        scene = self.centralWidget().scene
        view = self.centralWidget().view
        view.setAcceptDrops(True)

        background = QGraphicsSvgItem("testsvg.svg")
        background.setFlags(QGraphicsItem.ItemClipsToShape)
        scene.addItem(background)

        for i in range(1, 11):
            for j in range(1, 11):
                if i % 2 == 0:
                    le1.setStyleSheet("background: #ff9999")
                le1 = QLineEdit()
                le1.setMaximumWidth(80)
                proxy1 = scene.addWidget(le1)
                proxy1.show()
                ler1 = ReactionBox(proxy1, str(i+(j*10)))
                ler1.setPos(i*100, j*100)
                scene.addItem(ler1)
                view.reaction_boxes[str(i+(j*10))] = ler1


if __name__ == "__main__":
    # Qt Application
    app = QApplication(sys.argv)

    window = MainWindow()
    window.resize(800, 600)
    window.show()

    # Execute application
    sys.exit(app.exec_())
