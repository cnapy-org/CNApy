import io
import json
import os
import traceback
from tempfile import TemporaryDirectory
from typing import Tuple
from zipfile import ZipFile
from cnapy.flux_vector_container import FluxVectorContainer
from cnapy.utils import Worker

import cobra
import numpy as np

from cobra.manipulation.delete import prune_unused_metabolites
from qtpy.QtCore import QFileInfo, Qt, Slot, QRunnable, QObject, Signal
from qtpy.QtGui import QColor, QIcon, QPalette
from qtpy.QtSvg import QGraphicsSvgItem
from qtpy.QtWidgets import (QAction, QApplication, QFileDialog, QGraphicsItem,
                            QMainWindow, QMessageBox, QToolBar)

from cnapy.cnadata import CnaData, ProjectData
from cnapy.gui_elements.about_dialog import AboutDialog
from cnapy.gui_elements.centralwidget import CentralWidget
from cnapy.gui_elements.clipboard_calculator import ClipboardCalculator
from cnapy.gui_elements.config_dialog import ConfigDialog
from cnapy.gui_elements.config_cobrapy_dialog import ConfigCobrapyDialog
from cnapy.gui_elements.description_dialog import DescriptionDialog
from cnapy.gui_elements.efm_dialog import EFMDialog
from cnapy.gui_elements.efmtool_dialog import EFMtoolDialog
from cnapy.gui_elements.map_view import MapView
from cnapy.gui_elements.mcs_dialog import MCSDialog
from cnapy.gui_elements.phase_plane_dialog import PhasePlaneDialog
from cnapy.gui_elements.rename_map_dialog import RenameMapDialog
from cnapy.gui_elements.yield_optimization_dialog import \
    YieldOptimizationDialog
