"""The central widget"""
from ast import literal_eval as make_tuple

import numpy
import cobra
from cobra.manipulation.delete import prune_unused_metabolites
from qtconsole.inprocess import QtInProcessKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (QDialog, QLabel, QLineEdit, QPushButton, QSplitter,
                            QTabWidget, QVBoxLayout, QWidget, QAction)

from cnapy.appdata import AppData, CnaMap
from cnapy.gui_elements.map_view import MapView
from cnapy.gui_elements.metabolite_list import MetaboliteList
from cnapy.gui_elements.gene_list import GeneList
from cnapy.gui_elements.mode_navigator import ModeNavigator
from cnapy.gui_elements.model_info import ModelInfo
from cnapy.gui_elements.reactions_list import ReactionList
from cnapy.utils import SignalThrottler


class CentralWidget(QWidget):
    """The PyNetAnalyzer central widget"""

    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        self.appdata: AppData = parent.appdata
        self.map_counter = 0
        self.searchbar = QLineEdit()
        self.searchbar.setPlaceholderText("Enter search term")

        self.throttler = SignalThrottler(300)
        self.searchbar.textChanged.connect(self.throttler.throttle)
        self.throttler.triggered.connect(self.update_selected)

        self.tabs = QTabWidget()
        self.reaction_list = ReactionList(self.appdata)
        self.metabolite_list = MetaboliteList(self.appdata)
        self.gene_list = GeneList(self.appdata)
        self.model_info = ModelInfo(self.appdata)
        self.tabs.addTab(self.reaction_list, "Reactions")
        self.tabs.addTab(self.metabolite_list, "Metabolites")
        self.tabs.addTab(self.gene_list, "Genes")
        self.tabs.addTab(self.model_info, "Model")

        self.map_tabs = QTabWidget()
        self.map_tabs.setTabsClosable(True)
        self.map_tabs.setMovable(True)

        # Create an in-process kernel
        kernel_manager = QtInProcessKernelManager()
        kernel_manager.start_kernel(show_banner=False)
        kernel = kernel_manager.kernel
        kernel.gui = 'qt'

        myglobals = globals()
        myglobals["cna"] = self.parent
        self.kernel_shell = kernel_manager.kernel.shell
        self.kernel_shell.push(myglobals)
        self.kernel_client = kernel_manager.client()
        self.kernel_client.start_channels()

        # Check if client is working
        self.kernel_client.execute('import matplotlib.pyplot as plt')
        self.kernel_client.execute('%matplotlib inline')
        self.kernel_client.execute(
            "%config InlineBackend.figure_format = 'svg'")
        self.console = RichJupyterWidget()
        self.console.kernel_manager = kernel_manager
        self.console.kernel_client = self.kernel_client

        self.splitter = QSplitter()
        self.splitter2 = QSplitter()
        self.splitter2.addWidget(self.map_tabs)
        self.mode_navigator = ModeNavigator(self.appdata, self)
        self.splitter2.addWidget(self.mode_navigator)
        self.splitter2.addWidget(self.console)
        self.splitter2.setOrientation(Qt.Vertical)
        self.splitter.addWidget(self.splitter2)
        self.splitter.addWidget(self.tabs)
        self.console.show()

        layout = QVBoxLayout()
        layout.addWidget(self.searchbar)
        layout.addWidget(self.splitter)
        self.setLayout(layout)

        self.tabs.currentChanged.connect(self.tabs_changed)
        self.reaction_list.jumpToMap.connect(self.jump_to_map)
        self.reaction_list.jumpToMetabolite.connect(self.jump_to_metabolite)
        self.reaction_list.reactionChanged.connect(
            self.handle_changed_reaction)
        self.reaction_list.reactionDeleted.connect(
            self.handle_deleted_reaction)
        self.metabolite_list.metaboliteChanged.connect(
            self.handle_changed_metabolite)
        self.metabolite_list.jumpToReaction.connect(self.jump_to_reaction)
        self.metabolite_list.computeInOutFlux.connect(self.in_out_fluxes)
        self.gene_list.geneChanged.connect(
            self.handle_changed_gene)
        self.gene_list.jumpToReaction.connect(self.jump_to_reaction)
        self.gene_list.jumpToMetabolite.connect(self.jump_to_metabolite)
        print("UUUU")
        self.gene_list.computeInOutFlux.connect(self.in_out_fluxes)
        self.model_info.optimizationDirectionChanged.connect(
            self.handle_changed_optimization_direction)
        self.map_tabs.tabCloseRequested.connect(self.delete_map)
        self.mode_navigator.changedCurrentMode.connect(self.update_mode)
        self.mode_navigator.modeNavigatorClosed.connect(self.update)
        self.mode_navigator.reaction_participation_button.clicked.connect(self.reaction_participation)

        self.update()

    def fit_mapview(self):
        self.map_tabs.currentWidget().fit()

    def show_bottom_of_console(self):
        (_, r) = self.splitter2.getRange(1)
        self.splitter2.moveSplitter(r*0.5, 1)

        vSB = self.console.children()[2].verticalScrollBar()
        max_scroll = vSB.maximum()
        vSB.setValue(max_scroll-100)

    def handle_changed_reaction(self, old_id: str, reaction: cobra.Reaction):
        self.parent.unsaved_changes()
        reaction_has_box = False
        for mmap in self.appdata.project.maps:
            if old_id in self.appdata.project.maps[mmap]["boxes"].keys():
                self.appdata.project.maps[mmap]["boxes"][reaction.id] = self.appdata.project.maps[mmap]["boxes"].pop(
                    old_id)
                reaction_has_box = True
        if reaction_has_box:
            self.update_reaction_on_maps(old_id, reaction.id)

    def handle_deleted_reaction(self, reaction: cobra.Reaction):
        self.appdata.project.cobra_py_model.remove_reactions(
            [reaction], remove_orphans=True)

        self.parent.unsaved_changes()
        for mmap in self.appdata.project.maps:
            if reaction.id in self.appdata.project.maps[mmap]["boxes"].keys():
                self.appdata.project.maps[mmap]["boxes"].pop(reaction.id)

        self.delete_reaction_on_maps(reaction.id)

    def handle_changed_metabolite(self, old_id: str, metabolite: cobra.Metabolite):
        self.parent.unsaved_changes()
        # TODO update only relevant reaction boxes on maps
        self.update_maps()

    def handle_changed_gene(self, old_id: str, gene: cobra.Gene):
        self.parent.unsaved_changes()
        # TODO update only relevant reaction boxes on maps
        self.update_maps()

    def handle_changed_optimization_direction(self, direction: str):
        self.parent.unsaved_changes()

    def shutdown_kernel(self):
        self.console.kernel_client.stop_channels()
        self.console.kernel_manager.shutdown_kernel()

    def switch_to_reaction(self, reaction: str):
        self.tabs.setCurrentIndex(0)
        if self.tabs.width() == 0:
            (left, _) = self.splitter.sizes()
            self.splitter.setSizes([left, 1])
        self.reaction_list.set_current_item(reaction)

    def minimize_reaction(self, reaction: str):
        self.parent.fba_optimize_reaction(reaction, mmin=True)

    def maximize_reaction(self, reaction: str):
        self.parent.fba_optimize_reaction(reaction, mmin=False)

    def update_reaction_value(self, reaction: str, value: str):
        if value == "":
            self.appdata.scen_values_pop(reaction)
            self.appdata.project.comp_values.pop(reaction, None)
        else:
            try:
                x = float(value)
                self.appdata.scen_values_set(reaction, (x, x))
            except ValueError:
                (vl, vh) = make_tuple(value)
                self.appdata.scen_values_set(reaction, (vl, vh))
        self.reaction_list.update()

    def update_reaction_maps(self, _reaction: str):
        self.parent.unsaved_changes()
        self.reaction_list.reaction_mask.update_state()

    def handle_mapChanged(self, _reaction: str):
        self.parent.unsaved_changes()

    def tabs_changed(self, idx):
        if idx == 0:
            self.reaction_list.update()
        elif idx == 1:
            (clean_model, unused_mets) = prune_unused_metabolites(
                self.appdata.project.cobra_py_model)
            self.appdata.project.cobra_py_model = clean_model
            self.metabolite_list.update()
        elif idx == 2:
            self.gene_list.update()
        elif idx == 3:
            self.model_info.update()

    def add_map(self):
        while True:
            name = "Map "+str(self.map_counter)
            self.map_counter += 1
            if name not in self.appdata.project.maps.keys():
                break
        m = CnaMap(name)

        self.appdata.project.maps[name] = m
        mmap = MapView(self.appdata, self, name)
        mmap.switchToReactionMask.connect(self.switch_to_reaction)
        mmap.minimizeReaction.connect(self.minimize_reaction)
        mmap.maximizeReaction.connect(self.maximize_reaction)

        mmap.reactionValueChanged.connect(self.update_reaction_value)
        mmap.reactionRemoved.connect(self.update_reaction_maps)
        mmap.reactionAdded.connect(self.update_reaction_maps)
        mmap.mapChanged.connect(self.handle_mapChanged)
        self.map_tabs.addTab(mmap, m["name"])
        self.update_maps()
        self.map_tabs.setCurrentIndex(len(self.appdata.project.maps))
        self.parent.unsaved_changes()

    def delete_map(self, idx: int):
        name = self.map_tabs.tabText(idx)
        diag = ConfirmMapDeleteDialog(self, idx, name)
        diag.exec()

    def update_selected(self):
        x = self.searchbar.text()
        idx = self.tabs.currentIndex()
        if idx == 0:
            self.reaction_list.update_selected(x)
        if idx == 1:
            self.metabolite_list.update_selected(x)
        if idx == 2:
            self.gene_list.update_selected(x)

        idx = self.map_tabs.currentIndex()
        if idx >= 0:
            m = self.map_tabs.widget(idx)
            m.update_selected(x)

    def update_mode(self):
        if len(self.appdata.project.modes) > self.mode_navigator.current:
            values = self.appdata.project.modes[self.mode_navigator.current]
            if self.mode_navigator.mode_type == 0 and not self.appdata.project.modes.is_integer_vector_rounded(
                self.mode_navigator.current, self.appdata.rounding):
                # normalize non-integer EFM for better display
                mean = sum(abs(v) for v in values.values())/len(values)
                for r,v in values.items():
                    values[r] = v/mean

            # set values
            self.appdata.project.scen_values.clear()
            self.appdata.project.comp_values.clear()
            for i in values:
                if self.mode_navigator.mode_type == 1 and values[i] == -1:
                    values[i] = 0.0 # display cuts as zero flux
                self.appdata.project.comp_values[i] = (values[i], values[i])
            self.appdata.project.comp_values_type = 0

        self.appdata.modes_coloring = True
        self.update()
        self.appdata.modes_coloring = False

    def reaction_participation(self):
        relative_participation = numpy.sum(self.appdata.project.modes.fv_mat[self.mode_navigator.selection, :] != 0, axis=0)/self.mode_navigator.num_selected
        if isinstance(relative_participation, numpy.matrix): # numpy.sum returns a matrix with one row when fv_mat is scipy.sparse
            relative_participation = relative_participation.A1 # flatten into 1D array
        self.appdata.project.comp_values.clear()
        self.appdata.project.comp_values = {r: (relative_participation[i], relative_participation[i]) for i,r in enumerate(self.appdata.project.modes.reac_id)}
        self.appdata.project.comp_values_type = 0
        self.update()
        self.parent.set_heaton()

    def update(self):
        if len(self.appdata.project.modes) == 0:
            self.mode_navigator.hide()
            self.mode_navigator.current = 0
        else:
            self.mode_navigator.show()
            self.mode_navigator.update()

        idx = self.tabs.currentIndex()
        if idx == 0:
            self.reaction_list.update()
        elif idx == 1:
            self.metabolite_list.update()
        elif idx == 2:
            self.gene_list.update()
        elif idx == 3:
            self.model_info.update()

        idx = self.map_tabs.currentIndex()
        if idx >= 0:
            m = self.map_tabs.widget(idx)
            m.update()

        if self.parent.heaton_action.isChecked():
            self.parent.heaton_action.activate(QAction.Trigger)
        elif self.parent.onoff_action.isChecked():
            self.parent.onoff_action.activate(QAction.Trigger)

    def update_map(self, idx):
        m = self.map_tabs.widget(idx)
        if m is not None:
            m.update()

    def update_reaction_on_maps(self, old_reaction_id: str, new_reaction_id: str):
        for idx in range(0, self.map_tabs.count()):
            m = self.map_tabs.widget(idx)
            m.update_reaction(old_reaction_id, new_reaction_id)

    def delete_reaction_on_maps(self, reation_id: str):
        for idx in range(0, self.map_tabs.count()):
            m = self.map_tabs.widget(idx)
            m.delete_box(reation_id)

    def update_maps(self):
        for idx in range(0, self.map_tabs.count()):
            m = self.map_tabs.widget(idx)
            m.update()

    def jump_to_map(self, identifier: str, reaction: str):
        for idx in range(0, self.map_tabs.count()):
            name = self.map_tabs.tabText(idx)
            if name == identifier:
                m = self.map_tabs.widget(idx)
                self.map_tabs.setCurrentIndex(idx)

                m.update()
                m.focus_reaction(reaction)
                m.highlight_reaction(reaction)
                break

    def jump_to_metabolite(self, metabolite: str):
        self.tabs.setCurrentIndex(1)
        m = self.tabs.widget(1)
        m.set_current_item(metabolite)

    def jump_to_reaction(self, reaction: str):
        self.tabs.setCurrentIndex(0)
        m = self.tabs.widget(0)
        m.set_current_item(reaction)

    def in_out_fluxes(self, metabolite):
        self.kernel_client.execute("cna.print_in_out_fluxes('"+metabolite+"')")
        self.show_bottom_of_console()

    broadcastReactionID = Signal(str)

class ConfirmMapDeleteDialog(QDialog):

    def __init__(self, parent, idx: int, name: str):
        super(ConfirmMapDeleteDialog, self).__init__(parent)
        # Create widgets
        self.parent = parent
        self.idx = idx
        self.name = name
        self.lable = QLabel("Do you realy want to delete this map?")
        self.button_yes = QPushButton("Yes delete")
        self.button_no = QPushButton("No!")
        # Create layout and add widgets
        layout = QVBoxLayout()
        layout.addWidget(self.lable)
        layout.addWidget(self.button_yes)
        layout.addWidget(self.button_no)
        # Set dialog layout
        self.setLayout(layout)
        # Add button signals to the slots
        self.button_yes.clicked.connect(self.delete)
        self.button_no.clicked.connect(self.reject)

    def delete(self):
        del self.parent.appdata.project.maps[self.name]
        self.parent.map_tabs.removeTab(self.idx)
        self.parent.reaction_list.reaction_mask.update_state()
        self.parent.parent.unsaved_changes()
        self.accept()
