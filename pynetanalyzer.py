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
import json
from PySide2.QtCore import Slot
from PySide2.QtWidgets import (QAction, QApplication, QFileDialog,
                               QGraphicsScene, QHBoxLayout,
                               QMainWindow, QTabWidget,
                               QWidget)
import cobra

# Internal modules
from gui_elements.about_dialog import AboutDialog
from gui_elements.reactions_list import ReactionList
from gui_elements.species_list import SpeciesList
from gui_elements.map_view import MapView
from gui_elements.console import Console


class PnaData:
    def __init__(self):
        self.cobra_py_model = cobra.Model()
        self.maps = [{}]
        self.values = {}


class CentralWidget(QWidget):
    """The PyNetAnalyzer central widget"""

    def __init__(self, appdata):
        QWidget.__init__(self)
        self.appdata = appdata
        self.tabs = QTabWidget()
        self.reaction_list = ReactionList(self.appdata)
        self.specie_list = SpeciesList(self.appdata)
        self.tabs.addTab(self.reaction_list, "Reactions")
        self.tabs.addTab(self.specie_list, "Species")

        self.scene = QGraphicsScene()
        self.map = MapView(self.appdata, self.scene)
        self.map.show()
        self.tabs.addTab(self.map, "Map")

        self.console = Console(self.appdata)
        self.tabs.addTab(self.console, "Console")

        layout = QHBoxLayout()
        layout.addWidget(self.tabs)
        self.setLayout(layout)

        self.reaction_list.changedMap.connect(self.update_map)
        self.reaction_list.changedModel.connect(self.update_model_view)
        self.specie_list.changedModel.connect(self.update_model_view)

    def update_model_view(self):
        print("update_model_view")
        self.reaction_list.update()
        self.specie_list.update()

    def update_map(self):
        print("update_map")
        self.map.update()
        self.tabs.setCurrentIndex(2)


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

        import_sbml_action = QAction("Import SBML...", self)
        self.file_menu.addAction(import_sbml_action)
        import_sbml_action.triggered.connect(self.import_sbml)

        export_sbml_action = QAction("Export SBML...", self)
        self.file_menu.addAction(export_sbml_action)
        export_sbml_action.triggered.connect(self.export_sbml)

        load_maps_action = QAction("Load map...", self)
        self.file_menu.addAction(load_maps_action)
        load_maps_action.triggered.connect(self.load_maps)

        save_maps_action = QAction("Save maps...", self)
        self.file_menu.addAction(save_maps_action)
        save_maps_action.triggered.connect(self.save_maps)

        save_project_action = QAction("Save project...", self)
        self.file_menu.addAction(save_project_action)

        save_as_project_action = QAction("Save project as...", self)
        self.file_menu.addAction(save_as_project_action)
        # save_as_project_action.triggered.connect(self.save_project_as)

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
        fba_action.triggered.connect(self.fba)

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
    def import_sbml(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.xml")

        self.appdata.cobra_py_model = cobra.io.read_sbml_model(filename[0])
        self.update_view()

    @Slot()
    def export_sbml(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.xml")

        cobra.io.write_sbml_model(
            self.appdata.cobra_py_model, filename[0])

    @Slot()
    def load_maps(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.maps")

        with open(filename[0], 'r') as fp:
            self.appdata.maps = json.load(fp)
        self.update_view()

    @Slot()
    def save_maps(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.maps")

        with open(filename[0], 'w') as fp:
            json.dump(self.appdata.maps, fp)

    # def reaction_selected(self, item, _column):
    #     # print("something something itemActivated", item, column)
    #     print(item.data(2, 0).name)

    def update_view(self):
        self.centralWidget().reaction_list.update()
        self.centralWidget().specie_list.update()
        self.centralWidget().map.update()

    def fba(self):
        solution = self.appdata.cobra_py_model.optimize()
        if solution.status == 'optimal':
            self.centralWidget().map.set_values(solution.fluxes)


if __name__ == "__main__":
    # Qt Application
    app = QApplication(sys.argv)

    window = MainWindow()
    window.resize(800, 600)
    window.show()

    # Execute application
    sys.exit(app.exec_())
