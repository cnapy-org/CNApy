import io
import json
import os
import traceback
from tempfile import TemporaryDirectory
from typing import Tuple
from zipfile import ZipFile

import cobra
from qtpy.QtCore import Qt
from qtpy.QtCore import QFileInfo, Slot
from qtpy.QtGui import QColor, QIcon, QPalette
from qtpy.QtSvg import QGraphicsSvgItem
from qtpy.QtWidgets import (QAction, QApplication, QFileDialog, QGraphicsItem,
                            QMainWindow, QMessageBox, QToolBar)

from cnapy.cnadata import CnaData
from cnapy.gui_elements.about_dialog import AboutDialog
from cnapy.gui_elements.centralwidget import CentralWidget
from cnapy.gui_elements.clipboard_calculator import ClipboardCalculator
from cnapy.gui_elements.rename_map_dialog import RenameMapDialog
from cnapy.gui_elements.config_dialog import ConfigDialog
from cnapy.gui_elements.efm_dialog import EFMDialog
from cnapy.gui_elements.map_view import MapView
from cnapy.gui_elements.mcs_dialog import MCSDialog
from cnapy.gui_elements.phase_plane_dialog import PhasePlaneDialog
from cnapy.gui_elements.yield_optimization_dialog import \
    YieldOptimizationDialog


