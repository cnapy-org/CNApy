import io
import json
import os
import traceback
from tempfile import TemporaryDirectory
from typing import Tuple
from zipfile import ZipFile
import xml.etree.ElementTree as ET
from cnapy.flux_vector_container import FluxVectorContainer
from cnapy.core import model_optimization_with_exceptions
import cobra
from optlang_enumerator.cobra_cnapy import CNApyModel
from optlang_enumerator.mcs_computation import flux_variability_analysis
from optlang.symbolics import Zero
import numpy as np
import cnapy.resources  # Do not delete this import - it seems to be unused but in fact it provides the menu icons
import matplotlib.pyplot as plt

from qtpy.QtCore import QFileInfo, Qt, Slot
from qtpy.QtGui import QColor, QIcon, QKeySequence
from qtpy.QtWidgets import (QAction, QActionGroup, QApplication, QFileDialog,
                            QMainWindow, QMessageBox, QToolBar, QShortcut, QStatusBar, QLabel, QDialog)

from cnapy.appdata import AppData, ProjectData
from cnapy.gui_elements.about_dialog import AboutDialog
from cnapy.gui_elements.central_widget import CentralWidget, ModelTabIndex
from cnapy.gui_elements.clipboard_calculator import ClipboardCalculator
from cnapy.gui_elements.config_dialog import ConfigDialog
from cnapy.gui_elements.download_dialog import DownloadDialog
from cnapy.gui_elements.config_cobrapy_dialog import ConfigCobrapyDialog
from cnapy.gui_elements.efmtool_dialog import EFMtoolDialog
from cnapy.gui_elements.flux_feasibility_dialog import FluxFeasibilityDialog
from cnapy.gui_elements.map_view import MapView
from cnapy.gui_elements.mcs_dialog import MCSDialog
from cnapy.gui_elements.strain_design_dialog import SDDialog, SDComputationViewer, SDViewer, SDComputationThread
from cnapy.gui_elements.plot_space_dialog import PlotSpaceDialog
from cnapy.gui_elements.in_out_flux_dialog import InOutFluxDialog
from cnapy.gui_elements.reactions_list import ReactionListColumn
from cnapy.gui_elements.rename_map_dialog import RenameMapDialog
from cnapy.gui_elements.yield_optimization_dialog import YieldOptimizationDialog
from cnapy.gui_elements.flux_optimization_dialog import FluxOptimizationDialog
from cnapy.gui_elements.configuration_cplex import CplexConfigurationDialog
from cnapy.gui_elements.configuration_gurobi import GurobiConfigurationDialog
import cnapy.utils as utils


