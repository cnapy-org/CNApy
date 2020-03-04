import os
import json
from zipfile import ZipFile
from tempfile import TemporaryDirectory
from PySide2.QtCore import Slot
from PySide2.QtWidgets import (
    QAction, QApplication, QFileDialog, QMainWindow)
from gui_elements.centralwidget import CentralWidget

from gui_elements.about_dialog import AboutDialog

from legacy import matlabcall

import cobra


class MainWindow(QMainWindow):
    """The cnapy main window"""

    def __init__(self, app):
        QMainWindow.__init__(self)
        self.setWindowTitle("cnapy")
        self.app = app

        central_widget = CentralWidget(self.app)
        self.setCentralWidget(central_widget)

        self.menu = self.menuBar()
        self.file_menu = self.menu.addMenu("File")

        new_project_action = QAction("New project...", self)
        self.file_menu.addAction(new_project_action)
        new_project_action.triggered.connect(self.new_project)

        open_project_action = QAction("Open project ...", self)
        self.file_menu.addAction(open_project_action)
        open_project_action.triggered.connect(self.open_project)

        # save_project_action = QAction("Save project...", self)
        # self.file_menu.addAction(save_project_action)

        save_as_project_action = QAction("Save project as...", self)
        self.file_menu.addAction(save_as_project_action)
        save_as_project_action.triggered.connect(self.save_project_as)

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

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        self.file_menu.addAction(exit_action)
        exit_action.triggered.connect(self.exit_app)

        self.find_menu = self.menu.addMenu("Find")
        find_reaction_action = QAction("Find reaction...", self)
        self.find_menu.addAction(find_reaction_action)

        self.analysis_menu = self.menu.addMenu("Analysis")
        fba_action = QAction("Flux Balance Analysis (FBA)...", self)
        fba_action.triggered.connect(self.fba)
        self.analysis_menu.addAction(fba_action)

        fva_action = QAction("Flux Variability Analysis (FVA)...", self)
        fba_action.triggered.connect(self.fva)
        self.analysis_menu.addAction(fva_action)

        self.help_menu = self.menu.addMenu("Help")
        about_action = QAction("About cnapy...", self)
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

        self.app.appdata.cobra_py_model = cobra.io.read_sbml_model(filename[0])
        self.update_view()

    @Slot()
    def export_sbml(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.xml")

        cobra.io.write_sbml_model(
            self.app.appdata.cobra_py_model, filename[0])

    @Slot()
    def load_maps(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.maps")

        with open(filename[0], 'r') as fp:
            self.app.appdata.maps = json.load(fp)
        self.update_view()

    @Slot()
    def save_maps(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.maps")

        with open(filename[0], 'w') as fp:
            json.dump(self.app.appdata.maps, fp)

    @Slot()
    def new_project(self, _checked):
        self.app.appdata.cobra_py_model = cobra.Model()
        self.app.appdata.maps = [{}]

        self.update_view()

    @Slot()
    def open_project(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.cna")

        folder = TemporaryDirectory()

        with ZipFile(filename[0], 'r') as zip_ref:
            zip_ref.extractall(folder.name)

            with open(folder.name+"/maps.json", 'r') as fp:
                self.app.appdata.maps = json.load(fp)

            self.app.appdata.cobra_py_model = cobra.io.read_sbml_model(
                folder.name+"/model.sbml")
            self.update_view()

    @Slot()
    def save_project_as(self, _checked):

        print("save_project_as")
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.cna")

        folder = TemporaryDirectory().name

        cobra.io.write_sbml_model(
            self.app.appdata.cobra_py_model, folder + "model.sbml")

        with open(folder + "maps.json", 'w') as fp:
            json.dump(self.app.appdata.maps, fp)

        with ZipFile(filename[0], 'w') as zipObj:
            zipObj.write(folder + "model.sbml", arcname="model.sbml")
            zipObj.write(folder + "maps.json", arcname="maps.json")

    def update_view(self):
        self.centralWidget().reaction_list.update()
        self.centralWidget().specie_list.update()
        self.centralWidget().map.update()

    def fba(self):
        solution = self.app.appdata.cobra_py_model.optimize()
        if solution.status == 'optimal':
            self.app.appdata.high = 0.0
            self.app.appdata.low = 0.0
            for key in solution.fluxes.keys():
                self.app.appdata.values[key] = solution.fluxes[key]
                if self.app.appdata.values[key] > self.app.appdata.high:
                    self.app.appdata.high = self.app.appdata.values[key]
                if self.app.appdata.values[key] < self.app.appdata.low:
                    self.app.appdata.low = self.app.appdata.values[key]

            self.centralWidget().map.update()
            self.centralWidget().reaction_list.update()

    def fva(self):
        res = matlabcall()
        print("yeah", res)