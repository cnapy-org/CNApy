import re
from typing import Tuple
from cnadata import CnaData
import os
from shutil import copyfile
import json
from zipfile import ZipFile
from ast import literal_eval as make_tuple
from tempfile import TemporaryDirectory
from PySide2.QtCore import Slot
from PySide2.QtWidgets import (QGraphicsItem,
                               QAction, QApplication, QFileDialog, QMainWindow)
from PySide2.QtGui import QColor
from PySide2.QtSvg import QGraphicsSvgItem
from gui_elements.centralwidget import CentralWidget

from gui_elements.about_dialog import AboutDialog
from gui_elements.clipboard_calculator import ClipboardCalculator

from legacy import matlab_CNAcomputeEFM

import cobra


class MainWindow(QMainWindow):
    """The cnapy main window"""

    def __init__(self, appdata: CnaData):
        QMainWindow.__init__(self)
        self.setWindowTitle("cnapy")
        self.appdata = appdata

        central_widget = CentralWidget(self)
        self.setCentralWidget(central_widget)

        self.menu = self.menuBar()
        self.file_menu = self.menu.addMenu("&Project")

        new_project_action = QAction("New project", self)
        self.file_menu.addAction(new_project_action)
        new_project_action.triggered.connect(self.new_project)

        open_project_action = QAction("&Open project ...", self)
        self.file_menu.addAction(open_project_action)
        open_project_action.triggered.connect(self.open_project)

        # save_project_action = QAction("Save project...", self)
        # self.file_menu.addAction(save_project_action)

        save_as_project_action = QAction("&Save project as...", self)
        self.file_menu.addAction(save_as_project_action)
        save_as_project_action.triggered.connect(self.save_project_as)

        import_sbml_action = QAction("Import SBML...", self)
        self.file_menu.addAction(import_sbml_action)
        import_sbml_action.triggered.connect(self.import_sbml)

        export_sbml_action = QAction("Export SBML...", self)
        self.file_menu.addAction(export_sbml_action)
        export_sbml_action.triggered.connect(self.export_sbml)

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        self.file_menu.addAction(exit_action)
        exit_action.triggered.connect(self.exit_app)

        self.scenario_menu = self.menu.addMenu("Scenario")

        load_scenario_action = QAction("Load scenario...", self)
        self.scenario_menu.addAction(load_scenario_action)
        load_scenario_action.triggered.connect(self.load_scenario)

        save_scenario_action = QAction("Save scenario...", self)
        self.scenario_menu.addAction(save_scenario_action)
        save_scenario_action.triggered.connect(self.save_scenario)

        clear_scenario_action = QAction("Clear scenario", self)
        self.scenario_menu.addAction(clear_scenario_action)
        clear_scenario_action.triggered.connect(self.clear_scenario)

        reset_scenario_action = QAction("Reset scenario", self)
        self.scenario_menu.addAction(reset_scenario_action)
        reset_scenario_action.triggered.connect(self.reset_scenario)

        heaton_action = QAction("Apply heatmap coloring", self)
        heaton_action.triggered.connect(self.set_heaton)
        self.scenario_menu.addAction(heaton_action)

        onoff_action = QAction("Apply On/Off coloring", self)
        onoff_action.triggered.connect(self.set_onoff)
        self.scenario_menu.addAction(onoff_action)

        self.clipboard_menu = self.menu.addMenu("Clipboard")

        copy_to_clipboard_action = QAction("Copy to clipboard", self)
        self.clipboard_menu.addAction(copy_to_clipboard_action)
        copy_to_clipboard_action.triggered.connect(self.copy_to_clipboard)

        paste_clipboard_action = QAction("Paste clipboard", self)
        self.clipboard_menu.addAction(paste_clipboard_action)
        paste_clipboard_action.triggered.connect(self.paste_clipboard)

        clipboard_arithmetics_action = QAction(
            "Clipboard arithmetics ...", self)
        self.clipboard_menu.addAction(clipboard_arithmetics_action)
        clipboard_arithmetics_action.triggered.connect(
            self.clipboard_arithmetics)

        self.map_menu = self.menu.addMenu("Map")

        load_maps_action = QAction("Load map positions...", self)
        self.map_menu.addAction(load_maps_action)
        load_maps_action.triggered.connect(self.load_maps)

        save_maps_action = QAction("Save map positions...", self)
        self.map_menu.addAction(save_maps_action)
        save_maps_action.triggered.connect(self.save_maps)

        self.change_background_action = QAction("Change background", self)
        self.map_menu.addAction(self.change_background_action)
        self.change_background_action.triggered.connect(self.change_background)
        self.change_background_action.setEnabled(False)

        self.inc_bg_size_action = QAction("Increase background size", self)
        self.map_menu.addAction(self.inc_bg_size_action)
        self.inc_bg_size_action.triggered.connect(self.inc_bg_size)
        self.inc_bg_size_action.setEnabled(False)

        self.dec_bg_size_action = QAction("Decrease background size", self)
        self.map_menu.addAction(self.dec_bg_size_action)
        self.dec_bg_size_action.triggered.connect(self.dec_bg_size)
        self.dec_bg_size_action.setEnabled(False)

        self.analysis_menu = self.menu.addMenu("Analysis")

        fba_action = QAction("Flux Balance Analysis (FBA)...", self)
        fba_action.triggered.connect(self.fba)
        self.analysis_menu.addAction(fba_action)

        pfba_action = QAction(
            "Parsimonious Flux Balance Analysis (pFBA)...", self)
        pfba_action.triggered.connect(self.pfba)
        self.analysis_menu.addAction(pfba_action)

        fva_action = QAction("Flux Variability Analysis (FVA)...", self)
        fva_action.triggered.connect(self.fva)
        self.analysis_menu.addAction(fva_action)

        self.efm_menu = self.analysis_menu.addMenu("Elementary Flux Modes")
        efm_action = QAction("Compute Elementary Flux Modes", self)
        efm_action.triggered.connect(self.efm)
        self.efm_menu.addAction(efm_action)

        load_modes_action = QAction("Load modes...", self)
        self.efm_menu.addAction(load_modes_action)
        load_modes_action.triggered.connect(self.load_modes)

        self.save_modes_action = QAction("Save modes...", self)
        self.efm_menu.addAction(self.save_modes_action)
        self.save_modes_action.triggered.connect(self.save_modes)

        phase_plane_action = QAction("Phase plane ...", self)
        phase_plane_action.triggered.connect(self.phase_plane)
        self.analysis_menu.addAction(phase_plane_action)

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
    def phase_plane(self, _checked):

        with self.appdata.project.cobra_py_model as model:
            from cameo import phenotypic_phase_plane
            self.load_scenario_into_model(model)
            # model.reactions.EX_o2_ex.lower_bound = -10
            result = phenotypic_phase_plane(model,
                                            variables=[model.reactions.Growth],
                                            objective=model.reactions.EthEx,
                                            points=10)
            result.plot()


        with self.appdata.project.cobra_py_model as model:
            import matplotlib.pyplot as plt

            import cobra.test
            from cobra.flux_analysis import production_envelope

            self.load_scenario_into_model(model)
            prod_env = production_envelope(
                model, ["Growth"], objective="EthEx", carbon_sources=["GlcUp"])

            print(str(prod_env))

            prod_env.plot(
                kind='line', x='Growth', y='carbon_yield_maximum', yerr=None)

            plt.show()

    @Slot()
    def import_sbml(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.xml")

        self.appdata.project.cobra_py_model = cobra.io.read_sbml_model(
            filename[0])
        self.centralWidget().update()

    @Slot()
    def export_sbml(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.xml")

        cobra.io.write_sbml_model(
            self.appdata.project.cobra_py_model, filename[0])

    @Slot()
    def load_maps(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.maps")

        with open(filename[0], 'r') as fp:
            self.appdata.project.maps = json.load(fp)

        self.centralWidget().recreate_maps()
        self.centralWidget().update()

    @Slot()
    def load_scenario(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.scen")

        with open(filename[0], 'r') as fp:
            values = json.load(fp)
            self.appdata.project.scenario_backup = self.appdata.project.scen_values.copy()
            self.appdata.project.scenario_backup = self.appdata.project.scen_values.clear()
            for i in values:
                self.appdata.project.scen_values[i] = values[i]

            self.appdata.project.comp_values.clear()
        self.centralWidget().update()

    @Slot()
    def load_modes(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.modes")

        with open(filename[0], 'r') as fp:
            self.appdata.project.modes = json.load(fp)
            self.centralWidget().mode_navigator.current = 0
            values = self.appdata.project.modes[0].copy()
            # TODO: should we really overwrite scenario_values
            self.appdata.project.scen_values.clear()
            self.appdata.project.comp_values.clear()
            for i in values:
                self.appdata.project.comp_values[i] = (values[i], values[i])
        self.centralWidget().update()

    @Slot()
    def change_background(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.svg")

        idx = self.centralWidget().tabs.currentIndex()
        if filename[0] != '':
            # try:
            self.appdata.project.maps[idx - 3]["background"] = filename[0]
            print(self.appdata.project.maps[idx - 3]["background"])

            background = QGraphicsSvgItem(
                self.appdata.project.maps[idx - 3]["background"])
            background.setFlags(QGraphicsItem.ItemClipsToShape)
            self.centralWidget().tabs.widget(idx).scene.addItem(background)
            # except:
            # print("could not update background")

            self.centralWidget().update()
            self.centralWidget().tabs.setCurrentIndex(idx)

    @Slot()
    def inc_bg_size(self, _checked):

        idx = self.centralWidget().tabs.currentIndex()
        self.appdata.project.maps[idx - 3]["bg-size"] += 0.2

        self.centralWidget().update()
        self.centralWidget().tabs.setCurrentIndex(idx)

    @Slot()
    def dec_bg_size(self, _checked):

        idx = self.centralWidget().tabs.currentIndex()
        self.appdata.project.maps[idx - 3]["bg-size"] -= 0.2

        self.centralWidget().update()
        self.centralWidget().tabs.setCurrentIndex(idx)

    @Slot()
    def save_maps(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.maps")

        with open(filename[0], 'w') as fp:
            json.dump(self.appdata.project.maps, fp)

    @Slot()
    def save_scenario(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.scen")

        with open(filename[0], 'w') as fp:
            json.dump(self.appdata.project.scen_values, fp)
        self.appdata.project.scenario_backup = self.appdata.project.scen_values.copy()

    @Slot()
    def save_modes(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.modes")

        with open(filename[0], 'w') as fp:
            json.dump(self.appdata.project.modes, fp)

    def reset_scenario(self):
        self.appdata.project.scen_values = self.appdata.project.scenario_backup.copy()
        self.centralWidget().update()

    def clear_scenario(self):
        self.appdata.project.scen_values.clear()
        self.appdata.project.comp_values.clear()
        self.appdata.project.high = 0
        self.appdata.project.low = 0
        self.centralWidget().update()

    @Slot()
    def new_project(self, _checked):
        self.appdata.project.cobra_py_model = cobra.Model()
        self.appdata.project.maps = []
        self.centralWidget().remove_map_tabs()

        self.centralWidget().mode_navigator.clear()
        self.clear_scenario()

    @Slot()
    def open_project(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.cna")

        folder = TemporaryDirectory()

        with ZipFile(filename[0], 'r') as zip_ref:
            zip_ref.extractall(folder.name)

            with open(folder.name+"/maps.json", 'r') as fp:
                self.appdata.project.maps = json.load(fp)

                for m in self.appdata.project.maps:
                    copyfile(folder.name+"/"+m["background"], m["background"])

            self.appdata.project.cobra_py_model = cobra.io.read_sbml_model(
                folder.name + "/model.sbml")

            self.centralWidget().recreate_maps()
            self.centralWidget().mode_navigator.clear()
            self.clear_scenario()

    @Slot()
    def save_project_as(self, _checked):

        print("save_project_as")
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.cna")

        folder = TemporaryDirectory().name

        cobra.io.write_sbml_model(
            self.appdata.project.cobra_py_model, folder + "model.sbml")

        files = {}
        for m in self.appdata.project.maps:
            files[m["background"]] = ""
        count = 1
        for f in files.keys():
            files[f] = ".bg" + str(count) + ".svg"
            count += 1

        for m in self.appdata.project.maps:
            m["background"] = files[m["background"]]

        with open(folder + "maps.json", 'w') as fp:
            json.dump(self.appdata.project.maps, fp)

        with ZipFile(filename[0], 'w') as zipObj:
            zipObj.write(folder + "model.sbml", arcname="model.sbml")
            zipObj.write(folder + "maps.json", arcname="maps.json")
            for key in files.keys():
                zipObj.write(key, arcname=files[key])

    def get_current_view(self):
        idx = self.centralWidget().tabs.currentIndex()
        print(idx)
        if idx == 0:
            view = self.centralWidget().reaction_list
        elif idx > 2:
            view = self.centralWidget().tabs.widget(idx)
        else:
            view = None

        return view

    def on_tab_change(self, idx):
        print("currentTab changed", str(idx))
        if idx >= 3:
            self.change_background_action.setEnabled(True)
            self.inc_bg_size_action.setEnabled(True)
            self.dec_bg_size_action.setEnabled(True)
        else:
            self.change_background_action.setEnabled(False)
            self.inc_bg_size_action.setEnabled(False)
            self.dec_bg_size_action.setEnabled(False)

        self.centralWidget().update_tab(idx)

    def load_scenario_into_model(self, model):
        for x in self.appdata.project.scen_values:
            y = model.reactions.get_by_id(x)
            (vl, vu) = self.appdata.project.scen_values[x]
            y.lower_bound = vl
            y.upper_bound = vu

    def copy_to_clipboard(self):
        print("copy_to_clipboard")
        self.appdata.project.clipboard = self.appdata.project.comp_values.copy()

    def paste_clipboard(self):
        print("paste_clipboard")
        self.appdata.project.comp_values = self.appdata.project.clipboard
        self.centralWidget().update()

    @Slot()
    def clipboard_arithmetics(self, _checked):
        print("clipboard_arithmetics")
        dialog = ClipboardCalculator(self.appdata.project)
        dialog.exec_()
        self.centralWidget().update()

    def fba(self):
        with self.appdata.project.cobra_py_model as model:
            self.load_scenario_into_model(model)

            solution = model.optimize()
            if solution.status == 'optimal':
                soldict = solution.fluxes.to_dict()
                for i in soldict:
                    self.appdata.project.comp_values[i] = (
                        soldict[i], soldict[i])
            else:
                self.appdata.project.comp_values.clear()
            self.centralWidget().update()

    def pfba(self):
        with self.appdata.project.cobra_py_model as model:
            self.load_scenario_into_model(model)

            solution = cobra.flux_analysis.pfba(model)
            if solution.status == 'optimal':
                soldict = solution.fluxes.to_dict()
                for i in soldict:
                    self.appdata.project.comp_values[i] = (
                        soldict[i], soldict[i])
            else:
                self.appdata.project.comp_values.clear()
            self.centralWidget().update()

    def fva(self):
        from cobra.flux_analysis import flux_variability_analysis

        with self.appdata.project.cobra_py_model as model:
            self.load_scenario_into_model(model)

            solution = flux_variability_analysis(model)

            minimum = solution.minimum.to_dict()
            maximum = solution.maximum.to_dict()
            for i in minimum:
                self.appdata.project.comp_values[i] = (minimum[i], maximum[i])

            self.appdata.project.compute_color_type = 3
            self.centralWidget().update()

    def efm(self):
        self.appdata.project.modes = matlab_CNAcomputeEFM(
            self.appdata.project.cobra_py_model)
        self.centralWidget().update()

    def set_onoff(self):
        idx = self.centralWidget().tabs.currentIndex()
        if idx == 0:
            view = self.centralWidget().reaction_list
            root = view.reaction_list.invisibleRootItem()
            child_count = root.childCount()
            for i in range(child_count):
                item = root.child(i)
                key = item.text(0)
                if key in self.appdata.project.scen_values:
                    value = self.appdata.project.scen_values[key]
                    color = self.compute_color_onoff(value)
                    item.setBackground(2, color)
                elif key in self.appdata.project.comp_values:
                    value = self.appdata.project.comp_values[key]
                    color = self.compute_color_onoff(value)
                    item.setBackground(2, color)

        elif idx > 2:
            view = self.centralWidget().tabs.widget(idx)
            for key in self.appdata.project.maps[idx-3]["boxes"]:
                if key in self.appdata.project.scen_values:
                    value = self.appdata.project.scen_values[key]
                    color = self.compute_color_onoff(value)
                    view.reaction_boxes[key].set_color(color)
                elif key in self.appdata.project.comp_values:
                    value = self.appdata.project.comp_values[key]
                    color = self.compute_color_onoff(value)
                    view.reaction_boxes[key].set_color(color)

    def compute_color_onoff(self, value: Tuple[float, float]):
        (vl, vh) = value
        if vl < 0.0:
            return QColor.fromRgb(0, 255, 0)
        elif vh > 0.0:
            return QColor.fromRgb(0, 255, 0)
        else:
            return QColor.fromRgb(255, 0, 0)

    def set_heaton(self):
        idx = self.centralWidget().tabs.currentIndex()
        if idx == 0:
            view = self.centralWidget().reaction_list
            root = view.reaction_list.invisibleRootItem()
            child_count = root.childCount()
            for i in range(child_count):
                item = root.child(i)
                key = item.text(0)
                if key in self.appdata.project.scen_values:
                    value = self.appdata.project.scen_values[key]
                    color = self.compute_color_heat(value)
                    item.setBackground(2, color)
                elif key in self.appdata.project.comp_values:
                    value = self.appdata.project.comp_values[key]
                    color = self.compute_color_heat(value)
                    item.setBackground(2, color)
        elif idx > 2:
            view = self.centralWidget().tabs.widget(idx)
            for key in self.appdata.project.maps[idx-3]["boxes"]:
                if key in self.appdata.project.scen_values:
                    value = self.appdata.project.scen_values[key]
                    color = self.compute_color_heat(value)
                    view.reaction_boxes[key].set_color(color)
                elif key in self.appdata.project.comp_values:
                    value = self.appdata.project.comp_values[key]
                    color = self.compute_color_heat(value)
                    view.reaction_boxes[key].set_color(color)

    def compute_color_heat(self, value: Tuple[float, float]):
        (low, high) = self.high_and_low()

        (vl, vh) = value
        mean = my_mean((vl, vh))
        if mean > 0.0:
            if high == 0.0:
                h = 255
            else:
                h = mean * 255 / high
            return QColor.fromRgb(255-h, 255, 255-h)
        else:
            if low == 0.0:
                h = 255
            else:
                h = mean * 255 / low
            return QColor.fromRgb(255, 255 - h, 255 - h)

    def high_and_low(self):
        low = 0
        high = 0
        for key in self.appdata.project.scen_values.keys():
            mean = my_mean(self.appdata.project.scen_values[key])
            if mean < low:
                low = mean
            if mean > high:
                high = mean
        for key in self.appdata.project.comp_values.keys():
            mean = my_mean(self.appdata.project.comp_values[key])
            if mean < low:
                low = mean
            if mean > high:
                high = mean
        return (low, high)


def my_mean(value):
    if isinstance(value, float):
        return value
    else:
        (vl, vh) = value
        return (vl+vh)/2
