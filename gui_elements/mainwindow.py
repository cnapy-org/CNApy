import os
from shutil import copyfile
import json
from zipfile import ZipFile
from tempfile import TemporaryDirectory
from PySide2.QtCore import Slot
from PySide2.QtWidgets import (QGraphicsItem,
                               QAction, QApplication, QFileDialog, QMainWindow)
from PySide2.QtSvg import QGraphicsSvgItem
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

        load_maps_action = QAction("Load maps...", self)
        self.file_menu.addAction(load_maps_action)
        load_maps_action.triggered.connect(self.load_maps)

        save_maps_action = QAction("Save maps...", self)
        self.file_menu.addAction(save_maps_action)
        save_maps_action.triggered.connect(self.save_maps)

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        self.file_menu.addAction(exit_action)
        exit_action.triggered.connect(self.exit_app)

        # self.find_menu = self.menu.addMenu("Find")
        # find_reaction_action = QAction("Find reaction...", self)
        # self.find_menu.addAction(find_reaction_action)

        self.scenario_menu = self.menu.addMenu("Scenario")

        load_scenario_action = QAction("Load scenario...", self)
        self.scenario_menu.addAction(load_scenario_action)
        load_scenario_action.triggered.connect(self.load_scenario)

        save_scenario_action = QAction("Save scenario...", self)
        self.scenario_menu.addAction(save_scenario_action)
        save_scenario_action.triggered.connect(self.save_scenario)

        self.modes_menu = self.menu.addMenu("Modes")

        load_modes_action = QAction("Load modes...", self)
        self.modes_menu.addAction(load_modes_action)
        load_modes_action.triggered.connect(self.load_modes)

        save_modes_action = QAction("Save modes...", self)
        self.modes_menu.addAction(save_modes_action)
        save_modes_action.triggered.connect(self.save_modes)

        self.map_menu = self.menu.addMenu("Map")
        self.map_menu.setEnabled(False)

        change_background_action = QAction("Change background", self)
        self.map_menu.addAction(change_background_action)
        change_background_action.triggered.connect(self.change_background)

        change_bg_size_action = QAction("Change background size", self)
        self.map_menu.addAction(change_bg_size_action)
        change_bg_size_action.triggered.connect(self.change_bg_size)

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

        self.centralWidget().tabs.currentChanged.connect(self.on_tab_change)

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
        self.centralWidget().update()

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
        self.centralWidget().update()

    @Slot()
    def load_scenario(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.scen")

        with open(filename[0], 'r') as fp:
            values = json.load(fp)
            self.app.appdata.set_scen(values)
        self.centralWidget().update()

    @Slot()
    def load_modes(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.modes")

        with open(filename[0], 'r') as fp:
            self.app.appdata.modes = json.load(fp)
            self.centralWidget().modenavigator.current = 0
            values = self.app.appdata.modes[0].copy()
            self.app.appdata.set_scen(values)
        self.centralWidget().update()

    @Slot()
    def change_background(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.svg")

        idx = self.centralWidget().tabs.currentIndex()
        if filename[0] != '':
            # try:
            self.app.appdata.maps[idx - 3]["background"] = filename[0]
            print(self.app.appdata.maps[idx - 3]["background"])

            background = QGraphicsSvgItem(
                self.app.appdata.maps[idx - 3]["background"])
            background.setFlags(QGraphicsItem.ItemClipsToShape)
            self.centralWidget().tabs.widget(idx).scene.addItem(background)
            # except:
            # print("could not update background")

            self.centralWidget().update()
            self.centralWidget().tabs.setCurrentIndex(idx)

    @Slot()
    def change_bg_size(self, _checked):
        # dialog = QFileDialog(self)
        # filename: str = dialog.getOpenFileName(
        #     dir=os.getcwd(), filter="*.svg")

        idx = self.centralWidget().tabs.currentIndex()
        self.app.appdata.maps[idx - 3]["bg-size"] = 3

        # background = QGraphicsSvgItem(
        #     self.app.appdata.maps[idx - 3]["background"])
        # background.setFlags(QGraphicsItem.ItemClipsToShape)
        # background.setScale(self.app.appdata.maps[idx - 3]["bg-size"])
        # self.centralWidget().tabs.widget(idx).scene.addItem(background)

        self.centralWidget().update()
        self.centralWidget().tabs.setCurrentIndex(idx)

    @Slot()
    def save_maps(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.maps")

        with open(filename[0], 'w') as fp:
            json.dump(self.app.appdata.maps, fp)

    @Slot()
    def save_scenario(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.scen")

        with open(filename[0], 'w') as fp:
            json.dump(self.app.appdata.values, fp)

    @Slot()
    def save_modes(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.modes")

        with open(filename[0], 'w') as fp:
            json.dump(self.app.appdata.modes, fp)

    @Slot()
    def new_project(self, _checked):
        self.app.appdata.cobra_py_model = cobra.Model()
        self.app.appdata.maps = []

        self.centralWidget().update()

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

                for m in self.app.appdata.maps:
                    copyfile(folder.name+"/"+m["background"], m["background"])

            self.app.appdata.cobra_py_model = cobra.io.read_sbml_model(
                folder.name+"/model.sbml")
            self.centralWidget().update()

    @Slot()
    def save_project_as(self, _checked):

        print("save_project_as")
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.cna")

        folder = TemporaryDirectory().name

        cobra.io.write_sbml_model(
            self.app.appdata.cobra_py_model, folder + "model.sbml")

        files = {}
        for m in self.app.appdata.maps:
            files[m["background"]] = ""
        count = 1
        for f in files.keys():
            files[f] = ".bg" + str(count) + ".svg"
            count += 1

        for m in self.app.appdata.maps:
            m["background"] = files[m["background"]]

        with open(folder + "maps.json", 'w') as fp:
            json.dump(self.app.appdata.maps, fp)

        with ZipFile(filename[0], 'w') as zipObj:
            zipObj.write(folder + "model.sbml", arcname="model.sbml")
            zipObj.write(folder + "maps.json", arcname="maps.json")
            for key in files.keys():
                zipObj.write(key, arcname=files[key])

    def on_tab_change(self, idx):
        print("currentTab changed", str(idx))
        if idx >= 3:
            self.map_menu.setEnabled(True)
        else:
            self.map_menu.setEnabled(False)

    def fba(self):
        solution = self.app.appdata.cobra_py_model.optimize()
        if solution.status == 'optimal':
            self.app.appdata.high = 0.0
            self.app.appdata.low = 0.0
            self.app.appdata.set_scen(solution.fluxes)

            self.centralWidget().update_maps()
            self.centralWidget().reaction_list.update()

    def fva(self):
        res = matlabcall()
        print("yeah", res)