from cnapy.legacy import try_cna
from cnapy.core import load_values_into_model, fva_computation


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

        new_project_from_sbml_action = QAction(
            "New project from SBML ...", self)
        self.file_menu.addAction(new_project_from_sbml_action)
        new_project_from_sbml_action.triggered.connect(
            self.new_project_from_sbml)

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

        export_sbml_action = QAction("Export SBML...", self)
        self.file_menu.addAction(export_sbml_action)
        export_sbml_action.triggered.connect(self.export_sbml)

        description_action = QAction("Project description ...", self)
        self.file_menu.addAction(description_action)
        description_action.triggered.connect(self.show_description_dialog)

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        self.file_menu.addAction(exit_action)
        exit_action.triggered.connect(self.exit_app)

        self.scenario_menu = self.menu.addMenu("Scenario")

        load_default_scenario_action = QAction("Apply default scenario", self)
        self.scenario_menu.addAction(load_default_scenario_action)
        load_default_scenario_action.setIcon(QIcon(":/icons/d-font.png"))
        load_default_scenario_action.triggered.connect(
            self.load_default_scenario)

        load_scenario_action = QAction("Load scenario ...", self)
        self.scenario_menu.addAction(load_scenario_action)
        load_scenario_action.triggered.connect(self.load_scenario)

        save_scenario_action = QAction("Save scenario...", self)
        self.scenario_menu.addAction(save_scenario_action)
        save_scenario_action.triggered.connect(self.save_scenario)

        clear_scenario_action = QAction("Clear scenario", self)
        clear_scenario_action.setIcon(QIcon(":/icons/clear.png"))
        self.scenario_menu.addAction(clear_scenario_action)
        clear_scenario_action.triggered.connect(self.clear_scenario)

        undo_scenario_action = QAction("Undo scenario edit", self)
        undo_scenario_action.setIcon(QIcon(":/icons/undo.png"))
        self.scenario_menu.addAction(undo_scenario_action)
        undo_scenario_action.triggered.connect(self.undo_scenario_edit)

        redo_scenario_action = QAction("Redo scenario edit", self)
        redo_scenario_action.setIcon(QIcon(":/icons/redo.png"))
        self.scenario_menu.addAction(redo_scenario_action)
        redo_scenario_action.triggered.connect(self.redo_scenario_edit)

        add_values_to_scenario_action = QAction(
            "Add all values to scenario", self)
        self.scenario_menu.addAction(add_values_to_scenario_action)
        add_values_to_scenario_action.triggered.connect(
            self.add_values_to_scenario)

        show_model_bounds_action = QAction("Show model bounds", self)
        self.scenario_menu.addAction(show_model_bounds_action)
        show_model_bounds_action.triggered.connect(self.show_model_bounds)

        set_model_bounds_to_scenario_action = QAction(
            "Set the model bounds as scenario values", self)
        self.scenario_menu.addAction(set_model_bounds_to_scenario_action)
        set_model_bounds_to_scenario_action.triggered.connect(
            self.set_model_bounds_to_scenario)

        set_scenario_to_default_scenario_action = QAction(
            "Set current scenario as default scenario", self)
        self.scenario_menu.addAction(set_scenario_to_default_scenario_action)
        set_scenario_to_default_scenario_action.triggered.connect(
            self.set_scenario_to_default_scenario)

        self.scenario_menu.addSeparator()

        heaton_action = QAction("Apply heatmap coloring", self)
        heaton_action.setIcon(QIcon(":/icons/heat.png"))
        heaton_action.triggered.connect(self.set_heaton)
        self.scenario_menu.addAction(heaton_action)

        onoff_action = QAction("Apply On/Off coloring", self)
        onoff_action.setIcon(QIcon(":/icons/onoff.png"))
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

        add_map_action = QAction("Add new map", self)
        self.map_menu.addAction(add_map_action)
        add_map_action.triggered.connect(central_widget.add_map)

        load_maps_action = QAction("Load reaction box positions...", self)
        self.map_menu.addAction(load_maps_action)
        load_maps_action.triggered.connect(self.load_box_positions)

        self.save_box_positions_action = QAction(
            "Save reaction box positions...", self)
        self.map_menu.addAction(self.save_box_positions_action)
        self.save_box_positions_action.triggered.connect(
            self.save_box_positions)
        self.save_box_positions_action.setEnabled(False)

        self.change_map_name_action = QAction("Change map name", self)
        self.map_menu.addAction(self.change_map_name_action)
        self.change_map_name_action.triggered.connect(self.change_map_name)
        self.change_map_name_action.setEnabled(False)

        self.change_background_action = QAction("Change map background", self)
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

        self.analysis_menu.addSeparator()

        self.efm_menu = self.analysis_menu.addMenu("Elementary Flux Modes")
        self.efm_action = QAction(
            "Compute Elementary Flux Modes via CNA ...", self)
        self.efm_action.triggered.connect(self.efm)
        self.efm_menu.addAction(self.efm_action)

        self.efmtool_action = QAction(
            "Compute Elementary Flux Modes via EFMtool ...", self)
        self.efmtool_action.triggered.connect(self.efmtool)
        self.efm_menu.addAction(self.efmtool_action)

        load_modes_action = QAction("Load modes...", self)
        self.efm_menu.addAction(load_modes_action)
        load_modes_action.triggered.connect(self.load_modes)

        self.save_modes_action = QAction("Save modes...", self)
        self.efm_menu.addAction(self.save_modes_action)
        self.save_modes_action.triggered.connect(self.save_modes)

        self.mcs_action = QAction("Minimal Cut Sets via CNA ...", self)
        self.mcs_action.triggered.connect(self.mcs)
        self.analysis_menu.addAction(self.mcs_action)

        phase_plane_action = QAction("Phase plane analysis ...", self)
        phase_plane_action.triggered.connect(self.phase_plane)
        self.analysis_menu.addAction(phase_plane_action)

        self.yield_optimization_action = QAction(
            "Yield optimization via CNA ...", self)
        self.yield_optimization_action.triggered.connect(self.optimize_yield)
        self.analysis_menu.addAction(self.yield_optimization_action)

        self.analysis_menu.addSeparator()

        show_model_stats_action = QAction("Show model stats", self)
        self.analysis_menu.addAction(show_model_stats_action)
        show_model_stats_action.triggered.connect(
            self.execute_print_model_stats)

        net_conversion_action = QAction(
            "Net conversion of external metabolites", self)
        self.analysis_menu.addAction(net_conversion_action)
        net_conversion_action.triggered.connect(
            self.show_net_conversion)

        show_optimization_function_action = QAction(
            "Show optimization function", self)
        self.analysis_menu.addAction(show_optimization_function_action)
        show_optimization_function_action.triggered.connect(
            self.show_optimization_function)

        self.config_menu = self.menu.addMenu("Config")

        config_action = QAction("Configure CNApy ...", self)
        self.config_menu.addAction(config_action)
        config_action.triggered.connect(self.show_config_dialog)

        config_action = QAction("Configure COBRApy ...", self)
        self.config_menu.addAction(config_action)
        config_action.triggered.connect(self.show_config_cobrapy_dialog)

        about_action = QAction("About cnapy...", self)
        self.config_menu.addAction(about_action)
        about_action.triggered.connect(self.show_about)

        update_action = QAction("Default Coloring", self)
        update_action.setIcon(QIcon(":/icons/default-color.png"))
        update_action.triggered.connect(central_widget.update)

        zoom_in_action = QAction("Zoom in Map", self)
        zoom_in_action.setIcon(QIcon(":/icons/zoom-in.png"))
        zoom_in_action.triggered.connect(self.zoom_in)

        zoom_out_action = QAction("Zoom out Map", self)
        zoom_out_action.setIcon(QIcon(":/icons/zoom-out.png"))
        zoom_out_action.triggered.connect(self.zoom_out)

        self.set_current_filename("Untitled project")

        self.tool_bar = QToolBar()
        self.tool_bar.addAction(clear_scenario_action)
        self.tool_bar.addAction(undo_scenario_action)
        self.tool_bar.addAction(redo_scenario_action)
        self.tool_bar.addAction(heaton_action)
        self.tool_bar.addAction(onoff_action)
        self.tool_bar.addAction(update_action)
        self.tool_bar.addAction(zoom_in_action)
        self.tool_bar.addAction(zoom_out_action)
        self.addToolBar(self.tool_bar)

        self.centralWidget().map_tabs.currentChanged.connect(self.on_tab_change)

    def unsaved_changes(self):
        if not self.appdata.unsaved:
            self.appdata.unsaved = True
            self.save_project_action.setEnabled(True)
            if len(self.appdata.project.name) == 0:
                shown_name = "Untitled project"
            else:
                shown_name = QFileInfo(self.appdata.project.name).fileName()

            self.setWindowTitle("CNApy - " + shown_name + ' - unsaved changes')

    def nounsaved_changes(self):
        if self.appdata.unsaved:
            self.appdata.unsaved = False
            self.save_project_action.setEnabled(False)
            if len(self.appdata.project.name) == 0:
                shown_name = "Untitled project"
            else:
                shown_name = QFileInfo(self.appdata.project.name).fileName()

            self.setWindowTitle("CNApy - " + shown_name)

    def disable_enable_dependent_actions(self):

        self.efm_action.setEnabled(False)
        self.mcs_action.setEnabled(False)
        self.yield_optimization_action.setEnabled(False)

        if self.appdata.selected_engine == "matlab" and self.appdata.is_matlab_ready():
            if try_cna(self.appdata.matlab_engine, self.appdata.cna_path):
                self.efm_action.setEnabled(True)
                self.mcs_action.setEnabled(True)
                self.yield_optimization_action.setEnabled(True)

        elif self.appdata.selected_engine == "octave" and self.appdata.is_octave_ready():
            if try_cna(self.appdata.octave_engine, self.appdata.cna_path):
                self.efm_action.setEnabled(True)
                self.mcs_action.setEnabled(True)
                self.yield_optimization_action.setEnabled(True)

    @Slot()
    def exit_app(self):
        QApplication.quit()

    def set_current_filename(self, filename):
        self.appdata.project.name = filename

        if len(self.appdata.project.name) == 0:
            shown_name = "Untitled project"
        else:
            shown_name = QFileInfo(self.appdata.project.name).fileName()

        self.setWindowTitle("CNApy - " + shown_name)

    @Slot()
    def show_about(self):
        dialog = AboutDialog()
        dialog.exec_()

    @Slot()
    def phase_plane(self):
        dialog = PhasePlaneDialog(self.appdata)
        dialog.exec_()

    @Slot()
    def optimize_yield(self):
        dialog = YieldOptimizationDialog(self.appdata, self.centralWidget())
        dialog.exec_()

    @Slot()
    def show_config_dialog(self):
        dialog = ConfigDialog(self.appdata)
        dialog.exec_()

    @Slot()
    def show_config_cobrapy_dialog(self):
        dialog = ConfigCobrapyDialog(self.appdata)
        dialog.exec_()

    @Slot()
    def show_description_dialog(self):
        dialog = DescriptionDialog(self.appdata)
        dialog.exec_()

    @Slot()
    def export_sbml(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            directory=self.appdata.work_directory, filter="*.xml *.sbml")[0]
        if not filename or len(filename) == 0:
            return

        try:
            self.save_sbml(filename)
        except ValueError:
            output = io.StringIO()
            traceback.print_exc(file=output)
            exstr = output.getvalue()
            QMessageBox.critical(self, 'ValueError: Could not save project!',
                                 exstr+'\nPlease report the problem to:\n\
                                    \nhttps://github.com/cnapy-org/CNApy/issues')

            return

    @Slot()
    def load_box_positions(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            directory=self.appdata.work_directory, filter="*.maps")[0]
        if not filename or len(filename) == 0 or not os.path.exists(filename):
            return

        idx = self.centralWidget().map_tabs.currentIndex()
        if idx < 0:
            self.centralWidget().add_map()
            idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)

        with open(filename, 'r') as fp:
            self.appdata.project.maps[name]["boxes"] = json.load(fp)

        to_remove = []
        for r_id in self.appdata.project.maps[name]["boxes"].keys():
            if not self.appdata.project.cobra_py_model.reactions.has_id(r_id):
                to_remove.append(r_id)

        for r_id in to_remove:
            self.appdata.project.maps[name]["boxes"].pop(r_id)

        self.recreate_maps()
        self.unsaved_changes()
        self.centralWidget().update()

    @Slot()
    def load_scenario(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            directory=self.appdata.work_directory, filter="*.scen")[0]
        if not filename or len(filename) == 0 or not os.path.exists(filename):
            return

        with open(filename, 'r') as fp:
            values = json.load(fp)
            self.appdata.project.scen_values.clear()
            self.appdata.scenario_past.clear()
            self.appdata.scenario_future.clear()
            for i in values:
                self.appdata.scen_values_set(i, values[i])

            self.appdata.project.comp_values.clear()
        self.centralWidget().update()

    @Slot()
    def load_modes(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            directory=self.appdata.work_directory, filter="*.npz")[0]
        if not filename or len(filename) == 0 or not os.path.exists(filename):
            return

        self.appdata.project.modes = FluxVectorContainer(filename)
        self.centralWidget().mode_navigator.current = 0
        values = self.appdata.project.modes[0]
        self.appdata.project.scen_values.clear()
        self.appdata.project.comp_values.clear()
        for i in values:
            self.appdata.project.comp_values[i] = (values[i], values[i])
        self.centralWidget().update()

    @Slot()
    def change_background(self):
        '''Load a background image for the current map'''
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            directory=self.appdata.work_directory, filter="*.svg")[0]
        if not filename or len(filename) == 0 or not os.path.exists(filename):
            return

        idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)
        if filename != '':
            self.appdata.project.maps[name]["background"] = filename

            background = QGraphicsSvgItem(
                self.appdata.project.maps[name]["background"])
            background.setFlags(QGraphicsItem.ItemClipsToShape)
            self.centralWidget().map_tabs.widget(idx).scene.addItem(background)

            self.centralWidget().update()
            self.centralWidget().map_tabs.setCurrentIndex(idx)
            self.unsaved_changes()

    @Slot()
    def change_map_name(self):
        '''Execute RenameMapDialog'''
        dialog = RenameMapDialog(
            self.appdata, self.centralWidget())
        dialog.exec_()

    @Slot()
    def inc_bg_size(self):
        idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)
        self.appdata.project.maps[name]["bg-size"] *= 1.1
        self.unsaved_changes()
        self.centralWidget().update()

    @Slot()
    def dec_bg_size(self):
        idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)
        self.appdata.project.maps[name]["bg-size"] *= (1/1.1)
        self.unsaved_changes()
        self.centralWidget().update()

    @Slot()
    def zoom_in(self):
        mv: MapView = self.centralWidget().map_tabs.currentWidget()
        if mv is not None:
            mv.zoom_in()

    @Slot()
    def zoom_out(self):
        mv: MapView = self.centralWidget().map_tabs.currentWidget()
        if mv is not None:
            mv.zoom_out()

    @Slot()
    def save_box_positions(self):
        idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)

        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            directory=self.appdata.work_directory, filter="*.maps")[0]
        if not filename or len(filename) == 0:
            return

        with open(filename, 'w') as fp:
            json.dump(self.appdata.project.maps[name]["boxes"], fp)

    @Slot()
    def save_scenario(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            directory=self.appdata.work_directory, filter="*.scen")[0]
        if not filename or len(filename) == 0:
            return

        with open(filename, 'w') as fp:
            json.dump(self.appdata.project.scen_values, fp)

    @Slot()
    def save_modes(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            directory=self.appdata.work_directory, filter="*.npz")[0]
        if not filename or len(filename) == 0:
            return
        self.appdata.project.modes.save(filename)

    def undo_scenario_edit(self):
        ''' undo last edit in scenario history '''
        if len(self.appdata.scenario_past) > 0:
            last = self.appdata.scenario_past.pop()
            self.appdata.scenario_future.append(last)
            self.appdata.recreate_scenario_from_history()
            self.centralWidget().update()

    def redo_scenario_edit(self):
        ''' redo last undo of scenario history '''
        if len(self.appdata.scenario_future) > 0:
            nex = self.appdata.scenario_future.pop()
            self.appdata.scenario_past.append(nex)
            self.appdata.recreate_scenario_from_history()
            self.centralWidget().update()

    def clear_scenario(self):
        self.appdata.scen_values_clear()
        self.appdata.project.comp_values.clear()
        self.appdata.project.high = 0
        self.appdata.project.low = 0
        self.centralWidget().update()

    def load_default_scenario(self):
        self.appdata.project.comp_values.clear()
        self.appdata.scen_values_clear()
        for r in self.appdata.project.cobra_py_model.reactions:
            if 'cnapy-default' in r.annotation.keys():
                self.centralWidget().update_reaction_value(
                    r.id, r.annotation['cnapy-default'])
        self.centralWidget().update()

    @Slot()
    def new_project(self):
        self.appdata.project = ProjectData()
        self.centralWidget().map_tabs.currentChanged.disconnect(self.on_tab_change)
        self.centralWidget().map_tabs.clear()
        self.centralWidget().map_tabs.currentChanged.connect(self.on_tab_change)

        self.centralWidget().mode_navigator.clear()

        self.appdata.project.scen_values.clear()
        self.appdata.scenario_past.clear()
        self.appdata.scenario_future.clear()

        self.set_current_filename("Untitled project")
        self.nounsaved_changes()

    @Slot()
    def new_project_from_sbml(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            directory=self.appdata.work_directory, filter="*.xml *.sbml")[0]
        if not filename or len(filename) == 0 or not os.path.exists(filename):
            return
        try:
            cobra_py_model = cobra.io.read_sbml_model(filename)
        except cobra.io.sbml.CobraSBMLError:
            output = io.StringIO()
            traceback.print_exc(file=output)
            exstr = output.getvalue()
            QMessageBox.warning(
                self, 'Could not read sbml.', exstr)
            return
        self.new_project()
        self.appdata.project.cobra_py_model = cobra_py_model
        self.centralWidget().update()

    @Slot()
    def open_project(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            directory=self.appdata.work_directory, filter="*.cna")[0]
        if not filename or len(filename) == 0 or not os.path.exists(filename):
            return

        temp_dir = TemporaryDirectory()

        try:
            with ZipFile(filename, 'r') as zip_ref:
                zip_ref.extractall(temp_dir.name)

                with open(temp_dir.name+"/box_positions.json", 'r') as fp:
                    maps = json.load(fp)

                    count = 1
                    for _name, m in maps.items():
                        m["background"] = temp_dir.name + \
                            "/map" + str(count) + ".svg"
                        count += 1
                # load meta_data
                with open(temp_dir.name+"/meta.json", 'r') as fp:
                    meta_data = json.load(fp)

                try:
                    cobra_py_model = cobra.io.read_sbml_model(
                        temp_dir.name + "/model.sbml")
                except cobra.io.sbml.CobraSBMLError:
                    output = io.StringIO()
                    traceback.print_exc(file=output)
                    exstr = output.getvalue()
                    QMessageBox.warning(
                        self, 'Could not open project.', exstr)
                    return
                self.appdata.temp_dir = temp_dir
                self.appdata.project.maps = maps
                self.appdata.project.meta_data = meta_data
                self.appdata.project.cobra_py_model = cobra_py_model
                self.set_current_filename(filename)
                self.recreate_maps()
                self.centralWidget().mode_navigator.clear()
                self.appdata.project.scen_values.clear()
                self.appdata.scenario_past.clear()
                self.appdata.scenario_future.clear()
                for r in self.appdata.project.cobra_py_model.reactions:
                    if 'cnapy-default' in r.annotation.keys():
                        self.centralWidget().update_reaction_value(
                            r.id, r.annotation['cnapy-default'])
                self.nounsaved_changes()

                # if project contains maps move splitter and fit mapview
                if len(self.appdata.project.maps) > 0:
                    (_, r) = self.centralWidget().splitter2.getRange(1)
                    self.centralWidget().splitter2.moveSplitter(r*0.8, 1)
                    self.centralWidget().fit_mapview()

                self.centralWidget().update()
        except FileNotFoundError:
            output = io.StringIO()
            traceback.print_exc(file=output)
            exstr = output.getvalue()
            QMessageBox.warning(self, 'Could not open project.', exstr)
            return

    def save_sbml(self, filename):
        '''Save model as SBML'''

        # cleanup to work around cobrapy not setting a default compartement
        # remove unused species
        (clean_model, unused_mets) = prune_unused_metabolites(
            self.appdata.project.cobra_py_model)
        # set unset compartments to ''
        undefined = ''
        for m in clean_model.metabolites:
            if m.compartment is None:
                undefined += m.id+'\n'
                m.compartment = 'undefined_compartment_please_fix'
            else:
                x = m.compartment
                x.strip()
                if x == '':
                    undefined += m.id+'\n'
                    m.compartment = 'undefined_compartment_please_fix'

        if undefined != '':
            QMessageBox.warning(self, 'Undefined compartments',
                                'The following metabolites have undefined compartments!\n' +
                                undefined+'\nPlease check!')

        self.appdata.project.cobra_py_model = clean_model

        cobra.io.write_sbml_model(
            self.appdata.project.cobra_py_model, filename)

    @Slot()
    def save_project(self):
        ''' Save the project '''
        tmp_dir = TemporaryDirectory().name
        filename: str = self.appdata.project.name

        try:
            self.save_sbml(tmp_dir + "model.sbml")
        except ValueError:
            output = io.StringIO()
            traceback.print_exc(file=output)
            exstr = output.getvalue()
            QMessageBox.critical(self, 'ValueError: Could not save project!',
                                 exstr+'\nPlease report the problem to:\n\
                                    \nhttps://github.com/cnapy-org/CNApy/issues')

            return

        svg_files = {}
        count = 1
        for name, m in self.appdata.project.maps.items():
            arc_name = "map" + str(count) + ".svg"
            svg_files[m["background"]] = arc_name
            m["background"] = arc_name
            count += 1

        # Save maps information
        with open(tmp_dir + "box_positions.json", 'w') as fp:
            json.dump(self.appdata.project.maps, fp)

        # Save meta data
        self.appdata.project.meta_data["format version"] = self.appdata.format_version
        with open(tmp_dir + "meta.json", 'w') as fp:
            json.dump(self.appdata.project.meta_data, fp)

        with ZipFile(filename, 'w') as zip_obj:
            zip_obj.write(tmp_dir + "model.sbml", arcname="model.sbml")
            zip_obj.write(tmp_dir + "box_positions.json",
                          arcname="box_positions.json")
            zip_obj.write(tmp_dir + "meta.json", arcname="meta.json")
            for name, m in svg_files.items():
                zip_obj.write(name, arcname=m)

        # put svgs into temporary directory and update references
        with ZipFile(filename, 'r') as zip_ref:
            zip_ref.extractall(self.appdata.temp_dir.name)
            count = 1
            for name, m in self.appdata.project.maps.items():
                m["background"] = self.appdata.temp_dir.name + \
                    "/map" + str(count) + ".svg"
                count += 1

        self.nounsaved_changes()

    @Slot()
    def save_project_as(self):

        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            directory=self.appdata.work_directory, filter="*.cna")

        if len(filename[0]) != 0:
            self.set_current_filename(filename[0])
            self.save_project()
        else:
            return

    def recreate_maps(self):
        self.centralWidget().map_tabs.currentChanged.disconnect(self.on_tab_change)
        self.centralWidget().map_tabs.clear()
        self.centralWidget().map_tabs.currentChanged.connect(self.on_tab_change)

        for name, mmap in self.appdata.project.maps.items():
            mmap = MapView(self.appdata, name)
            mmap.show()
            mmap.switchToReactionMask.connect(
                self.centralWidget().switch_to_reaction)
            mmap.minimizeReaction.connect(
                self.centralWidget().minimize_reaction)
            mmap.maximizeReaction.connect(
                self.centralWidget().maximize_reaction)
            mmap.reactionValueChanged.connect(
                self.centralWidget().update_reaction_value)
            mmap.reactionRemoved.connect(
                self.centralWidget().update_reaction_maps)
            mmap.reactionAdded.connect(
                self.centralWidget().update_reaction_maps)
            mmap.mapChanged.connect(
                self.centralWidget().handle_mapChanged)
            self.centralWidget().map_tabs.addTab(mmap, name)
            mmap.update()

    def on_tab_change(self, idx):
        if idx >= 0:
            self.change_map_name_action.setEnabled(True)
            self.change_background_action.setEnabled(True)
            self.inc_bg_size_action.setEnabled(True)
            self.dec_bg_size_action.setEnabled(True)
            self.save_box_positions_action.setEnabled(True)
            self.centralWidget().update_map(idx)
        else:
            self.change_map_name_action.setEnabled(False)
            self.change_background_action.setEnabled(False)
            self.inc_bg_size_action.setEnabled(False)
            self.dec_bg_size_action.setEnabled(False)
            self.save_box_positions_action.setEnabled(False)

    def copy_to_clipboard(self):
        self.appdata.project.clipboard = self.appdata.project.comp_values.copy()

    def paste_clipboard(self):
        self.appdata.project.comp_values = self.appdata.project.clipboard
        self.centralWidget().update()

    @Slot()
    def clipboard_arithmetics(self):
        dialog = ClipboardCalculator(self.appdata.project)
        dialog.exec_()
        self.centralWidget().update()

    def add_values_to_scenario(self):
        for key in self.appdata.project.comp_values.keys():
            self.appdata.scen_values_set(
                key, self.appdata.project.comp_values[key])
        self.centralWidget().update()

    def set_model_bounds_to_scenario(self):
        for reaction in self.appdata.project.cobra_py_model.reactions:
            if reaction.id in self.appdata.project.scen_values:
                (vl, vu) = self.appdata.project.scen_values[reaction.id]
                reaction.lower_bound = vl
                reaction.upper_bound = vu
        self.centralWidget().update()

    def set_scenario_to_default_scenario(self):
        ''' write current scenario into sbml annotation '''
        for reaction in self.appdata.project.cobra_py_model.reactions:
            if reaction.id in self.appdata.project.scen_values:
                values = self.appdata.project.scen_values[reaction.id]
                reaction.annotation['cnapy-default'] = str(values)
            else:
                if 'cnapy-default' in reaction.annotation.keys():
                    reaction.annotation.pop('cnapy-default')
        self.centralWidget().update()
        self.unsaved_changes()

    def fba(self):
        with self.appdata.project.cobra_py_model as model:
            load_values_into_model(self.appdata.project.scen_values,  model)
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

    def fba_optimize_reaction(self, reaction: str, mmin: bool):
        with self.appdata.project.cobra_py_model as model:
            load_values_into_model(self.appdata.project.scen_values,  model)

            for r in self.appdata.project.cobra_py_model.reactions:
                if r.id == reaction:
                    if mmin:
                        r.objective_coefficient = -1
                    else:
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
            load_values_into_model(self.appdata.project.scen_values,  model)
            try:
                solution = cobra.flux_analysis.pfba(model)
            except cobra.exceptions.Infeasible:
                QMessageBox.information(
                    self, 'No solution', 'The scenario is infeasible')
            except Exception:
                output = io.StringIO()
                traceback.print_exc(file=output)
                exstr = output.getvalue()
                print(exstr)
                QMessageBox.warning(self, 'Unknown exception occured!',
                                    exstr+'\nPlease report the problem to:\n\
                                    \nhttps://github.com/cnapy-org/CNApy/issues')
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

    def execute_print_model_stats(self):
        if len(self.appdata.project.cobra_py_model.reactions) > 0:
            self.centralWidget().kernel_client.execute("cna.print_model_stats()")
        else:
            self.centralWidget().kernel_client.execute("print('\\nEmpty matrix!')")

        self.centralWidget().scroll_down()

    def show_net_conversion(self):
        self.centralWidget().kernel_client.execute("cna.net_conversion()")
        self.centralWidget().scroll_down()

    def net_conversion(self):
        with self.appdata.project.cobra_py_model as model:
            load_values_into_model(self.appdata.project.scen_values,  model)
            solution = model.optimize()
            if solution.status == 'optimal':
                errors = False
                imports = []
                exports = []
                soldict = solution.fluxes.to_dict()
                for i in soldict:
                    r = self.appdata.project.cobra_py_model.reactions.get_by_id(
                        i)
                    val = round(soldict[i], self.appdata.rounding)
                    if r.reactants == []:
                        if len(r.products) != 1:
                            print(
                                'Error: Expected only import reactions with one metabolite but',
                                i, 'imports', r.products)
                            errors = True
                        else:
                            if val > 0.0:
                                imports.append(
                                    str(val) + ' ' + r.products[0].id)
                            elif val < 0.0:
                                exports.append(
                                    str(abs(val)) + ' ' + r.products[0].id)

                    elif r.products == []:
                        if len(r.reactants) != 1:
                            print(
                                'Error: Expected only export reactions with one metabolite but',
                                i, 'exports', r.reactants)
                            errors = True
                        else:
                            if val > 0.0:
                                exports.append(
                                    str(val) + ' ' + r.reactants[0].id)
                            elif val < 0.0:
                                imports.append(
                                    str(abs(val)) + ' ' + r.reactants[0].id)

                if errors:
                    return

                print(
                    '\x1b[1;04;34m'+"Net conversion of external metabolites by the given scenario is:\x1b[0m\n")
                print(' + '.join(imports))
                print('-->')
                print(' + '.join(exports))

            elif solution.status == 'infeasible':
                print('No solution the scenario is infeasible!')
            else:
                print('No solution!', solution.status)

    def show_optimization_function(self):
        self.centralWidget().kernel_client.execute("cna.optimization_function()")
        self.centralWidget().scroll_down()

    def optimization_function(self):
        print('\x1b[1;04;34m'+"Optimization function:\x1b[0m\n")
        first = True
        res = ""
        model = self.appdata.project.cobra_py_model
        for r in model.reactions:
            if r.objective_coefficient != 0:
                if first:
                    res += str(r.objective_coefficient) + " " + str(r.id)
                    first = False
                else:
                    if r.objective_coefficient > 0:
                        res += " +" + \
                            str(r.objective_coefficient) + " " + str(r.id)
                    else:
                        res += " "+str(r.objective_coefficient) + \
                            " " + str(r.id)

        print(model.objective.direction+"imize:", res)

    def print_model_stats(self):
        m = cobra.util.array.create_stoichiometric_matrix(
            self.appdata.project.cobra_py_model, array_type='DataFrame')
        metabolites = m.shape[0]
        reactions = m.shape[1]
        print('Stoichiometric matrix:\n', m)
        print('\nNumber of metabolites: ', metabolites)
        print('Number of reactions: ', reactions)
        rank = np.linalg.matrix_rank(m)
        print('\nRank of stoichiometric matrix: ' + str(rank))
        print('Degrees of freedom: ' + str(reactions-rank))
        print('Conservation relations: ' + str(metabolites-rank))

        has_non_zero = False
        mmin = None
        abs_m = np.absolute(m.to_numpy())
        for r in abs_m:
            for e in r:
                if not has_non_zero:
                    if e > 0.0:
                        has_non_zero = True
                        mmin = e
                else:
                    if e > 0.0 and e < mmin:
                        mmin = e
        if has_non_zero:
            print('\nSmallest (absolute) non-zero-value:', mmin)
        else:
            print('\nIt\'s the zero matrix')

        c = []
        abs_m = np.absolute(m.to_numpy())
        for r in abs_m:
            x = max(r)
            c.append(x)
        print('Largest (absolute) value:', max(c))

    def print_in_out_fluxes(self, metabolite):
        with self.appdata.project.cobra_py_model as model:
            load_values_into_model(self.appdata.project.scen_values,  model)
            solution = model.optimize()
            if solution.status == 'optimal':
                soldict = solution.fluxes.to_dict()
                self.in_out_fluxes(metabolite, soldict)
            elif solution.status == 'infeasible':
                print('No solution the scenario is infeasible!')
            else:
                print('No solution!', solution.status)

    def show_model_bounds(self):
        for reaction in self.appdata.project.cobra_py_model.reactions:
            self.appdata.project.comp_values[reaction.id] = (
                reaction.lower_bound, reaction.upper_bound)
        self.centralWidget().update()

    def fva(self):
        worker = Worker(self.run_fva)
        worker.signals.result.connect(self.set_fva_solution)
        self.appdata.threadpool.start(worker)

    def efm(self):
        self.efm_dialog = EFMDialog(
            self.appdata, self.centralWidget())
        self.efm_dialog.open()

    def efmtool(self):
        self.efmtool_dialog = EFMtoolDialog(
            self.appdata, self.centralWidget())
        self.efmtool_dialog.open()

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

        idx = self.centralWidget().map_tabs.currentIndex()
        if idx < 0:
            return
        name = self.centralWidget().map_tabs.tabText(idx)
        view = self.centralWidget().map_tabs.widget(idx)
        for key in self.appdata.project.maps[name]["boxes"]:
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
        (low, high) = self.high_and_low()
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
                    color = self.compute_color_heat(value, low, high)
                    item.setBackground(2, color)
                elif key in self.appdata.project.comp_values:
                    value = self.appdata.project.comp_values[key]
                    color = self.compute_color_heat(value, low, high)
                    item.setBackground(2, color)

        idx = self.centralWidget().map_tabs.currentIndex()
        if idx < 0:
            return
        name = self.centralWidget().map_tabs.tabText(idx)
        view = self.centralWidget().map_tabs.widget(idx)
        for key in self.appdata.project.maps[name]["boxes"]:
            if key in self.appdata.project.scen_values:
                value = self.appdata.project.scen_values[key]
                color = self.compute_color_heat(value, low, high)
                view.reaction_boxes[key].set_color(color)
            elif key in self.appdata.project.comp_values:
                value = self.appdata.project.comp_values[key]
                color = self.compute_color_heat(value, low, high)
                view.reaction_boxes[key].set_color(color)

    def compute_color_heat(self, value: Tuple[float, float], low, high):
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

    def in_out_fluxes(self, metabolite_id, soldict):
        import matplotlib.pyplot as plt

        with self.appdata.project.cobra_py_model as model:
            met = model.metabolites.get_by_id(metabolite_id)
            fig, ax = plt.subplots()
            ax.set_xticks([1, 2])
            ax.set_xticklabels(['In', 'Out'])
            cons = []
            prod = []
            sum_cons = 0
            sum_prod = 0
            for rxn in met.reactions:
                flux = rxn.get_coefficient(metabolite_id) * soldict[rxn.id]
                if flux < 0:
                    cons.append((rxn.id, -flux))
                elif flux > 0:
                    prod.append((rxn.id, flux))
            cons = sorted(cons, key=lambda x: x[1], reverse=True)
            prod = sorted(prod, key=lambda x: x[1], reverse=True)
            for rxn_id, flux in prod:
                ax.bar(1, flux, width=0.8, bottom=sum_prod, label=rxn_id)
                sum_prod += flux
            for rxn_id, flux in cons:
                ax.bar(2, flux, width=0.8, bottom=sum_cons, label=rxn_id)
                sum_cons += flux
            ax.set_ylabel('Flux')
            ax.set_title('In/Out fluxes at metabolite ' + metabolite_id)
            ax.legend(bbox_to_anchor=(1, 1), loc="upper left")
            plt.show()

    def run_fva(self):
        with self.appdata.project.cobra_py_model as model:
            solution = fva_computation(model, self.appdata.project.scen_values)
            return solution

    def set_fva_solution(self, solution):

        minimum = solution.minimum.to_dict()
        maximum = solution.maximum.to_dict()
        for i in minimum:
            self.appdata.project.comp_values[i] = (
                minimum[i], maximum[i])
        self.centralWidget().update()


def my_mean(value):
    if isinstance(value, float):
        return value
    else:
        (vl, vh) = value
        return (vl+vh)/2