class MainWindow(QMainWindow):
    """The cnapy main window"""

    def __init__(self, appdata: AppData):
        QMainWindow.__init__(self)
        self.setWindowTitle("cnapy")
        self.appdata = appdata

        # self.heaton_action and self.onoff_action need to be defined before CentralWidget
        self.heaton_action = QAction("Heatmap coloring", self)
        self.heaton_action.setIcon(QIcon(":/icons/heat.png"))
        self.heaton_action.triggered.connect(self.set_heaton)

        self.onoff_action = QAction("On/Off coloring", self)
        self.onoff_action.setIcon(QIcon(":/icons/onoff.png"))
        self.onoff_action.triggered.connect(self.set_onoff)

        central_widget = CentralWidget(self)
        self.setCentralWidget(central_widget)

        self.menu = self.menuBar()
        self.file_menu = self.menu.addMenu("&Project")

        new_project_action = QAction("&New project", self)
        new_project_action.setShortcut("Ctrl+N")
        self.file_menu.addAction(new_project_action)
        new_project_action.triggered.connect(self.new_project)

        new_project_from_sbml_action = QAction(
            "New project from SBML...", self)
        self.file_menu.addAction(new_project_from_sbml_action)
        new_project_from_sbml_action.triggered.connect(
            self.new_project_from_sbml)

        open_project_action = QAction("&Open project...", self)
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

        download_examples = QAction("Download CNApy example projects...", self)
        self.file_menu.addAction(download_examples)
        download_examples.triggered.connect(self.download_examples)

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        self.file_menu.addAction(exit_action)
        exit_action.triggered.connect(self.exit_app)

        self.scenario_menu = self.menu.addMenu("Scenario")

        load_default_scenario_action = QAction("Apply default scenario flux values", self)
        self.scenario_menu.addAction(load_default_scenario_action)
        load_default_scenario_action.setIcon(QIcon(":/icons/d-font.png"))
        load_default_scenario_action.triggered.connect(
            self.load_default_scenario)


        set_scenario_to_default_scenario_action = QAction(
            "Set current scenario fluxes as default scenario fluxes", self)
        self.scenario_menu.addAction(set_scenario_to_default_scenario_action)
        set_scenario_to_default_scenario_action.triggered.connect(
            self.set_scenario_to_default_scenario)

        load_scenario_action = QAction("Load scenario...", self)
        self.scenario_menu.addAction(load_scenario_action)
        load_scenario_action.triggered.connect(self.load_scenario)

        save_scenario_action = QAction("Save scenario...", self)
        self.scenario_menu.addAction(save_scenario_action)
        save_scenario_action.triggered.connect(self.save_scenario)

        undo_scenario_action = QAction("Undo scenario flux values edit", self)
        undo_scenario_action.setIcon(QIcon(":/icons/undo.png"))
        self.scenario_menu.addAction(undo_scenario_action)
        undo_scenario_action.triggered.connect(self.undo_scenario_edit)

        redo_scenario_action = QAction("Redo scenario flux values edit", self)
        redo_scenario_action.setIcon(QIcon(":/icons/redo.png"))
        self.scenario_menu.addAction(redo_scenario_action)
        redo_scenario_action.triggered.connect(self.redo_scenario_edit)

        clear_scenario_action = QAction("Clear scenario", self)
        self.scenario_menu.addAction(clear_scenario_action)
        clear_scenario_action.triggered.connect(self.clear_scenario)

        clear_all_action = QAction("Clear all reaction box entries", self)
        clear_all_action.setIcon(QIcon(":/icons/clear.png"))
        self.scenario_menu.addAction(clear_all_action)
        clear_all_action.triggered.connect(self.clear_all)

        add_values_to_scenario_action = QAction(
            "Add all flux values to scenario", self)
        self.scenario_menu.addAction(add_values_to_scenario_action)
        add_values_to_scenario_action.triggered.connect(
            self.add_values_to_scenario)

        merge_scenario_action = QAction("Merge flux values from scenario...", self)
        self.scenario_menu.addAction(merge_scenario_action)
        merge_scenario_action.triggered.connect(self.merge_scenario)

        set_model_bounds_to_scenario_action = QAction(
            "Use scenario flux values as model bounds", self)
        self.scenario_menu.addAction(set_model_bounds_to_scenario_action)
        set_model_bounds_to_scenario_action.triggered.connect(
            self.set_model_bounds_to_scenario)

        pin_scenario_reactions_action = QAction(
            "Pin all scenario reactions to top of reaction list", self)
        self.scenario_menu.addAction(pin_scenario_reactions_action)
        pin_scenario_reactions_action.triggered.connect(
            self.pin_scenario_reactions)

        self.scenario_menu.addSeparator()

        update_action = QAction("Default Coloring", self)
        update_action.setIcon(QIcon(":/icons/default-color.png"))
        update_action.triggered.connect(central_widget.update)

        self.scenario_menu.addAction(self.heaton_action)
        self.scenario_menu.addAction(self.onoff_action)
        self.scenario_menu.addAction(update_action)

        self.clipboard_menu = self.menu.addMenu("Clipboard")

        copy_to_clipboard_action = QAction("Copy to clipboard", self)
        self.clipboard_menu.addAction(copy_to_clipboard_action)
        copy_to_clipboard_action.triggered.connect(self.copy_to_clipboard)

        paste_clipboard_action = QAction("Paste clipboard", self)
        self.clipboard_menu.addAction(paste_clipboard_action)
        paste_clipboard_action.triggered.connect(self.paste_clipboard)

        clipboard_arithmetics_action = QAction(
            "Clipboard arithmetics...", self)
        self.clipboard_menu.addAction(clipboard_arithmetics_action)
        clipboard_arithmetics_action.triggered.connect(
            self.clipboard_arithmetics)

        self.map_menu = self.menu.addMenu("Map")

        add_map_action = QAction("Add new map", self)
        self.map_menu.addAction(add_map_action)
        add_map_action.triggered.connect(central_widget.add_map)

        # add_escher_map_action = QAction("Add new map from Escher JSON and SVG...", self)
        add_escher_map_action = QAction("Add new map from Escher SVG...", self)
        self.map_menu.addAction(add_escher_map_action)
        add_escher_map_action.triggered.connect(self.add_escher_map)

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

        self.inc_box_size_action = QAction("Increase box size", self)
        self.inc_box_size_action.setShortcut("Ctrl++")
        self.map_menu.addAction(self.inc_box_size_action)
        self.inc_box_size_action.triggered.connect(self.inc_box_size)
        self.inc_box_size_action.setEnabled(False)

        self.dec_box_size_action = QAction("Decrease box size", self)
        self.dec_box_size_action.setShortcut("Ctrl+-")
        self.map_menu.addAction(self.dec_box_size_action)
        self.dec_box_size_action.triggered.connect(self.dec_box_size)
        self.dec_box_size_action.setEnabled(False)

        self.inc_bg_size_action = QAction("Increase background size", self)
        self.inc_bg_size_action.setShortcut("Ctrl+Shift++")
        self.map_menu.addAction(self.inc_bg_size_action)
        self.inc_bg_size_action.triggered.connect(self.inc_bg_size)
        self.inc_bg_size_action.setEnabled(False)

        self.dec_bg_size_action = QAction("Decrease background size", self)
        self.dec_bg_size_action.setShortcut("Ctrl+Shift+-")
        self.map_menu.addAction(self.dec_bg_size_action)
        self.dec_bg_size_action.triggered.connect(self.dec_bg_size)
        self.dec_bg_size_action.setEnabled(False)

        self.analysis_menu = self.menu.addMenu("Analysis")

        fba_action = QAction("Flux Balance Analysis (FBA)", self)
        fba_action.triggered.connect(self.fba)
        self.analysis_menu.addAction(fba_action)

        self.auto_fba_action = QAction("Auto FBA", self)
        self.auto_fba_action.triggered.connect(self.auto_fba)
        self.auto_fba_action.setCheckable(True)
        self.analysis_menu.addAction(self.auto_fba_action)

        pfba_action = QAction(
            "Parsimonious Flux Balance Analysis (pFBA)", self)
        pfba_action.triggered.connect(self.pfba)
        self.analysis_menu.addAction(pfba_action)

        fva_action = QAction("Flux Variability Analysis (FVA)", self)
        fva_action.triggered.connect(self.fva)
        self.analysis_menu.addAction(fva_action)

        make_scenario_feasible_action = QAction("Make scenario feasible...", self)
        make_scenario_feasible_action.triggered.connect(self.make_scenario_feasible)
        self.analysis_menu.addAction(make_scenario_feasible_action)

        self.analysis_menu.addSeparator()

        self.efm_menu = self.analysis_menu.addMenu("Elementary Flux Modes")

        self.efmtool_action = QAction(
            "Compute Elementary Flux Modes via EFMtool...", self)
        self.efmtool_action.triggered.connect(self.efmtool)
        self.efm_menu.addAction(self.efmtool_action)

        load_modes_action = QAction("Load modes...", self)
        self.efm_menu.addAction(load_modes_action)
        load_modes_action.triggered.connect(self.load_modes)

        self.sd_menu = self.analysis_menu.addMenu("Computational Strain Design")
        self.sd_action = QAction("Compute Minimal Cut Sets...", self)
        self.sd_action.triggered.connect(self.mcs)
        self.sd_menu.addAction(self.sd_action)
        self.mcs_dialog = None

        load_mcs_action = QAction("Load Minimal Cut Sets...", self)
        self.sd_menu.addAction(load_mcs_action)
        load_mcs_action.triggered.connect(self.load_mcs)

        self.sd_action = QAction("Compute Strain Designs...", self)
        self.sd_action.triggered.connect(self.strain_design)
        self.sd_menu.addAction(self.sd_action)
        self.sd_dialog = None
        self.sd_sols = None

        load_sd_action = QAction("Load Strain Designs...", self)
        self.sd_menu.addAction(load_sd_action)
        load_sd_action.triggered.connect(self.load_strain_designs)

        self.flux_optimization_action = QAction(
            "Flux optimization...", self)
        self.flux_optimization_action.triggered.connect(self.optimize_flux)
        self.analysis_menu.addAction(self.flux_optimization_action)

        self.yield_optimization_action = QAction(
            "Yield optimization...", self)
        self.yield_optimization_action.triggered.connect(self.optimize_yield)
        self.analysis_menu.addAction(self.yield_optimization_action)

        plot_space_action = QAction("Plot flux space...", self)
        plot_space_action.triggered.connect(self.plot_space)
        self.analysis_menu.addAction(plot_space_action)

        self.analysis_menu.addSeparator()

        show_model_stats_action = QAction("Show model stats", self)
        self.analysis_menu.addAction(show_model_stats_action)
        show_model_stats_action.triggered.connect(
            self.execute_print_model_stats)

        show_model_bounds_action = QAction("Show flux bounds in reaction boxes", self)
        self.analysis_menu.addAction(show_model_bounds_action)
        show_model_bounds_action.triggered.connect(self.show_model_bounds)

        net_conversion_action = QAction(
            "Net conversion of external metabolites", self)
        self.analysis_menu.addAction(net_conversion_action)
        net_conversion_action.triggered.connect(
            self.show_net_conversion)

        in_out_flux_action = QAction(
            "Compute in/out fluxes at metabolite...", self)
        in_out_flux_action.triggered.connect(self.in_out_flux)
        self.analysis_menu.addAction(in_out_flux_action)

        self.config_menu = self.menu.addMenu("Config")

        config_action = QAction("Configure CNApy...", self)
        self.config_menu.addAction(config_action)
        config_action.triggered.connect(self.show_config_dialog)

        config_action = QAction("Configure COBRApy...", self)
        self.config_menu.addAction(config_action)
        config_action.triggered.connect(self.show_config_cobrapy_dialog)


        config_action = QAction("Configure IBM CPLEX Full Version...", self)
        self.config_menu.addAction(config_action)
        config_action.triggered.connect(self.show_cplex_configuration_dialog)


        config_action = QAction("Configure Gurobi Full Version...", self)
        self.config_menu.addAction(config_action)
        config_action.triggered.connect(self.show_gurobi_configuration_dialog)

        show_console_action = QAction("Show Console", self)
        self.config_menu.addAction(show_console_action)
        show_console_action.triggered.connect(self.show_console)

        show_map_view = QAction("Show map view", self)
        self.config_menu.addAction(show_map_view)
        show_map_view.triggered.connect(self.show_map_view)

        show_model_view_action = QAction("Show model view", self)
        self.config_menu.addAction(show_model_view_action)
        show_model_view_action.triggered.connect(self.show_model_view)

        about_action = QAction("About CNApy...", self)
        self.config_menu.addAction(about_action)
        about_action.triggered.connect(self.show_about)

        zoom_in_action = QAction("Zoom in Map", self)
        zoom_in_action.setIcon(QIcon(":/icons/zoom-in.png"))
        zoom_in_action.triggered.connect(self.zoom_in)

        zoom_out_action = QAction("Zoom out Map", self)
        zoom_out_action.setIcon(QIcon(":/icons/zoom-out.png"))
        zoom_out_action.triggered.connect(self.zoom_out)

        self.set_current_filename("Untitled project")

        self.heaton_action.setCheckable(True)
        self.onoff_action.setCheckable(True)
        update_action.setCheckable(True)
        update_action.setChecked(True)
        colorings = QActionGroup(self)
        colorings.addAction(self.heaton_action)
        colorings.addAction(self.onoff_action)
        colorings.addAction(update_action)
        colorings.setExclusive(True)

        self.tool_bar = QToolBar()
        self.tool_bar.addAction(clear_all_action)
        self.tool_bar.addAction(undo_scenario_action)
        self.tool_bar.addAction(redo_scenario_action)
        self.tool_bar.addSeparator()
        self.tool_bar.addAction(self.heaton_action)
        self.tool_bar.addAction(self.onoff_action)
        self.tool_bar.addAction(update_action)
        self.tool_bar.addSeparator()
        self.tool_bar.addAction(zoom_in_action)
        self.tool_bar.addAction(zoom_out_action)
        self.addToolBar(self.tool_bar)

        self.focus_search_action = QShortcut(
            QKeySequence('Ctrl+f'), self)
        self.focus_search_action.activated.connect(self.focus_search_box)

        status_bar: QStatusBar = self.statusBar()
        self.solver_status_display = QLabel()
        status_bar.addPermanentWidget(self.solver_status_display)
        self.solver_status_symbol = QLabel()
        status_bar.addPermanentWidget(self.solver_status_symbol)

        self.centralWidget().map_tabs.currentChanged.connect(self.on_tab_change)

    def closeEvent(self, event):
        if self.checked_unsaved():
            self.close_project_dialogs()
            event.accept()
            # releases the memory map file if this is a FluxVectorMemmap
            self.appdata.project.modes.clear()
        else:
            event.ignore()

    def checked_unsaved(self) -> bool:
        if self.appdata.unsaved:
            msgBox = QMessageBox()
            msgBox.setText("The project has been modified.")
            msgBox.setInformativeText("Do you want to save your changes?")
            msgBox.setStandardButtons(
                QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            msgBox.setDefaultButton(QMessageBox.Save)
            ret = msgBox.exec_()
            if ret == QMessageBox.Save:
                # Save was clicked
                self.save_project_as()
                return True
            if ret == QMessageBox.Discard:
                # Don't save was clicked
                return True
            if ret == QMessageBox.Cancel:
                return False
        return True

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

    @Slot()
    def exit_app(self):
        if self.checked_unsaved():
            # releases the memory map file if this is a FluxVectorMemmap
            self.appdata.project.modes.clear()
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
        dialog = AboutDialog(self.appdata)
        dialog.exec_()

    @Slot()
    def plot_space(self):
        self.plot_space = PlotSpaceDialog(self.appdata)
        self.plot_space.show()

    # Strain design computation and viewing functions
    def strain_design(self):
        self.sd_dialog = SDDialog(self.appdata)
        self.sd_dialog.show()

    @Slot(str)
    def strain_design_with_setup(self, sd_setup):
        self.sd_dialog = SDDialog(self.appdata, json.loads(sd_setup))
        self.sd_dialog.show()

    @Slot(str)
    def compute_strain_design(self,sd_setup):
        # launch progress viewer and computation thread
        self.sd_viewer = SDComputationViewer(self.appdata, sd_setup)
        self.sd_viewer.show_sd_signal.connect(self.show_strain_designs,Qt.QueuedConnection)
        # connect signals to update progress
        self.sd_computation = SDComputationThread(self.appdata, sd_setup)
        self.sd_computation.output_connector.connect(     self.sd_viewer.receive_progress_text,Qt.QueuedConnection)
        self.sd_computation.finished_computation.connect( self.sd_viewer.conclude_computation, Qt.QueuedConnection)
        self.sd_viewer.cancel_computation.connect(self.terminate_strain_design_computation)
        # show dialog and launch process
        # self.sd_viewer.exec()
        self.sd_viewer.show()
        self.sd_computation.start()

    @Slot()
    def terminate_strain_design_computation(self):
        self.sd_computation.output_connector.disconnect()
        self.sd_computation.finished_computation.disconnect()
        self.sd_computation.terminate()

    @Slot(bytes)
    def show_strain_designs(self,solutions):
        self.sd_sols = SDViewer(self.appdata, solutions)
        self.sd_sols.show()
        self.centralWidget().update_mode()

    @Slot()
    def load_strain_designs(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            directory=self.appdata.work_directory, filter="*.sds")[0]
        if not filename or len(filename) == 0 or not os.path.exists(filename):
            return
        with open(filename,'rb') as f:
            solutions = f.read()
        self.show_strain_designs(solutions)

    @Slot()
    def optimize_yield(self):
        dialog = YieldOptimizationDialog(self.appdata, self.centralWidget())
        dialog.exec_()

    @Slot()
    def optimize_flux(self):
        dialog = FluxOptimizationDialog(self.appdata, self.centralWidget())
        dialog.exec_()

    @Slot()
    def show_config_dialog(self):
        dialog = ConfigDialog(self.appdata)
        dialog.exec_()

    @Slot()
    def show_config_cobrapy_dialog(self):
        dialog = ConfigCobrapyDialog(self.appdata)
        if self.mcs_dialog is not None:
            dialog.optlang_solver_set.connect(self.mcs_dialog.set_optlang_solver_text)
            dialog.optlang_solver_set.connect(self.mcs_dialog.configure_solver_options)
        dialog.exec_()

    @Slot()
    def show_cplex_configuration_dialog(self):
        dialog = CplexConfigurationDialog(self.appdata)
        dialog.exec_()

    @Slot()
    def show_gurobi_configuration_dialog(self):
        dialog = GurobiConfigurationDialog(self.appdata)
        dialog.exec_()

    @Slot()
    def export_sbml(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            directory=self.appdata.work_directory, filter="*.xml *.sbml")[0]
        if not filename or len(filename) == 0:
            return

        self.setCursor(Qt.BusyCursor)
        try:
            self.save_sbml(filename)
        except ValueError:
            output = io.StringIO()
            traceback.print_exc(file=output)
            exstr = output.getvalue()
            utils.show_unknown_error_box(exstr)

        self.setCursor(Qt.ArrowCursor)

    @Slot()
    def download_examples(self):
        dialog = DownloadDialog(self.appdata)
        dialog.exec_()

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
    def merge_scenario(self):
        self.load_scenario(merge=True)

    @Slot()
    def load_scenario(self, merge=False):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            directory=self.appdata.last_scen_directory, filter="*.scen *.val")[0]
        if not filename or len(filename) == 0 or not os.path.exists(filename):
            return

        self.appdata.scenario_past.clear()
        self.appdata.scenario_future.clear()

        missing_reactions = self.appdata.project.scen_values.load(filename, self.appdata, merge=merge)

        self.centralWidget().reaction_list.pin_multiple(self.appdata.project.scen_values.pinned_reactions)

        if len(missing_reactions) > 0 :
            QMessageBox.warning(self, 'Unknown reactions in scenario',
            'The scenario references reactions which are not in the current model and will be ignored:\n'+' '.join(missing_reactions))

        self.appdata.project.comp_values.clear()
        self.appdata.project.fva_values.clear()
        if self.appdata.auto_fba:
            self.fba()
        else:
            self.centralWidget().update()
            self.clear_status_bar()
        self.appdata.last_scen_directory = os.path.dirname(filename)

    @Slot()
    def load_modes(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            directory=self.appdata.work_directory, filter="*.npz")[0]
        if not filename or len(filename) == 0 or not os.path.exists(filename):
            return

        self.appdata.project.modes = FluxVectorContainer(filename)
        self.centralWidget().mode_navigator.current = 0

        self.centralWidget().mode_navigator.set_to_efm()
        self.centralWidget().update_mode()

    @Slot()
    def load_mcs(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(
            directory=self.appdata.work_directory, filter="*.npz")[0]
        if not filename or len(filename) == 0 or not os.path.exists(filename):
            return

        self.appdata.project.modes = FluxVectorContainer(filename)
        self.centralWidget().mode_navigator.current = 0
        self.centralWidget().mode_navigator.set_to_mcs()
        self.centralWidget().update_mode()

    @Slot()
    def change_background(self, caption="Select a SVG file", directory=None):
        '''Load a background image for the current map'''
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(caption=caption,
            directory=self.appdata.work_directory if directory is None else directory,
            filter="*.svg")[0]
        if not filename or len(filename) == 0 or not os.path.exists(filename):
            return None

        idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)

        self.appdata.project.maps[name]["background"] = filename
        self.centralWidget().map_tabs.widget(idx).set_background()
        self.centralWidget().update()
        self.centralWidget().map_tabs.setCurrentIndex(idx)
        self.centralWidget().map_tabs.widget(idx).fit()
        self.unsaved_changes()

        return filename

    # the variant below requires both the Escher JSON and an exported SVG
    # @Slot()
    # def add_escher_map(self):
    #     dialog = QFileDialog(self)
    #     filename: str = dialog.getOpenFileName(caption="Select an Escher JSON file",
    #         directory=self.appdata.work_directory, filter="*.json")[0]
    #     if not filename or len(filename) == 0 or not os.path.exists(filename):
    #         return
    #
    #     with open(filename) as fp:
    #         map_json = json.load(fp)
    #
    #     map_name, map_idx = self.centralWidget().add_map(base_name=map_json[0]['map_name'])
    #     self.change_background(caption="Select a SVG file that corresponds to the previously loaded Escher JSON file")
    #
    #     reaction_bigg_ids = dict()
    #     for r in self.appdata.project.cobra_py_model.reactions:
    #         bigg_id = r.annotation.get("bigg.reaction", None)
    #         if bigg_id is None: # if there is no BiGG ID in the annotation...
    #             bigg_id = r.id # ... use the reaction ID as proxy
    #         reaction_bigg_ids[bigg_id] = r.id
    #
    #     offset_x = map_json[1]['canvas']['x']
    #     offset_y = map_json[1]['canvas']['y']
    #     self.appdata.project.maps[map_name]["boxes"] = dict()
    #     for r in map_json[1]["reactions"].values():
    #         bigg_id = r["bigg_id"]
    #         if bigg_id in reaction_bigg_ids:
    #             self.appdata.project.maps[map_name]["boxes"][reaction_bigg_ids[bigg_id]] = [r["label_x"] - offset_x, r["label_y"] - offset_y]
    #
    #     self.recreate_maps()
    #     self.centralWidget().map_tabs.setCurrentIndex(map_idx)

    @Slot()
    def add_escher_map(self):
        # map gets a default name because an Escher SVG file does not contain the map name
        has_unsaved_changes = self.appdata.unsaved
        map_name, map_idx = self.centralWidget().add_map()
        file_name = self.change_background(caption="Select an Escher SVG file")
        if file_name is None:
            del self.appdata.project.maps[map_name]
            self.centralWidget().map_tabs.removeTab(map_idx)
            self.appdata.unsaved = has_unsaved_changes
            return

        reaction_bigg_ids = dict()
        for r in self.appdata.project.cobra_py_model.reactions:
            bigg_id = r.annotation.get("bigg.reaction", None)
            if bigg_id is None: # if there is no BiGG ID in the annotation...
                bigg_id = r.id # ... use the reaction ID as proxy
            reaction_bigg_ids[bigg_id] = r.id

        def get_translate_coordinates(translate: str):
            x_y = translate.split("(")[1].split(",")
            return float(x_y[0]), float(x_y[1][:-1])
        self.appdata.project.maps[map_name]["boxes"] = dict()
        try:
            root = ET.parse(file_name).getroot()
            graph = root.find('{http://www.w3.org/2000/svg}g')
            canvas_group = None
            reactions = None
            for child in graph:
                # print(child.tag, child.attrib)
                if child.attrib.get("class", None) == "canvas-group":
                    canvas_group = child
                if child.attrib.get("id", None) == "reactions":
                    reactions = child
            if canvas_group is None or reactions is None:
                raise ValueError
            canvas = None
            for child in canvas_group:
                if child.attrib.get("id", None) == "canvas":
                    canvas = child
            if canvas is None:
                raise ValueError
            (offset_x, offset_y) = get_translate_coordinates(canvas.attrib['transform'])
            for r in reactions:
                for child in r:
                    if child.attrib.get("class", None) == "reaction-label-group":
                        for neighbor in child.iter():
                            if neighbor.attrib.get("class", None) == "reaction-label label":
                                bigg_id = neighbor.text
                                if bigg_id in reaction_bigg_ids:
                                    (label_x, label_y) =  get_translate_coordinates(child.attrib['transform'])
                                    self.appdata.project.maps[map_name]["boxes"][reaction_bigg_ids[bigg_id]] = [label_x - offset_x, label_y - offset_y]
        except:
            QMessageBox.critical(self, "Failed to parse "+file_name+" as Escher SVG file",
                                 file_name+" does not appear to have been exported from Escher. "
                                 "Automatic mapping of reaction boxes not possible.")
            self.appdata.project.maps[map_name]["boxes"] = dict()

        self.recreate_maps()
        self.centralWidget().map_tabs.setCurrentIndex(map_idx)
        self.centralWidget().map_tabs.widget(map_idx).fit()

    @Slot()
    def change_map_name(self):
        '''Execute RenameMapDialog'''
        dialog = RenameMapDialog(
            self.appdata, self.centralWidget())
        dialog.exec_()

    @Slot()
    def inc_box_size(self):
        idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)
        self.appdata.project.maps[name]["box-size"] *= 1.1
        self.unsaved_changes()
        self.centralWidget().update()

    @Slot()
    def dec_box_size(self):
        idx = self.centralWidget().map_tabs.currentIndex()
        name = self.centralWidget().map_tabs.tabText(idx)
        self.appdata.project.maps[name]["box-size"] *= (1/1.1)
        self.unsaved_changes()
        self.centralWidget().update()

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
    def focus_search_box(self):
        self.centralWidget().searchbar.setFocus()

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
            directory=self.appdata.last_scen_directory, filter="*.scen")[0]
        if not filename or len(filename) == 0:
            return

        # with open(filename, 'w') as fp:
        #     json.dump(self.appdata.project.scen_values, fp)
        self.appdata.project.scen_values.save(filename)

        self.appdata.last_scen_directory = os.path.dirname(filename)

    def undo_scenario_edit(self):
        ''' undo last edit in scenario history '''
        if len(self.appdata.scenario_past) > 0:
            last = self.appdata.scenario_past.pop()
            self.appdata.scenario_future.append(last)
            self.appdata.recreate_scenario_from_history()
            if self.appdata.auto_fba:
                self.fba()
            self.centralWidget().update()

    def redo_scenario_edit(self):
        ''' redo last undo of scenario history '''
        if len(self.appdata.scenario_future) > 0:
            nex = self.appdata.scenario_future.pop()
            self.appdata.scenario_past.append(nex)
            self.appdata.recreate_scenario_from_history()
            if self.appdata.auto_fba:
                self.fba()
            self.centralWidget().update()

    def clear_scenario(self):
        self.appdata.scen_values_clear()
        self.centralWidget().update()

    def clear_all(self):
        self.appdata.scen_values_clear()
        self.appdata.project.comp_values.clear()
        self.appdata.project.fva_values.clear()
        self.appdata.project.high = 0
        self.appdata.project.low = 0
        self.centralWidget().update()
        self.clear_status_bar()

    def load_default_scenario(self):
        self.appdata.project.comp_values.clear()
        self.appdata.project.fva_values.clear()
        self.appdata.scen_values_clear()
        (reactions, values) = self.appdata.project.collect_default_scenario_values()
        if len(reactions) == 0:
            self.appdata.scen_values_clear()
        else:
            self.appdata.scen_values_set_multiple(reactions, values)
        if self.appdata.auto_fba:
            self.fba()
        else:
            self.centralWidget().update()
            self.clear_status_bar()

    @Slot()
    def new_project(self):
        if self.checked_unsaved():
            self.new_project_unchecked()
            self.recreate_maps()

    def new_project_unchecked(self):
        self.appdata.project = ProjectData()
        self.centralWidget().map_tabs.currentChanged.disconnect(self.on_tab_change)
        self.centralWidget().map_tabs.clear()
        self.centralWidget().map_tabs.currentChanged.connect(self.on_tab_change)

        self.centralWidget().mode_navigator.clear()
        self.centralWidget().reaction_list.reaction_list.clear()
        self.close_project_dialogs()

        self.appdata.project.scen_values.clear()
        self.appdata.scenario_past.clear()
        self.appdata.scenario_future.clear()

        self.set_current_filename("Untitled project")
        self.nounsaved_changes()

    @Slot()
    def new_project_from_sbml(self):
        if self.checked_unsaved():
            dialog = QFileDialog(self)
            filename: str = dialog.getOpenFileName(
                directory=self.appdata.work_directory, filter="*.xml *.sbml")[0]
            if not filename or len(filename) == 0 or not os.path.exists(filename):
                return

            self.setCursor(Qt.BusyCursor)
            try:
                cobra_py_model = CNApyModel.read_sbml_model(filename)
            except cobra.io.sbml.CobraSBMLError:
                output = io.StringIO()
                traceback.print_exc(file=output)
                exstr = output.getvalue()
                QMessageBox.warning(
                    self, 'Could not read sbml.', exstr)
                return
            self.new_project_unchecked()
            self.appdata.project.cobra_py_model = cobra_py_model

            self.recreate_maps()
            self.centralWidget().update(rebuild=True)

            self.setCursor(Qt.ArrowCursor)

    @Slot()
    def open_project(self):
        if self.checked_unsaved():
            dialog = QFileDialog(self)
            filename: str = dialog.getOpenFileName(
                directory=self.appdata.work_directory, filter="*.cna")[0]
            if not filename or len(filename) == 0 or not os.path.exists(filename):
                return

            self.close_project_dialogs()
            temp_dir = TemporaryDirectory()

            self.setCursor(Qt.BusyCursor)
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
                        cobra_py_model = CNApyModel.read_sbml_model(
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
                    self.appdata.project.comp_values.clear()
                    self.appdata.project.fva_values.clear()
                    self.appdata.scenario_past.clear()
                    self.appdata.scenario_future.clear()
                    self.clear_status_bar()
                    (reactions, values) = self.appdata.project.collect_default_scenario_values()
                    if len(reactions) > 0:
                        self.appdata.scen_values_set_multiple(reactions, values)
                    self.nounsaved_changes()

                    # if project contains maps move splitter and fit mapview
                    if len(self.appdata.project.maps) > 0:
                        (_, r) = self.centralWidget().splitter2.getRange(1)
                        self.centralWidget().splitter2.moveSplitter(round(r*0.8), 1)
                        self.centralWidget().fit_mapview()

                    self.centralWidget().update(rebuild=True)
            except FileNotFoundError:
                output = io.StringIO()
                traceback.print_exc(file=output)
                exstr = output.getvalue()
                QMessageBox.warning(self, 'Could not open project.', exstr)

            self.setCursor(Qt.ArrowCursor)

    def close_project_dialogs(self):
        '''closes modeless dialogs'''
        if self.mcs_dialog is not None:
            self.mcs_dialog.close()
            self.mcs_dialog = None
        if self.sd_dialog:
            if self.sd_dialog.__weakref__:
                del self.sd_dialog
            self.sd_dialog = None

    def save_sbml(self, filename):
        '''Save model as SBML'''

        # cleanup to work around cobrapy not setting a default compartment
        # remove unused species - > cleanup disabled for now because of issues
        # with prune_unused_metabolites
        # (clean_model, unused_mets) = prune_unused_metabolites(
        #     self.appdata.project.cobra_py_model)
        clean_model = self.appdata.project.cobra_py_model
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

        self.setCursor(Qt.BusyCursor)
        try:
            self.save_sbml(tmp_dir + "model.sbml")
        except ValueError:
            output = io.StringIO()
            traceback.print_exc(file=output)
            exstr = output.getvalue()
            utils.show_unknown_error_box(exstr)

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
        self.setCursor(Qt.ArrowCursor)

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
            mmap = MapView(self.appdata, self.centralWidget(), name)
            mmap.show()
            mmap.switchToReactionMask.connect(
                self.centralWidget().switch_to_reaction)
            mmap.minimizeReaction.connect(
                self.centralWidget().minimize_reaction)
            mmap.maximizeReaction.connect(
                self.centralWidget().maximize_reaction)
            mmap.setScenValue.connect(
                self.centralWidget().set_scen_value)
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
            self.inc_box_size_action.setEnabled(True)
            self.dec_box_size_action.setEnabled(True)
            self.inc_bg_size_action.setEnabled(True)
            self.dec_bg_size_action.setEnabled(True)
            self.save_box_positions_action.setEnabled(True)
            self.centralWidget().update_map(idx)
        else:
            self.change_map_name_action.setEnabled(False)
            self.change_background_action.setEnabled(False)
            self.inc_box_size_action.setEnabled(False)
            self.dec_box_size_action.setEnabled(False)
            self.inc_bg_size_action.setEnabled(False)
            self.dec_bg_size_action.setEnabled(False)
            self.save_box_positions_action.setEnabled(False)

    def copy_to_clipboard(self):
        self.appdata.clipboard_comp_values = self.appdata.project.comp_values.copy()

    def paste_clipboard(self):
        self.appdata.project.comp_values = self.appdata.clipboard_comp_values.copy()
        self.centralWidget().update()

    @Slot()
    def clipboard_arithmetics(self):
        dialog = ClipboardCalculator(self.appdata)
        dialog.exec_()
        self.centralWidget().update()

    def add_values_to_scenario(self):
        self.appdata.scen_values_set_multiple(list(self.appdata.project.comp_values.keys()),
                                              list(self.appdata.project.comp_values.values()))
        self.appdata.project.comp_values.clear()
        if self.appdata.auto_fba:
            self.fba()
        self.centralWidget().update()

    def set_model_bounds_to_scenario(self):
        for reaction in self.appdata.project.cobra_py_model.reactions:
            if reaction.id in self.appdata.project.scen_values:
                (vl, vu) = self.appdata.project.scen_values[reaction.id]
                reaction.lower_bound = vl
                reaction.upper_bound = vu
        self.centralWidget().update()

    @Slot()
    def pin_scenario_reactions(self):
        self.centralWidget().reaction_list.pin_multiple(self.appdata.project.scen_values.keys())

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

    def auto_fba(self):
        if self.auto_fba_action.isChecked():
            self.appdata.auto_fba = True
            self.fba()
        else:
            self.appdata.auto_fba = False

    def fba(self):
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            self.appdata.project.solution = model_optimization_with_exceptions(model)
        self.process_fba_solution()

    def process_fba_solution(self, update=True):
        if self.appdata.project.solution.status == 'optimal':
            display_text = "Optimal solution with objective value "+self.appdata.format_flux_value(self.appdata.project.solution.objective_value)
            self.set_status_optimal()
            for r, v in self.appdata.project.solution.fluxes.items():
                self.appdata.project.comp_values[r] = (v, v)
        elif self.appdata.project.solution.status == 'infeasible':
            display_text = "No solution, the current scenario is infeasible"
            self.set_status_infeasible()
            self.appdata.project.comp_values.clear()
        else:
            display_text = "No optimal solution, solver status is "+self.appdata.project.solution.status
            self.set_status_unknown()
            self.appdata.project.comp_values.clear()
        self.centralWidget().console._append_plain_text("\n"+display_text, before_prompt=True)
        self.solver_status_display.setText(display_text)
        self.appdata.project.comp_values_type = 0
        if update:
            self.centralWidget().update()

    def make_scenario_feasible(self):
        make_scenario_feasible_dialog = FluxFeasibilityDialog(self.appdata)
        if make_scenario_feasible_dialog.exec_() == QDialog.Accepted:
            self.appdata.project.solution = make_scenario_feasible_dialog.solution
            self.process_fba_solution(update=False)
            if len(make_scenario_feasible_dialog.reactions_in_objective) > 0:
                if self.appdata.project.solution.status == 'optimal':
                    self.centralWidget().console._append_plain_text(
                        "\nThe fluxes of the following reactions were changed to make the scenario feasible:\n", before_prompt=True)
                    for r in make_scenario_feasible_dialog.reactions_in_objective:
                        given_value = self.appdata.project.scen_values[r][0]
                        computed_value = self.appdata.project.comp_values[r][0]
                        if abs(given_value - computed_value) > self.appdata.project.cobra_py_model.tolerance:
                            self.centralWidget().console._append_plain_text(r+": "+self.appdata.format_flux_value(given_value)
                                +" --> "+self.appdata.format_flux_value(computed_value)+"\n", before_prompt=True)
                    self.appdata.scen_values_set_multiple(make_scenario_feasible_dialog.reactions_in_objective,
                                [self.appdata.project.comp_values[r] for r in make_scenario_feasible_dialog.reactions_in_objective])
                    self.centralWidget().update()
                else:
                    QMessageBox.critical(self, "Solver could not find an optimal solution",
                                 "No optimal solution was found, solver returned status '"+self.appdata.project.solution.status+"'.")

    def fba_optimize_reaction(self, reaction: str, mmin: bool): # use status bar
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            for r in self.appdata.project.cobra_py_model.reactions:
                if r.id == reaction:
                    if mmin:
                        r.objective_coefficient = -1
                    else:
                        r.objective_coefficient = 1
                else:
                    r.objective_coefficient = 0
            self.appdata.project.solution = model_optimization_with_exceptions(model)
        self.process_fba_solution()

    def pfba(self):
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            try:
                solution = cobra.flux_analysis.pfba(model)
            except cobra.exceptions.Infeasible:
                display_text = "No solution, the current scenario is infeasible"
                self.set_status_infeasible()
                self.appdata.project.comp_values.clear()
            except Exception:
                display_text = "An unexpected error occured."
                self.set_status_unknown()
                self.appdata.project.comp_values.clear()
                output = io.StringIO()
                traceback.print_exc(file=output)
                exstr = output.getvalue()
                print(exstr)
                utils.show_unknown_error_box(exstr)
            else:
                if solution.status == 'optimal':
                    soldict = solution.fluxes.to_dict()
                    for i in soldict:
                        self.appdata.project.comp_values[i] = (
                            soldict[i], soldict[i])
                    display_text = "Optimal solution with objective value "+ \
                        self.appdata.format_flux_value(solution.objective_value)
                    self.set_status_optimal()
                else:
                    display_text = "No optimal solution, solver status is "+solution.status
                    self.set_status_unknown()
                    self.appdata.project.comp_values.clear()
            finally:
                self.centralWidget().console._append_plain_text("\n"+display_text, before_prompt=True)
                self.solver_status_display.setText(display_text)
                self.appdata.project.comp_values_type = 0
                self.centralWidget().update()

    def execute_print_model_stats(self):
        if len(self.appdata.project.cobra_py_model.reactions) > 0:
            self.centralWidget().kernel_client.execute("cna.print_model_stats()")
        else:
            self.centralWidget().kernel_client.execute("print('\\nEmpty matrix!')")

        self.centralWidget().show_bottom_of_console()

    def show_net_conversion(self):
        self.centralWidget().kernel_client.execute("cna.net_conversion()")
        self.centralWidget().show_bottom_of_console()

    def net_conversion(self):
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            solution = model_optimization_with_exceptions(model)
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
                    '\x1b[1;04;30m'+"Net conversion of external metabolites by the given scenario is:\x1b[0m\n")
                print(' + '.join(imports))
                print('-->')
                print(' + '.join(exports))

            elif solution.status == 'infeasible':
                print('No solution the scenario is infeasible!')
            else:
                print('No solution!', solution.status)

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
        print('Independent conservation relations: ' + str(metabolites-rank))

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
        soldict = {id: val[0] for (id, val) in self.appdata.project.comp_values.items()}
        self.in_out_fluxes(metabolite, soldict)

    def show_model_bounds(self):
        for reaction in self.appdata.project.cobra_py_model.reactions:
            self.appdata.project.comp_values[reaction.id] = (
                reaction.lower_bound, reaction.upper_bound)
        self.appdata.project.comp_values_type = 1
        self.centralWidget().update()

    def fva(self, fraction_of_optimum=0.0):  # cobrapy default is 1.0
        self.setCursor(Qt.BusyCursor)
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            if len(self.appdata.project.scen_values) > 0:
                update_stoichiometry_hash = True
            else:
                update_stoichiometry_hash = False
            for r in self.appdata.project.cobra_py_model.reactions:
                if r.lower_bound == -float('inf'):
                    r.lower_bound = cobra.Configuration().lower_bound
                    r.set_hash_value()
                    update_stoichiometry_hash = True
                if r.upper_bound == float('inf'):
                    r.upper_bound = cobra.Configuration().upper_bound
                    r.set_hash_value()
                    update_stoichiometry_hash = True
            if self.appdata.use_results_cache and update_stoichiometry_hash:
                model.set_stoichiometry_hash_object()
            try:
                solution = flux_variability_analysis(model, fraction_of_optimum=fraction_of_optimum,
                    results_cache_dir=self.appdata.results_cache_dir if self.appdata.use_results_cache else None,
                    fva_hash=model.stoichiometry_hash_object.copy() if self.appdata.use_results_cache else None,
                    print_func=lambda *txt: self.statusBar().showMessage(' '.join(list(txt))))
            except cobra.exceptions.Infeasible:
                QMessageBox.information(
                    self, 'No solution', 'The scenario is infeasible')
            except Exception:
                output = io.StringIO()
                traceback.print_exc(file=output)
                exstr = output.getvalue()
                print(exstr)
                utils.show_unknown_error_box(exstr)
            else:
                minimum = solution.minimum.to_dict()
                maximum = solution.maximum.to_dict()
                for i in minimum:
                    self.appdata.project.comp_values[i] = (
                        minimum[i], maximum[i])
                self.appdata.project.fva_values = self.appdata.project.comp_values.copy()
                self.appdata.project.comp_values_type = 1

        self.centralWidget().update()
        self.setCursor(Qt.ArrowCursor)

    # def efm(self):
    #     self.efm_dialog = EFMDialog(
    #         self.appdata, self.centralWidget())
    #     self.efm_dialog.exec_()

    def in_out_flux(self):
        in_out_flux_dialog = InOutFluxDialog(
            self.appdata)
        in_out_flux_dialog.exec_()

    def efmtool(self):
        self.efmtool_dialog = EFMtoolDialog(
            self.appdata, self.centralWidget())
        self.efmtool_dialog.exec_()

    def mcs(self):
        self.mcs_dialog = MCSDialog(
            self.appdata, self.centralWidget())
        self.mcs_dialog.show()

    def set_onoff(self):
        idx = self.centralWidget().tabs.currentIndex()
        if idx == ModelTabIndex.Reactions and self.appdata.project.comp_values_type == 0:
            # do coloring of LB/UB columns in this case?
            view = self.centralWidget().reaction_list
            view.reaction_list.blockSignals(True) # block itemChanged while recoloring
            root = view.reaction_list.invisibleRootItem()
            child_count = root.childCount()
            for i in range(child_count):
                item = root.child(i)
                key = item.text(0)
                if key in self.appdata.project.scen_values:
                    value = self.appdata.project.scen_values[key]
                    color = self.compute_color_onoff(value)
                    item.setBackground(ReactionListColumn.Flux, color)
                elif key in self.appdata.project.comp_values:
                    value = self.appdata.project.comp_values[key]
                    color = self.compute_color_onoff(value)
                    item.setBackground(ReactionListColumn.Flux, color)
            view.reaction_list.blockSignals(False)

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
        if idx == ModelTabIndex.Reactions and self.appdata.project.comp_values_type == 0:
            # TODO: coloring of LB/UB columns
            view = self.centralWidget().reaction_list
            view.reaction_list.blockSignals(True) # block itemChanged while recoloring
            root = view.reaction_list.invisibleRootItem()
            child_count = root.childCount()
            for i in range(child_count):
                item = root.child(i)
                key = item.text(0)
                if key in self.appdata.project.scen_values:
                    value = self.appdata.project.scen_values[key]
                    color = self.compute_color_heat(value, low, high)
                    item.setBackground(ReactionListColumn.Flux, color)
                elif key in self.appdata.project.comp_values:
                    value = self.appdata.project.comp_values[key]
                    color = self.compute_color_heat(value, low, high)
                    item.setBackground(ReactionListColumn.Flux, color)
            view.reaction_list.blockSignals(False)

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
        self.centralWidget().kernel_client.execute('%matplotlib inline', store_history=False)
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
                flux = rxn.get_coefficient(metabolite_id) * soldict.get(rxn.id, 0.0)
                if flux < 0:
                    cons.append((rxn, -flux))
                elif flux > 0:
                    prod.append((rxn, flux))
            cons = sorted(cons, key=lambda x: x[1], reverse=True)
            prod = sorted(prod, key=lambda x: x[1], reverse=True)
            for rxn, flux in prod:
                ax.bar(1, flux, width=0.8, bottom=sum_prod, label=rxn.id+": "+rxn.build_reaction_string())
                sum_prod += flux
            for rxn, flux in cons:
                ax.bar(2, flux, width=0.8, bottom=sum_cons, label=rxn.id+": "+rxn.build_reaction_string())
                sum_cons += flux
            ax.set_ylabel('Flux')
            ax.set_title('In/Out fluxes at metabolite ' + metabolite_id)
            ax.legend(bbox_to_anchor=(1, 1), loc="upper left")
            plt.show()
        self.centralWidget().kernel_client.execute('%matplotlib qt', store_history=False)

    def show_console(self):
        print("show model view")
        (x, _) = self.centralWidget().splitter.sizes()
        if x < 50:
            self.show_model_view()
        (_, r) = self.centralWidget().splitter2.getRange(1)
        self.centralWidget().splitter2.moveSplitter(round(r*0.5), 1)

    def show_map_view(self):
        self.show_console()

    def show_model_view(self):
        (_, r) = self.centralWidget().splitter.getRange(1)
        self.centralWidget().splitter.moveSplitter(round(r*0.5), 1)

    def clear_status_bar(self):
        self.solver_status_display.setText("")
        self.solver_status_symbol.setText("")

    def set_status_optimal(self):
        self.solver_status_symbol.setStyleSheet("color: green; font-weight: bold")
        self.solver_status_symbol.setText("\u2713")

    def set_status_infeasible(self):
        self.solver_status_symbol.setStyleSheet("color: red; font-weight: bold")
        self.solver_status_symbol.setText("\u2717")

    def set_status_unknown(self):
        self.solver_status_symbol.setStyleSheet("color: black")
        self.solver_status_symbol.setText("?")

def my_mean(value):
    if isinstance(value, float):
        return value
    else:
        (vl, vh) = value
        return (vl+vh)/2
