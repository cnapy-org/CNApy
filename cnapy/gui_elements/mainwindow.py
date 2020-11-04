import json
import os
import sys
import traceback
from shutil import copyfile
from tempfile import TemporaryDirectory
from typing import Tuple
from zipfile import ZipFile

import cobra
from qtpy.QtCore import Slot
from qtpy.QtGui import QColor, QIcon
from qtpy.QtSvg import QGraphicsSvgItem
from qtpy.QtWidgets import (QAction, QApplication, QFileDialog, QGraphicsItem,
                            QMainWindow, QMessageBox, QToolBar)

from cnapy.cnadata import CnaData
from cnapy.gui_elements.about_dialog import AboutDialog
from cnapy.gui_elements.centralwidget import CentralWidget
from cnapy.gui_elements.clipboard_calculator import ClipboardCalculator
from cnapy.gui_elements.config_dialog import ConfigDialog
from cnapy.gui_elements.efm_dialog import EFMDialog
from cnapy.gui_elements.mcs_dialog import MCSDialog
from cnapy.gui_elements.phase_plane_dialog import PhasePlaneDialog
from cnapy.gui_elements.yield_optimization_dialog import YieldOptimizationDialog


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

        new_project_action = QAction("&New project", self)
        new_project_action.setShortcut("Ctrl+N")
        self.file_menu.addAction(new_project_action)
        new_project_action.triggered.connect(self.new_project)

        open_project_action = QAction("&Open project ...", self)
        open_project_action.setShortcut("Ctrl+O")
        self.file_menu.addAction(open_project_action)
        open_project_action.triggered.connect(self.open_project)

        self.save_project_action = QAction("&Save project...", self)
        self.save_project_action.setShortcut("Ctrl+S")
        self.file_menu.addAction(self.save_project_action)
        self.save_project_action.triggered.connect(self.save_project)

        save_as_project_action = QAction("&Save project as...", self)
        save_as_project_action.setShortcut("Ctrl+Shift+S")
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
        clear_scenario_action.setIcon(QIcon.fromTheme("edit-clear"))
        self.scenario_menu.addAction(clear_scenario_action)
        clear_scenario_action.triggered.connect(self.clear_scenario)

        reset_scenario_action = QAction("Reset scenario", self)
        reset_scenario_action.setIcon(QIcon.fromTheme("edit-undo"))
        self.scenario_menu.addAction(reset_scenario_action)
        reset_scenario_action.triggered.connect(self.reset_scenario)

        add_values_to_scenario_action = QAction(
            "Add all values to scenario", self)
        self.scenario_menu.addAction(add_values_to_scenario_action)
        add_values_to_scenario_action.triggered.connect(
            self.add_values_to_scenario)

        set_model_bounds_to_scenario_action = QAction(
            "Set the model bounds to the current scenario values", self)
        self.scenario_menu.addAction(set_model_bounds_to_scenario_action)
        set_model_bounds_to_scenario_action.triggered.connect(
            self.set_model_bounds_to_scenario)

        heaton_action = QAction("Apply heatmap coloring", self)
        heaton_action.setIcon(QIcon.fromTheme("weather-clear"))
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

        show_model_bounds_action = QAction("Show model bounds", self)
        self.analysis_menu.addAction(show_model_bounds_action)
        show_model_bounds_action.triggered.connect(self.show_model_bounds)

        fba_action = QAction("Flux Balance Analysis (FBA)", self)
        fba_action.triggered.connect(self.fba)
        self.analysis_menu.addAction(fba_action)

        pfba_action = QAction(
            "Parsimonious Flux Balance Analysis (pFBA)", self)
        pfba_action.triggered.connect(self.pfba)
        self.analysis_menu.addAction(pfba_action)

        fva_action = QAction("Flux Variability Analysis (FVA)", self)
        fva_action.triggered.connect(self.fva)
        self.analysis_menu.addAction(fva_action)

        self.efm_menu = self.analysis_menu.addMenu("Elementary Flux Modes")
        self.efm_action = QAction("Compute Elementary Flux Modes ...", self)
        self.efm_action.triggered.connect(self.efm)
        self.efm_menu.addAction(self.efm_action)

        load_modes_action = QAction("Load modes...", self)
        self.efm_menu.addAction(load_modes_action)
        load_modes_action.triggered.connect(self.load_modes)

        self.save_modes_action = QAction("Save modes...", self)
        self.efm_menu.addAction(self.save_modes_action)
        self.save_modes_action.triggered.connect(self.save_modes)

        self.mcs_action = QAction("Minimal Cut Sets ...", self)
        self.mcs_action.triggered.connect(self.mcs)
        self.analysis_menu.addAction(self.mcs_action)

        phase_plane_action = QAction("Phase plane analysis ...", self)
        phase_plane_action.triggered.connect(self.phase_plane)
        self.analysis_menu.addAction(phase_plane_action)

        yield_optimization_action = QAction("Yield optimization ...", self)
        yield_optimization_action.triggered.connect(self.optimize_yield)
        self.analysis_menu.addAction(yield_optimization_action)

        self.help_menu = self.menu.addMenu("Help")

        config_action = QAction("Configure CNApy ...", self)
        self.help_menu.addAction(config_action)
        config_action.triggered.connect(self.show_config_dialog)

        about_action = QAction("About cnapy...", self)
        self.help_menu.addAction(about_action)
        about_action.triggered.connect(self.show_about)

        update_action = QAction("Default Coloring", self)
        update_action.triggered.connect(central_widget.update)

        set_default_scenario_action = QAction("Default scenario", self)
        set_default_scenario_action.triggered.connect(
            self.set_default_scenario)

        self.tool_bar = QToolBar()
        self.tool_bar.addAction(clear_scenario_action)
        self.tool_bar.addAction(reset_scenario_action)
        self.tool_bar.addAction(set_default_scenario_action)
        self.tool_bar.addAction(heaton_action)
        self.tool_bar.addAction(onoff_action)
        self.tool_bar.addAction(update_action)
        self.addToolBar(self.tool_bar)

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
        dialog = PhasePlaneDialog(self.appdata)
        dialog.exec_()

    @Slot()
    def optimize_yield(self, _checked):
        dialog = YieldOptimizationDialog(self.appdata)
        dialog.exec_()

    @Slot()
    def show_config_dialog(self):
        dialog = ConfigDialog(self.appdata)
        dialog.exec_()

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
            self.appdata.project.scen_values.clear()
            for i in values:
                self.appdata.project.scen_values[i] = values[i]

            self.appdata.project.scenario_backup = self.appdata.project.scen_values.copy()
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
        self.appdata.project.comp_values.clear()
        self.appdata.project.scen_values = self.appdata.project.scenario_backup.copy()
        self.centralWidget().update()

    def clear_scenario(self):
        self.appdata.project.scen_values.clear()
        self.appdata.project.comp_values.clear()
        self.appdata.project.high = 0
        self.appdata.project.low = 0
        self.centralWidget().update()

    def set_default_scenario(self):
        self.appdata.project.comp_values.clear()
        for r in self.appdata.project.cobra_py_model.reactions:
            if 'cnapy-default' in r.annotation.keys():
                self.centralWidget().update_reaction_value(
                    r.id, r.annotation['cnapy-default'])
        self.centralWidget().reaction_list.update()

    @Slot()
    def new_project(self, _checked):
        self.appdata.project.cobra_py_model = cobra.Model()
        self.appdata.project.maps = []
        self.centralWidget().remove_map_tabs()

        self.centralWidget().mode_navigator.clear()
        self.clear_scenario()

        self.appdata.project.name = "Unnamed project"
        self.save_project_action.setEnabled(False)

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
            for r in self.appdata.project.cobra_py_model.reactions:
                if 'cnapy-default' in r.annotation.keys():
                    self.centralWidget().update_reaction_value(
                        r.id, r.annotation['cnapy-default'])
            self.appdata.project.name = filename[0]
            print(self.appdata.project.name)
            self.save_project_action.setEnabled(True)
            self.centralWidget().reaction_list.update()

    @Slot()
    def save_project(self, _checked):

        filename: str = self.appdata.project.name
        print(self.appdata.project.name)
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

        with ZipFile(filename, 'w') as zipObj:
            zipObj.write(folder + "model.sbml", arcname="model.sbml")
            zipObj.write(folder + "maps.json", arcname="maps.json")
            for key in files.keys():
                zipObj.write(key, arcname=files[key])

    @Slot()
    def save_project_as(self, _checked):

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
            self.appdata.project.name = filename[0]
            self.save_project_action.setEnabled(True)

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

    def add_values_to_scenario(self):
        for key in self.appdata.project.comp_values.keys():
            self.appdata.project.scen_values[key] = self.appdata.project.comp_values[key]
        self.centralWidget().update()

    def set_model_bounds_to_scenario(self):
        for reaction in self.appdata.project.cobra_py_model.reactions:
            if reaction.id in self.appdata.project.scen_values:
                (vl, vu) = self.appdata.project.scen_values[reaction.id]
                reaction.lower_bound = vl
                reaction.upper_bound = vu
        self.centralWidget().update()

    def fba(self):
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            solution = model.optimize()
            if solution.status == 'optimal':
                soldict = solution.fluxes.to_dict()
                for i in soldict:
                    self.appdata.project.comp_values[i] = (
                        soldict[i], soldict[i])
            elif solution.status == 'infeasible':
                QMessageBox.information(
                    self, 'No solution!', 'No solution the scenario is infeasible!')
                self.appdata.project.comp_values.clear()
            else:
                QMessageBox.information(
                    self, 'No solution!', solution.status)
                self.appdata.project.comp_values.clear()
            self.centralWidget().update()

    def fba_optimize_reaction(self, reaction):
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            for r in self.appdata.project.cobra_py_model.reactions:
                if r.id == reaction:
                    r.objective_coefficient = 1
                else:
                    r.objective_coefficient = 0
            solution = model.optimize()
            if solution.status == 'optimal':
                soldict = solution.fluxes.to_dict()
                for i in soldict:
                    self.appdata.project.comp_values[i] = (
                        soldict[i], soldict[i])
            elif solution.status == 'infeasible':
                QMessageBox.information(
                    self, 'No solution!', 'No solution the scenario is infeasible!')
                self.appdata.project.comp_values.clear()
            else:
                QMessageBox.information(
                    self, 'No solution!', solution.status)
                self.appdata.project.comp_values.clear()
            self.centralWidget().update()

    def pfba(self):
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            try:
                solution = cobra.flux_analysis.pfba(model)
            except cobra.exceptions.Infeasible:
                QMessageBox.information(
                    self, 'No solution', 'The scenario is infeasible')
            except Exception as e:
                traceback.print_exception(*sys.exc_info())
                QMessageBox.warning(
                    self, 'Unknown exception occured!', 'Please report the problem to:\n\nhttps://github.com/ARB-Lab/CNApy/issues')
            else:
                if solution.status == 'optimal':
                    soldict = solution.fluxes.to_dict()
                    for i in soldict:
                        self.appdata.project.comp_values[i] = (
                            soldict[i], soldict[i])
                else:
                    QMessageBox.information(
                        self, 'No solution!', solution.status)
                    self.appdata.project.comp_values.clear()
            finally:
                self.centralWidget().update()

    def show_model_bounds(self):
        for reaction in self.appdata.project.cobra_py_model.reactions:
            self.appdata.project.comp_values[reaction.id] = (
                reaction.lower_bound, reaction.upper_bound)
        self.centralWidget().update()

    def fva(self):
        from cobra.flux_analysis import flux_variability_analysis

        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            try:
                solution = flux_variability_analysis(model)
            except cobra.exceptions.Infeasible:
                QMessageBox.information(
                    self, 'No solution', 'The scenario is infeasible')
            except Exception:
                traceback.print_exception(*sys.exc_info())
                QMessageBox.warning(
                    self, 'Unknown exception occured!', 'Please report the problem to:\n\nhttps://github.com/ARB-Lab/CNApy/issues')
            else:
                minimum = solution.minimum.to_dict()
                maximum = solution.maximum.to_dict()
                for i in minimum:
                    self.appdata.project.comp_values[i] = (
                        minimum[i], maximum[i])

                self.appdata.project.compute_color_type = 3
            finally:
                self.centralWidget().update()

    def efm(self):
        self.efm_dialog = EFMDialog(
            self.appdata, self.centralWidget())
        self.efm_dialog.open()

    def mcs(self):
        self.mcs_dialog = MCSDialog(
            self.appdata, self.centralWidget())
        self.mcs_dialog.open()

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
        vl = round(vl, self.appdata.rounding)
        vh = round(vh, self.appdata.rounding)
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
        vl = round(vl, self.appdata.rounding)
        vh = round(vh, self.appdata.rounding)
        mean = my_mean((vl, vh))
        if mean > 0.0:
            if high == 0.0:
                h = 255
            else:
                h = mean * 255 / high
            return QColor.fromRgb(255-h, 255, 255 - h)
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
