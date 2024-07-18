"""The central widget"""

import numpy
from enum import IntEnum
import cobra
from qtconsole.inprocess import QtInProcessKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtpy.QtCore import Qt, Signal, Slot, QSignalBlocker
from qtpy.QtGui import QColor, QBrush
from qtpy.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSplitter,
                            QTabWidget, QVBoxLayout, QWidget, QAction, QApplication, QComboBox, QFrame)

from cnapy.appdata import AppData, CnaMap, ModelItemType, parse_scenario
from cnapy.gui_elements.map_view import MapView
from cnapy.gui_elements.escher_map_view import EscherMapView
from cnapy.gui_elements.metabolite_list import MetaboliteList
from cnapy.gui_elements.gene_list import GeneList
from cnapy.gui_elements.mode_navigator import ModeNavigator
from cnapy.gui_elements.model_info import ModelInfo
from cnapy.gui_elements.scenario_tab import ScenarioTab
from cnapy.gui_elements.reactions_list import ReactionList, ReactionListColumn
from cnapy.utils import SignalThrottler

class ModelTabIndex(IntEnum):
    Reactions = 0
    Metabolites = 1
    Genes = 2
    Scenario = 3
    Model = 4

class CentralWidget(QWidget):
    """The PyNetAnalyzer central widget"""

    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        self.appdata: AppData = parent.appdata
        self.map_counter = 0

        searchbar_layout = QHBoxLayout()
        self.searchbar = QLineEdit()
        self.searchbar.setPlaceholderText("Enter search term")
        self.searchbar.setClearButtonEnabled(True)
        searchbar_layout.addWidget(self.searchbar)
        searchbar_layout.addSpacing(1)
        self.search_annotations = QCheckBox("+Annotations")
        self.search_annotations.setChecked(False)
        searchbar_layout.addWidget(self.search_annotations)
        line = QFrame()
        line.setFrameShape(QFrame.VLine)
        line.setFrameShadow(QFrame.Sunken)
        searchbar_layout.addWidget(line)
        searchbar_layout.addSpacing(10)
        self.model_item_history = QComboBox()
        self.model_item_history.setToolTip("Recently viewed model items")
        self.model_item_history.activated.connect(self.select_item_from_history)
        self.model_item_history.setMaxCount(30)
        self.model_item_history.setMinimumContentsLength(25)
        self.model_item_history.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        searchbar_layout.addWidget(self.model_item_history)
        model_item_history_clear = QPushButton("Clear")
        model_item_history_clear.setFixedWidth(model_item_history_clear.fontMetrics().horizontalAdvance("Clear") + 10)
        searchbar_layout.addWidget(model_item_history_clear)
        model_item_history_clear.clicked.connect(self.clear_model_item_history)

        self.throttler = SignalThrottler(300)
        self.searchbar.textChanged.connect(self.throttler.throttle)
        self.throttler.triggered.connect(self.update_selected)
        self.search_annotations.clicked.connect(self.update_selected)

        self.tabs = QTabWidget()
        self.reaction_list = ReactionList(self)
        self.metabolite_list = MetaboliteList(self)
        self.scenario_tab = ScenarioTab(self)
        self.gene_list = GeneList(self)
        self.model_info = ModelInfo(self.appdata)
        self.tabs.addTab(self.reaction_list, "Reactions")
        self.tabs.addTab(self.metabolite_list, "Metabolites")
        self.tabs.addTab(self.gene_list, "Genes")
        self.tabs.addTab(self.scenario_tab, "Scenario")
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
        self.kernel_client.execute('import matplotlib.pyplot as plt', store_history=False)
        # Maybe add selection for inline or separate Qt window plotting in configure menu:
        # "Show plots in separate window" - Checkbox
        # self.kernel_client.execute('%matplotlib inline')
        self.kernel_client.execute('%matplotlib qt', store_history=False)
        self.kernel_client.execute(
            "%config InlineBackend.figure_format = 'svg'", store_history=False)
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
        layout.addItem(searchbar_layout)
        layout.addWidget(self.splitter)
        self.setLayout(layout)
        margins = self.layout().contentsMargins()
        margins.setBottom(0) # otherwise the distance to the status bar appears too large
        self.layout().setContentsMargins(margins)

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
        self.metabolite_list.metabolite_mask.metaboliteChanged.connect(
                self.reaction_list.reaction_mask.update_reaction_string)
        self.metabolite_list.metabolite_mask.metaboliteDeleted.connect(
                self.reaction_list.reaction_mask.update_reaction_string)
        self.metabolite_list.metabolite_mask.metaboliteDeleted.connect(
                self.handle_changed_metabolite)
        self.metabolite_list.metabolite_mask.metaboliteDeleted.connect(
                self.remove_top_item_history_entry)
        self.gene_list.geneChanged.connect(
            self.handle_changed_gene)
        self.gene_list.jumpToReaction.connect(self.jump_to_reaction)
        self.gene_list.jumpToMetabolite.connect(self.jump_to_metabolite)
        self.gene_list.computeInOutFlux.connect(self.in_out_fluxes)
        self.model_info.globalObjectiveChanged.connect(self.handle_changed_global_objective)
        self.scenario_tab.objectiveSetupChanged.connect(self.handle_changed_objective_setup)
        self.scenario_tab.scenarioChanged.connect(self.parent.update_scenario_file_name)
        self.map_tabs.tabCloseRequested.connect(self.delete_map)
        self.mode_navigator.changedCurrentMode.connect(self.update_mode)
        self.mode_navigator.modeNavigatorClosed.connect(self.update)
        self.mode_navigator.reaction_participation_button.clicked.connect(self.reaction_participation)

        self.mode_normalization_reaction = ""

        self.update()

    def fit_mapview(self):
        if isinstance(self.map_tabs.currentWidget(), MapView):
            self.map_tabs.currentWidget().fit()

    def show_bottom_of_console(self):
        (_, r) = self.splitter2.getRange(1)
        self.splitter2.moveSplitter(r//2, 1)

        vSB = self.console.children()[2].verticalScrollBar()
        max_scroll = vSB.maximum()
        vSB.setValue(max_scroll-100)

    def handle_changed_reaction(self, previous_id: str, reaction: cobra.Reaction):
        self.parent.unsaved_changes()
        reaction_has_box = False
        escher_map_present = False
        for mmap in self.appdata.project.maps:
            if previous_id in self.appdata.project.maps[mmap]["boxes"].keys():
                self.appdata.project.maps[mmap]["boxes"][reaction.id] = self.appdata.project.maps[mmap]["boxes"].pop(
                    previous_id)
                reaction_has_box = True
            if self.appdata.project.maps[mmap].get('view', '') == "escher":
                escher_map_present = True
        if reaction_has_box or escher_map_present:
            self.update_reaction_on_maps(previous_id, reaction.id, reaction_has_box, escher_map_present)
        if reaction.id != previous_id:
            self.appdata.project.reaction_ids.replace_entry(previous_id, reaction.id)
        self.update_item_in_history(previous_id, reaction.id, reaction.name, ModelItemType.Reaction)

    def handle_deleted_reaction(self, reaction: cobra.Reaction):
        self.appdata.project.cobra_py_model.remove_reactions(
            [reaction], remove_orphans=True)
        self.appdata.project.scen_values.pop(reaction.id, None)
        self.appdata.project.scen_values.objective_coefficients.pop(reaction.id, None)
        self.remove_top_item_history_entry()

        self.parent.unsaved_changes()
        for mmap in self.appdata.project.maps:
            if reaction.id in self.appdata.project.maps[mmap]["boxes"].keys():
                self.appdata.project.maps[mmap]["boxes"].pop(reaction.id)
        self.delete_reaction_on_maps(reaction.id)
        self.appdata.project.update_reaction_id_lists()

        if self.appdata.auto_fba:
            self.parent.fba()

    @Slot(cobra.Metabolite, object, str)
    def handle_changed_metabolite(self, metabolite: cobra.Metabolite, affected_reactions, previous_id: str):
        self.parent.unsaved_changes()
        for reaction in affected_reactions: # only updates CNApy maps
            self.update_reaction_on_maps(reaction.id, reaction.id)
        for idx in range(0, self.map_tabs.count()):
            m = self.map_tabs.widget(idx)
            if isinstance(m, EscherMapView):
                m.change_metabolite_id(previous_id, metabolite.id)
        self.update_item_in_history(previous_id, metabolite.id, metabolite.name, ModelItemType.Metabolite)

    def handle_changed_gene(self, previous_id: str, gene: cobra.Gene):
        self.parent.unsaved_changes()
        # TODO update only relevant reaction boxes on maps
        self.update_maps()
        self.update_item_in_history(previous_id, gene.id, gene.name, ModelItemType.Gene)

    @Slot()
    def handle_changed_global_objective(self):
        self.parent.unsaved_changes()
        if self.appdata.auto_fba and not self.appdata.project.scen_values.use_scenario_objective:
            self.parent.fba()

    @Slot()
    def handle_changed_objective_setup(self):
        if self.appdata.auto_fba:
            self.parent.fba()

    def shutdown_kernel(self):
        self.console.kernel_client.stop_channels()
        self.console.kernel_manager.shutdown_kernel()

    def switch_to_reaction(self, reaction: str):
        with QSignalBlocker(self.tabs): # set_current_item will update
            self.tabs.setCurrentIndex(ModelTabIndex.Reactions)
        if self.tabs.width() == 0:
            (left, _) = self.splitter.sizes()
            self.splitter.setSizes([left, 1])
        self.reaction_list.set_current_item(reaction)

    def minimize_reaction(self, reaction: str):
        self.parent.fba_optimize_reaction(reaction, mmin=True)

    def maximize_reaction(self, reaction: str):
        self.parent.fba_optimize_reaction(reaction, mmin=False)

    @Slot(str)
    def set_scen_value(self, reaction: str):
        self.appdata.set_comp_value_as_scen_value(reaction)
        self.update()

    def update_reaction_value(self, reaction: str, value: str, update_reaction_list=True):
        if value == "":
            self.appdata.scen_values_pop(reaction)
            self.appdata.project.comp_values.pop(reaction, None)
        else:
            self.appdata.scen_values_set(reaction, parse_scenario(value))
        if update_reaction_list:
            self.reaction_list.update(rebuild=False)

    def update_reaction_maps(self, _reaction: str):
        self.parent.unsaved_changes()
        self.reaction_list.reaction_mask.update_state()

    def handle_mapChanged(self, _reaction: str):
        self.parent.unsaved_changes()

    def tabs_changed(self, idx):
        if idx == ModelTabIndex.Reactions:
            self.reaction_list.update()
        elif idx == ModelTabIndex.Metabolites:
            self.metabolite_list.update()
        elif idx == ModelTabIndex.Genes:
            self.gene_list.update()
        elif idx == ModelTabIndex.Scenario:
            self.scenario_tab.update()
        elif idx == ModelTabIndex.Model:
            self.model_info.update()

    def connect_map_view_signals(self, mmap: MapView):
        mmap.switchToReactionMask.connect(self.switch_to_reaction)
        mmap.minimizeReaction.connect(self.minimize_reaction)
        mmap.maximizeReaction.connect(self.maximize_reaction)
        mmap.setScenValue.connect(self.set_scen_value)
        mmap.reactionValueChanged.connect(self.update_reaction_value)
        mmap.reactionRemoved.connect(self.update_reaction_maps)
        mmap.reactionAdded.connect(self.update_reaction_maps)
        mmap.mapChanged.connect(self.handle_mapChanged)

    def connect_escher_map_view_signals(self, mmap: EscherMapView):
        mmap.cnapy_bridge.reactionValueChanged.connect(self.update_reaction_value)
        mmap.cnapy_bridge.switchToReactionMask.connect(self.switch_to_reaction)
        mmap.cnapy_bridge.jumpToMetabolite.connect(self.jump_to_metabolite)

    @Slot()
    def add_map(self, base_name="Map", escher=False):
        if base_name == "Map" or (base_name in self.appdata.project.maps.keys()):
            while True:
                name = base_name + " " + str(self.map_counter)
                if name not in self.appdata.project.maps.keys():
                    break
                self.map_counter += 1
        else:
            name = base_name
        m = CnaMap(name)
        self.appdata.project.maps[name] = m
        if escher:
            mmap: EscherMapView = EscherMapView(self, name)
            self.connect_escher_map_view_signals(mmap)
            self.appdata.project.maps[name][EscherMapView] = mmap
            self.appdata.project.maps[name]['view'] = 'escher'
            self.appdata.project.maps[name]['pos'] = '{"x":0,"y":0}'
            self.appdata.project.maps[name]['zoom'] = '1'
            # mmap.loadFinished.connect(self.finish_add_escher_map)
            # mmap.cnapy_bridge.reactionValueChanged.connect(self.update_reaction_value) # connection is not made?!
            # self.appdata.qapp.processEvents() # does not help
            idx = self.map_tabs.addTab(mmap, m["name"])
        else:
            mmap = MapView(self.appdata, self, name)
            self.connect_map_view_signals(mmap)
            idx = self.map_tabs.addTab(mmap, m["name"])
            self.update_maps() # only update mmap?
        self.map_tabs.setCurrentIndex(idx)
        self.parent.unsaved_changes()

        return name, idx

    def delete_map(self, idx: int):
        name = self.map_tabs.tabText(idx)
        diag = ConfirmMapDeleteDialog(self, idx, name)
        diag.exec()

    def update_selected(self):
        string = self.searchbar.text()

        idx = self.tabs.currentIndex()
        map_idx = self.map_tabs.currentIndex()

        with_annotations = self.search_annotations.isChecked() and self.search_annotations.isEnabled()
        QApplication.setOverrideCursor(Qt.BusyCursor)
        QApplication.processEvents() # to put the change above into effect
        if idx == ModelTabIndex.Reactions:
            found_ids = self.reaction_list.update_selected(string, with_annotations)
            found_reaction_ids = found_ids
        elif idx == ModelTabIndex.Metabolites:
            found_ids = self.metabolite_list.update_selected(string, with_annotations)
            if map_idx >= 0:
                found_reaction_ids = []
                for found_id in found_ids:
                    metabolite = self.appdata.project.cobra_py_model.metabolites.get_by_id(found_id)
                    found_reaction_ids += [x.id for x in metabolite.reactions]
            else:
                found_reaction_ids = found_ids
        elif idx == ModelTabIndex.Genes:
            found_ids = self.gene_list.update_selected(string, with_annotations)
            if map_idx >= 0:
                found_reaction_ids = []
                for found_id in found_ids:
                    gene = self.appdata.project.cobra_py_model.genes.get_by_id(found_id)
                    found_reaction_ids += [x.id for x in gene.reactions]
            else:
                found_reaction_ids = found_ids
        else:
            if len(string) == 0:
                # needed to reset selection on map
                found_reaction_ids = self.appdata.project.cobra_py_model.reactions.list_attr("id")
            else:
                QApplication.restoreOverrideCursor()
                return

        if map_idx >= 0:
            m = self.map_tabs.widget(map_idx)
            if isinstance(m, EscherMapView):
                m.update_selected(string)
            else:
                m.update_selected(found_reaction_ids)
        QApplication.restoreOverrideCursor()

    def update_mode(self):
        if self.mode_navigator.mode_type <= 1:
            if len(self.appdata.project.modes) > self.mode_navigator.current:
                values = self.appdata.project.modes[self.mode_navigator.current]
                if self.mode_navigator.mode_type == 0 and not self.appdata.project.modes.is_integer_vector_rounded(
                    self.mode_navigator.current, self.appdata.rounding):
                    # normalize non-integer EFM for better display
                    mean = sum(abs(v) for v in values.values())/len(values)
                    for r,v in values.items():
                        values[r] = v/mean
                if self.mode_normalization_reaction != "":
                    if self.mode_normalization_reaction in values.keys():
                        normalization_value = values[self.mode_normalization_reaction]
                        if normalization_value != 0.0:
                            for r,v in values.items():
                                values[r] = v/normalization_value

                # set values
                self.appdata.project.comp_values.clear()
                self.parent.clear_status_bar()
                for i in values:
                    if self.mode_navigator.mode_type == 1:
                        if values[i] < 0:
                            values[i] = 0.0 # display KOs as zero flux
                    self.appdata.project.comp_values[i] = (values[i], values[i])
                self.appdata.project.comp_values_type = 0

            self.appdata.modes_coloring = True
            self.update()
            self.appdata.modes_coloring = False

        elif self.mode_navigator.mode_type == 2:
            if len(self.appdata.project.modes) > self.mode_navigator.current:
                # clear previous coloring
                self.appdata.project.comp_values.clear()
                self.parent.clear_status_bar()
                self.appdata.project.comp_values_type = 0
                # Set values
                bnd_dict = self.appdata.project.modes[self.mode_navigator.current]
                for k,v in bnd_dict.items():
                    if numpy.any(numpy.isnan(v)):
                        self.appdata.project.comp_values[k] = (0,0)
                    else:
                        mod_bnds = self.appdata.project.cobra_py_model.reactions.get_by_id(k).bounds
                        self.appdata.project.comp_values[k] = (numpy.max((v[0],mod_bnds[0])),numpy.min((v[1],mod_bnds[1])))
                self.appdata.modes_coloring = True
                self.update()
                self.appdata.modes_coloring = False
                idx = self.appdata.window.centralWidget().tabs.currentIndex()
                if idx == ModelTabIndex.Reactions and self.appdata.project.comp_values_type == 0:
                    view = self.appdata.window.centralWidget().reaction_list
                    view.reaction_list.blockSignals(True) # block itemChanged while recoloring
                    root = view.reaction_list.invisibleRootItem()
                    child_count = root.childCount()
                    for i in range(child_count):
                        item = root.child(i)
                        if item.text(0) in bnd_dict:
                            v = bnd_dict[item.text(0)]
                            if numpy.any(numpy.isnan(v)):
                                item.setBackground(ReactionListColumn.Flux, self.appdata.special_color_1)
                            elif (v[0]<0 and v[1]>=0) or (v[0]<=0 and v[1]>0):
                                item.setBackground(ReactionListColumn.Flux, self.appdata.special_color_2)
                            elif v[0] == 0.0 and v[1] == 0.0:
                                item.setBackground(ReactionListColumn.Flux, QColor.fromRgb(255, 0, 0))
                            elif (v[0]<0 and v[1]<0) or (v[0]>0 and v[1]>0):
                                item.setBackground(ReactionListColumn.Flux, self.appdata.special_color_1)
                        else:
                            item.setBackground(ReactionListColumn.Flux, QColor.fromRgb(255, 255, 255))
                    view.reaction_list.blockSignals(False)
                idx = self.appdata.window.centralWidget().map_tabs.currentIndex()
                if idx < 0:
                    return
                name = self.appdata.window.centralWidget().map_tabs.tabText(idx)
                view = self.appdata.window.centralWidget().map_tabs.widget(idx)
                for key in self.appdata.project.maps[name]["boxes"]:
                    if key in bnd_dict:
                        v = bnd_dict[key]
                        if numpy.any(numpy.isnan(v)):
                            view.reaction_boxes[key].set_color(self.appdata.special_color_1)
                        elif (v[0]<0 and v[1]>=0) or (v[0]<=0 and v[1]>0):
                            view.reaction_boxes[key].set_color(self.appdata.special_color_2)
                        elif v[0] == 0.0 and v[1] == 0.0:
                            view.reaction_boxes[key].set_color(QColor.fromRgb(255, 0, 0))
                        elif (v[0]<0 and v[1]<0) or (v[0]>0 and v[1]>0):
                            view.reaction_boxes[key].set_color(self.appdata.special_color_1)
                    else:
                        view.reaction_boxes[key].set_color(QColor.fromRgb(255, 255, 255))
                if self.appdata.window.sd_sols and self.appdata.window.sd_sols.__weakref__: # if dialog exists
                    self.mode_navigator.current
                    for i in range(self.appdata.window.sd_sols.sd_table.rowCount()):
                        if self.mode_navigator.current == int(self.appdata.window.sd_sols.sd_table.item(i,0).text())-1:
                            self.appdata.window.sd_sols.sd_table.item(i,0).setBackground(QBrush(QColor(230,230,230)))
                            self.appdata.window.sd_sols.sd_table.item(i,1).setBackground(QBrush(QColor(230,230,230)))
                            if self.appdata.window.sd_sols.sd_table.columnCount() == 3:
                                self.appdata.window.sd_sols.sd_table.item(i,2).setBackground(QBrush(QColor(230,230,230)))
                        else:
                            self.appdata.window.sd_sols.sd_table.item(i,0).setBackground(QBrush(QColor(255, 255, 255)))
                            self.appdata.window.sd_sols.sd_table.item(i,1).setBackground(QBrush(QColor(255, 255, 255)))
                            if self.appdata.window.sd_sols.sd_table.columnCount() == 3:
                                self.appdata.window.sd_sols.sd_table.item(i,2).setBackground(QBrush(QColor(255, 255, 255)))
        self.mode_navigator.current_flux_values = self.appdata.project.comp_values.copy()

    def reaction_participation(self):
        self.appdata.project.comp_values.clear()
        self.parent.clear_status_bar()
        if self.appdata.window.centralWidget().mode_navigator.mode_type <=1:
            relative_participation = numpy.sum(self.appdata.project.modes.fv_mat[self.mode_navigator.selection, :] != 0, axis=0)/self.mode_navigator.num_selected
            if isinstance(relative_participation, numpy.matrix): # numpy.sum returns a matrix with one row when fv_mat is scipy.sparse
                relative_participation = relative_participation.A1 # flatten into 1D array
            self.appdata.project.comp_values = {r: (relative_participation[i], relative_participation[i]) for i,r in enumerate(self.appdata.project.modes.reac_id)}
        elif self.appdata.window.centralWidget().mode_navigator.mode_type == 2:
            reacs = self.appdata.project.cobra_py_model.reactions.list_attr('id')
            abund = [0 for _ in reacs]
            for i,r in enumerate(reacs):
                for s in [self.appdata.project.modes[l] for l,t in enumerate(self.mode_navigator.selection) if t]:
                    if r in s:
                        if not numpy.any(numpy.isnan(s[r])) or numpy.all((s[r] == 0)):
                            abund[i] += 1
            relative_participation = [a/self.mode_navigator.num_selected for a in abund]
            self.appdata.project.comp_values = {r: (p,p) for r,p in zip(reacs,relative_participation)}
        if isinstance(relative_participation, numpy.matrix): # numpy.sum returns a matrix with one row when fv_mat is scipy.sparse
            relative_participation = relative_participation.A1 # flatten into 1D array
        self.appdata.project.comp_values_type = 0
        self.update()
        self.parent.set_heaton()

    def update(self, rebuild_all_tabs=False):
        # use rebuild_all_tabs=True to rebuild all tabs when the model changes
        if len(self.appdata.project.modes) == 0:
            self.mode_navigator.hide()
            self.mode_navigator.current = 0
        else:
            self.mode_navigator.show()
            self.mode_navigator.update()

        if rebuild_all_tabs:
                self.reaction_list.update(rebuild=True)
                self.metabolite_list.update()
                self.gene_list.update()
                self.scenario_tab.recreate_scenario_items_needed = True
                self.scenario_tab.update()
                self.model_info.update()
        else:
            idx = self.tabs.currentIndex()
            if idx == ModelTabIndex.Reactions:
                self.reaction_list.update()
            elif idx == ModelTabIndex.Metabolites:
                self.metabolite_list.update()
            elif idx == ModelTabIndex.Genes:
                self.gene_list.update()
            elif idx == ModelTabIndex.Scenario:
                self.scenario_tab.update()
            elif idx == ModelTabIndex.Model:
                self.model_info.update()

        idx = self.map_tabs.currentIndex()
        if idx >= 0:
            m = self.map_tabs.widget(idx)
            m.update()

        self.__recolor_map()

    def update_map(self, idx):
        m = self.map_tabs.widget(idx)
        if m is not None:
            m.update()
        self.__recolor_map()

    def update_reaction_on_maps(self, old_reaction_id: str, new_reaction_id: str,
                                update_cnapy_maps:bool=True, update_escher_maps:bool=False):
        for idx in range(0, self.map_tabs.count()):
            m = self.map_tabs.widget(idx)
            if update_cnapy_maps and isinstance(m, MapView):
                m.update_reaction(old_reaction_id, new_reaction_id)
            elif update_escher_maps and isinstance(m, EscherMapView):
                if old_reaction_id != new_reaction_id:
                    m.change_reaction_id(old_reaction_id, new_reaction_id)
                else:
                    m.update_reaction_stoichiometry(old_reaction_id)

    def delete_reaction_on_maps(self, reation_id: str):
        for idx in range(0, self.map_tabs.count()):
            m = self.map_tabs.widget(idx)
            if isinstance(m, MapView):
                m.delete_box(reation_id)
            else:
                m.delete_reaction(reation_id)

    def update_maps(self):
        for idx in range(0, self.map_tabs.count()):
            m = self.map_tabs.widget(idx)
            m.update()
        self.__recolor_map()

    def jump_to_map(self, identifier: str, reaction: str):
        for idx in range(0, self.map_tabs.count()):
            name = self.map_tabs.tabText(idx)
            if name == identifier:
                m = self.map_tabs.widget(idx)
                self.map_tabs.setCurrentIndex(idx)

                m.update()
                m.focus_reaction(reaction)
                self.__recolor_map()
                m.highlight_reaction(reaction)
                break

    def reaction_selected(self, reac_id: str):
        for idx in range(0, self.map_tabs.count()):
            self.map_tabs.widget(idx).select_single_reaction(reac_id)

    def set_onoff(self):
        idx = self.tabs.currentIndex()
        if idx == ModelTabIndex.Reactions and self.appdata.project.comp_values_type == 0:
            self.__set_onoff_reaction_list()
        self.__set_onoff_map()

    def __set_onoff_reaction_list(self):
        # do coloring of LB/UB columns in this case?
        view = self.reaction_list
        # block itemChanged while recoloring
        view.reaction_list.blockSignals(True)
        root = view.reaction_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            key = item.text(0)
            if key in self.appdata.project.scen_values:
                value = self.appdata.project.scen_values[key]
                color = self.appdata.compute_color_onoff(value)
                item.setBackground(ReactionListColumn.Flux, color)
            elif key in self.appdata.project.comp_values:
                value = self.appdata.project.comp_values[key]
                color = self.appdata.compute_color_onoff(value)
                item.setBackground(ReactionListColumn.Flux, color)
        view.reaction_list.blockSignals(False)

    def __set_onoff_map(self):
        idx = self.map_tabs.currentIndex()
        if idx < 0:
            return
        name = self.map_tabs.tabText(idx)
        map_view = self.map_tabs.widget(idx)
        for key in self.appdata.project.maps[name]["boxes"]:
            if key in self.appdata.project.scen_values:
                value = self.appdata.project.scen_values[key]
                color = self.appdata.compute_color_onoff(value)
                map_view.reaction_boxes[key].set_color(color)
            elif key in self.appdata.project.comp_values:
                value = self.appdata.project.comp_values[key]
                color = self.appdata.compute_color_onoff(value)
                map_view.reaction_boxes[key].set_color(color)

    def set_heaton(self):
        (low, high) = self.appdata.low_and_high()
        idx = self.tabs.currentIndex()
        if idx == ModelTabIndex.Reactions and self.appdata.project.comp_values_type == 0:
            self.__set_heaton_reaction_list(low,high)
        self.__set_heaton_map(low,high)

    def __set_heaton_reaction_list(self, low, high):
        # TODO: coloring of LB/UB columns
        view = self.reaction_list
        # block itemChanged while recoloring
        view.reaction_list.blockSignals(True)
        root = view.reaction_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            key = item.text(0)
            if key in self.appdata.project.scen_values:
                value = self.appdata.project.scen_values[key]
                color = self.appdata.compute_color_heat(value, low, high)
                item.setBackground(ReactionListColumn.Flux, color)
            elif key in self.appdata.project.comp_values:
                value = self.appdata.project.comp_values[key]
                color = self.appdata.compute_color_heat(value, low, high)
                item.setBackground(ReactionListColumn.Flux, color)
        view.reaction_list.blockSignals(False)

    def set_heaton_map(self):
        (low, high) = self.appdata.low_and_high()
        self.__set_heaton_map(low, high)

    def __set_heaton_map(self, low, high):
        idx = self.map_tabs.currentIndex()
        if idx < 0:
            return
        name = self.map_tabs.tabText(idx)
        map_view = self.map_tabs.widget(idx)
        for key in self.appdata.project.maps[name]["boxes"]:
            if key in self.appdata.project.scen_values:
                value = self.appdata.project.scen_values[key]
                color = self.appdata.compute_color_heat(value, low, high)
                map_view.reaction_boxes[key].set_color(color)
            elif key in self.appdata.project.comp_values:
                value = self.appdata.project.comp_values[key]
                color = self.appdata.compute_color_heat(value, low, high)
                map_view.reaction_boxes[key].set_color(color)

    def __recolor_map(self):
        ''' recolor the map based on the activated coloring mode '''
        if self.parent.heaton_action.isChecked():
            self.set_heaton_map()
        elif self.parent.onoff_action.isChecked():
            self.__set_onoff_map()

    def jump_to_metabolite(self, metabolite: str):
        self.tabs.setCurrentIndex(ModelTabIndex.Metabolites)
        m = self.tabs.widget(ModelTabIndex.Metabolites)
        m.set_current_item(metabolite)

    def jump_to_reaction(self, reaction: str):
        self.tabs.setCurrentIndex(ModelTabIndex.Reactions)
        m = self.tabs.widget(ModelTabIndex.Reactions)
        m.set_current_item(reaction)

    def jump_to_gene(self, gene: str):
        self.tabs.setCurrentIndex(ModelTabIndex.Genes)
        m = self.tabs.widget(ModelTabIndex.Genes)
        m.set_current_item(gene)

    @Slot(int)
    def select_item_from_history(self, index: int):
        item_id, item_type = self.model_item_history.itemData(index)
        if item_type == ModelItemType.Reaction:
            self.jump_to_reaction(item_id)
        elif item_type == ModelItemType.Metabolite:
            self.jump_to_metabolite(item_id)
        elif item_type == ModelItemType.Gene:
            self.jump_to_gene(item_id)

    def add_model_item_to_history(self, item_id: str, item_name: str, item_type: ModelItemType):
        item_data = [item_id, item_type]
        index = self.model_item_history.findData(item_data)
        with QSignalBlocker(self.model_item_history):
            if index >= 0:
                index = self.model_item_history.removeItem(index)
            self.model_item_history.insertItem(0, item_id + " (" + ModelItemType(item_type).name + ")", item_data)
            self.model_item_history.setItemData(0, item_name, Qt.ToolTipRole)
            self.model_item_history.setCurrentIndex(0)

    def update_item_in_history(self, previous_id: str, new_id: str, new_name: str, item_type: ModelItemType):
        index = self.model_item_history.findData([previous_id, item_type])
        if index >= 0:
            self.model_item_history.setItemData(index, [new_id, item_type])
            self.model_item_history.setItemText(index, new_id + " (" + ModelItemType(item_type).name + ")")

    def remove_top_item_history_entry(self):
        # can be used when a reaction or metabolite is deleted because
        # in that case the item which is being deleted is at the top
        with QSignalBlocker(self.model_item_history):
            self.model_item_history.removeItem(0)
            self.model_item_history.setCurrentIndex(-1)

    @Slot()
    def clear_model_item_history(self):
        with QSignalBlocker(self.model_item_history):
            self.model_item_history.clear()

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
        self.lable = QLabel("Do you really want to delete this map?")
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