class MainWindow(QMainWindow):
    """The cnapy main window"""

    def __init__(self, appdata: CnaData):
        QMainWindow.__init__(self)
        self.setWindowTitle("cnapy")
        self.appdata = appdata

        # safe original color
        palette = self.palette()
        self.original_color = palette.color(QPalette.Window)

        import pkg_resources
        heat_svg = pkg_resources.resource_filename('cnapy', 'data/heat.svg')
        onoff_svg = pkg_resources.resource_filename('cnapy', 'data/onoff.svg')
        default_color_svg = pkg_resources.resource_filename(
            'cnapy', 'data/default-color.svg')
        default_scenario_svg = pkg_resources.resource_filename(
            'cnapy', 'data/Font_D.svg')

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
        heaton_action.setIcon(QIcon(heat_svg))
        heaton_action.triggered.connect(self.set_heaton)
        self.scenario_menu.addAction(heaton_action)

        onoff_action = QAction("Apply On/Off coloring", self)
        onoff_action.setIcon(QIcon(onoff_svg))
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

        load_maps_action = QAction("Load reaction box positions...", self)
        self.map_menu.addAction(load_maps_action)
        load_maps_action.triggered.connect(self.load_box_positions)

        save_box_positions_action = QAction(
            "Save reaction box positions...", self)
        self.map_menu.addAction(save_box_positions_action)
        save_box_positions_action.triggered.connect(self.save_box_positions)

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

        show_model_stats_action = QAction("Show model stats", self)
        self.analysis_menu.addAction(show_model_stats_action)
        show_model_stats_action.triggered.connect(
            self.execute_print_model_stats)

        net_conversion_action = QAction(
            "Compute net conversion of external metabolites", self)
        self.analysis_menu.addAction(net_conversion_action)
        net_conversion_action.triggered.connect(
            self.execute_net_conversion)

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
        update_action.setIcon(QIcon(default_color_svg))
        update_action.triggered.connect(central_widget.update)

        set_default_scenario_action = QAction("Default scenario", self)
        set_default_scenario_action.setIcon(QIcon(default_scenario_svg))
        set_default_scenario_action.triggered.connect(
            self.set_default_scenario)

        add_map_action = QAction("Add new map", self)
        # add_map_action.setIcon(QIcon("cnapy/data/Font_D.svg"))
        add_map_action.triggered.connect(
            central_widget.add_map)

        self.setCurrentFile("Untitled project")

        self.tool_bar = QToolBar()
        self.tool_bar.addAction(clear_scenario_action)
        self.tool_bar.addAction(reset_scenario_action)
        self.tool_bar.addAction(set_default_scenario_action)
        self.tool_bar.addAction(heaton_action)
        self.tool_bar.addAction(onoff_action)
        self.tool_bar.addAction(update_action)
        self.tool_bar.addAction(add_map_action)
        self.addToolBar(self.tool_bar)

        self.centralWidget().map_tabs.currentChanged.connect(self.on_tab_change)

    def unsaved_changes(self):
        self.appdata.unsaved = True
        palette = self.palette()
        palette.setColor(QPalette.Window, Qt.yellow)
        self.setPalette(palette)

    @Slot()
    def exit_app(self, _checked):
        QApplication.quit()

    def setCurrentFile(self, fileName):
        self.appdata.project.name = fileName

        if len(self.appdata.project.name) == 0:
            shownName = "Untitled project"
        else:
            shownName = QFileInfo(self.appdata.project.name).fileName()

        self.setWindowTitle(
            "CNApy - " + shownName)

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
        dialog = YieldOptimizationDialog(self.appdata, self.centralWidget())
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
    def load_box_positions(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.maps")

        idx = self.centralWidget().map_tabs.currentIndex()
        if idx < 0:
            self.centralWidget().add_map()
            idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)

        with open(filename[0], 'r') as fp:
            print(fp)
            self.appdata.project.maps[name]["boxes"] = json.load(fp)

        to_remove = []
        for r in self.appdata.project.maps[name]["boxes"].keys():
            if not self.appdata.project.cobra_py_model.reactions.has_id(r):
                to_remove.append(r)

        for r in to_remove:
            self.appdata.project.maps[name]["boxes"].pop(r)

        self.recreate_maps()
        self.unsaved_changes()
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

        idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)
        if filename[0] != '':
            # try:
            self.appdata.project.maps[name]["background"] = filename[0]
            print(self.appdata.project.maps[name]["background"])

            background = QGraphicsSvgItem(
                self.appdata.project.maps[name]["background"])
            background.setFlags(QGraphicsItem.ItemClipsToShape)
            self.centralWidget().map_tabs.widget(idx).scene.addItem(background)
            # except:
            # print("could not update background")

            self.centralWidget().update()
            self.centralWidget().map_tabs.setCurrentIndex(idx)

    @Slot()
    def change_map_name(self, _checked):
        dialog = RenameMapDialog(
            self.appdata, self.centralWidget())
        dialog.exec_()

    @Slot()
    def inc_bg_size(self, _checked):
        idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)
        self.appdata.project.maps[name]["bg-size"] += 0.2
        self.unsaved_changes()
        self.centralWidget().update()

    @Slot()
    def dec_bg_size(self, _checked):
        idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)
        self.appdata.project.maps[name]["bg-size"] -= 0.2
        self.unsaved_changes()
        self.centralWidget().update()

    @Slot()
    def save_box_positions(self, _checked):
        idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)

        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.maps")

        with open(filename[0], 'w') as fp:
            json.dump(self.appdata.project.maps[name]["boxes"], fp)

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
        self.appdata.project.scen_values.clear()
        for r in self.appdata.project.cobra_py_model.reactions:
            if 'cnapy-default' in r.annotation.keys():
                self.centralWidget().update_reaction_value(
                    r.id, r.annotation['cnapy-default'])
        self.centralWidget().update()

    @Slot()
    def new_project(self, _checked):
        self.appdata.project.cobra_py_model = cobra.Model()
        self.appdata.project.maps = {}
        self.centralWidget().map_tabs.currentChanged.disconnect(self.on_tab_change)
        self.centralWidget().map_tabs.clear()
        self.centralWidget().map_tabs.currentChanged.connect(self.on_tab_change)

        self.centralWidget().mode_navigator.clear()
        self.clear_scenario()

        self.setCurrentFile("Untitled project")
        self.save_project_action.setEnabled(False)

    @Slot()
    def open_project(self, _checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            dir=os.getcwd(), filter="*.cna")

        self.appdata.temp_dir = TemporaryDirectory()

        with ZipFile(filename[0], 'r') as zip_ref:
            zip_ref.extractall(self.appdata.temp_dir.name)

            with open(self.appdata.temp_dir.name+"/maps.json", 'r') as fp:
                self.appdata.project.maps = json.load(fp)

                count = 1
                for name, m in self.appdata.project.maps.items():
                    m["background"] = self.appdata.temp_dir.name + \
                        "/.bg" + str(count) + ".svg"
                    count += 1

            self.appdata.project.cobra_py_model = cobra.io.read_sbml_model(
                self.appdata.temp_dir.name + "/model.sbml")

            self.recreate_maps()
            self.centralWidget().mode_navigator.clear()
            self.clear_scenario()
            for r in self.appdata.project.cobra_py_model.reactions:
                if 'cnapy-default' in r.annotation.keys():
                    self.centralWidget().update_reaction_value(
                        r.id, r.annotation['cnapy-default'])
            self.save_project_action.setEnabled(True)
            self.centralWidget().reaction_list.update()

        self.setCurrentFile(filename[0])

    @Slot()
    def save_project(self, _checked):

        tmp_dir = TemporaryDirectory().name
        filename: str = self.appdata.project.name

        # save SBML model
        cobra.io.write_sbml_model(
            self.appdata.project.cobra_py_model, tmp_dir + "model.sbml")

        svg_files = {}
        count = 1
        for name, m in self.appdata.project.maps.items():
            arc_name = ".bg" + str(count) + ".svg"
            svg_files[m["background"]] = arc_name
            m["background"] = arc_name
            count += 1

        # Save maps information
        with open(tmp_dir + "maps.json", 'w') as fp:
            json.dump(self.appdata.project.maps, fp)

        with ZipFile(filename, 'w') as zipObj:
            zipObj.write(tmp_dir + "model.sbml", arcname="model.sbml")
            zipObj.write(tmp_dir + "maps.json", arcname="maps.json")
            for name, m in svg_files.items():
                zipObj.write(name, arcname=m)

        # put svgs into temporary directory and update references
        with ZipFile(filename, 'r') as zip_ref:
            zip_ref.extractall(self.appdata.temp_dir.name)
            count = 1
            for name, m in self.appdata.project.maps.items():
                m["background"] = self.appdata.temp_dir.name + \
                    "/.bg" + str(count) + ".svg"
                count += 1

        palette = self.palette()
        palette.setColor(QPalette.Window, self.original_color)
        self.setPalette(palette)

    @Slot()
    def save_project_as(self, _checked):

        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            dir=os.getcwd(), filter="*.cna")

        if len(filename[0]) != 0:
            self.setCurrentFile(filename[0])
            self.save_project_action.setEnabled(True)
            self.save_project(_checked=True)
        else:
            return False

    def recreate_maps(self):
        self.centralWidget().map_tabs.currentChanged.disconnect(self.on_tab_change)
        self.centralWidget().map_tabs.clear()
        self.centralWidget().map_tabs.currentChanged.connect(self.on_tab_change)

        for name, map in self.appdata.project.maps.items():
            map = MapView(self.appdata, name)
            map.show()
            map.switchToReactionDialog.connect(
                self.centralWidget().switch_to_reaction)
            map.minimizeReaction.connect(
                self.centralWidget().minimize_reaction)
            map.maximizeReaction.connect(
                self.centralWidget().maximize_reaction)
            map.reactionValueChanged.connect(
                self.centralWidget().update_reaction_value)
            map.reactionRemoved.connect(
                self.centralWidget().update_reaction_maps)
            map.reactionAdded.connect(
                self.centralWidget().update_reaction_maps)
            map.mapChanged.connect(
                self.centralWidget().handle_mapChanged)
            self.centralWidget().map_tabs.addTab(map, name)
            map.update()

    def on_tab_change(self, idx):
        if idx >= 0:
            self.change_map_name_action.setEnabled(True)
            self.change_background_action.setEnabled(True)
            self.inc_bg_size_action.setEnabled(True)
            self.dec_bg_size_action.setEnabled(True)
            self.centralWidget().update_map(idx)
        else:
            self.change_map_name_action.setEnabled(False)
            self.change_background_action.setEnabled(False)
            self.inc_bg_size_action.setEnabled(False)
            self.dec_bg_size_action.setEnabled(False)

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

    def fba_optimize_reaction(self, reaction: str, min: bool):
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            for r in self.appdata.project.cobra_py_model.reactions:
                if r.id == reaction:
                    if min:
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
            self.appdata.project.load_scenario_into_model(model)
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
                                    \nhttps://github.com/ARB-Lab/CNApy/issues')
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

        self.centralWidget().splitter2.setSizes([0, 0, 100])

    def execute_net_conversion(self):
        self.centralWidget().kernel_client.execute("cna.net_conversion()")
        self.centralWidget().splitter2.setSizes([0, 0, 100])

    def net_conversion(self):
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            solution = model.optimize()
            if solution.status == 'optimal':
                errors = False
                imports = []
                exports = []
                soldict = solution.fluxes.to_dict()
                for i in soldict:
                    r = self.appdata.project.cobra_py_model.reactions.get_by_id(
                        i)
                    if r.reactants == []:
                        if len(r.products) != 1:
                            print(
                                'Error: Expected only import reactions with one metabolite but', i, 'imports', r.products)
                            errors = True
                        else:
                            if soldict[i] > 0.0:
                                imports.append(
                                    str(round(soldict[i], self.appdata.rounding)) + ' ' + r.products[0].id)
                            elif soldict[i] < 0.0:
                                exports.append(
                                    str(abs(round(soldict[i], self.appdata.rounding))) + ' ' + r.products[0].id)

                    elif r.products == []:
                        if len(r.reactants) != 1:
                            print(
                                'Error: Expected only export reactions with one metabolite but', i, 'exports', r.reactants)
                            errors = True
                        else:
                            if soldict[i] > 0.0:
                                exports.append(
                                    str(round(soldict[i], self.appdata.rounding)) + ' ' + r.reactants[0].id)
                            elif soldict[i] < 0.0:
                                imports.append(
                                    str(abs(round(soldict[i], self.appdata.rounding))) + ' ' + r.reactants[0].id)

                if errors:
                    return
                else:
                    print(
                        '\x1b[1;04;34m'+"Net conversion of external metabolites by the given scenario is:\x1b[0m\n")
                    print(' + '.join(imports))
                    print('-->')
                    print(' + '.join(exports))

            elif solution.status == 'infeasible':
                print('No solution the scenario is infeasible!')
            else:
                print('No solution!', solution.status)

    def print_model_stats(self):
        import cobra
        m = cobra.util.array.create_stoichiometric_matrix(
            self.appdata.project.cobra_py_model, array_type='DataFrame')
        metabolites = m.shape[0]
        reactions = m.shape[1]
        print('Stoichiometric matrix:\n', m)
        print('\nNumber of metabolites: ', metabolites)
        print('Number of reactions: ', reactions)
        import numpy
        rank = numpy.linalg.matrix_rank(m)
        print('\nRank of stoichiometric matrix: ' + str(rank))
        print('Degrees of freedom: ' + str(reactions-rank))
        print('Conservation relations: ' + str(metabolites-rank))
        import numpy as np
        has_non_zero = False
        min = None
        abs_m = np.absolute(m.to_numpy())
        for r in abs_m:
            for e in r:
                if not has_non_zero:
                    if e > 0.0:
                        has_non_zero = True
                        min = e
                else:
                    if e > 0.0 and e < min:
                        min = e
        if has_non_zero:
            print('\nSmallest (absolute) non-zero-value:', min)
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
            self.appdata.project.load_scenario_into_model(model)
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
        from cobra.flux_analysis import flux_variability_analysis
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            for r in self.appdata.project.cobra_py_model.reactions:
                r.objective_coefficient = 0
            try:
                solution = flux_variability_analysis(model)
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
                                    \nhttps://github.com/ARB-Lab/CNApy/issues')
            else:
                minimum = solution.minimum.to_dict()
                maximum = solution.maximum.to_dict()
                for i in minimum:
                    self.appdata.project.comp_values[i] = (
                        minimum[i], maximum[i])

                self.appdata.project.compute_color_type = 3

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

        idx = self.centralWidget().map_tabs.currentIndex()
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

        idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)
        view = self.centralWidget().map_tabs.widget(idx)
        for key in self.appdata.project.maps[name]["boxes"]:
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


def my_mean(value):
    if isinstance(value, float):
        return value
    else:
        (vl, vh) = value
        return (vl+vh)/2
