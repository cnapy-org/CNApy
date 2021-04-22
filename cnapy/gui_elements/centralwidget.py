"""The central widget"""
from ast import literal_eval as make_tuple

import cobra
from cobra.manipulation.delete import prune_unused_metabolites
from qtconsole.inprocess import QtInProcessKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (QDialog, QLabel, QLineEdit, QPushButton, QSplitter,
                            QTabWidget, QVBoxLayout, QWidget)

from cnapy.cnadata import CnaData, CnaMap
from cnapy.gui_elements.map_view import MapView
from cnapy.gui_elements.metabolite_list import MetaboliteList
from cnapy.gui_elements.modenavigator import ModeNavigator
from cnapy.gui_elements.reactions_list import ReactionList
from cnapy.utils import SignalThrottler


class CentralWidget(QWidget):
    """The PyNetAnalyzer central widget"""

    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        self.appdata: CnaData = parent.appdata
        self.map_counter = 0
        self.searchbar = QLineEdit()
        self.searchbar.setPlaceholderText("Enter search term")

        self.throttler = SignalThrottler(300)
        self.searchbar.textChanged.connect(self.throttler.throttle)
        self.throttler.triggered.connect(self.update_selected)

        self.tabs = QTabWidget()
        self.reaction_list = ReactionList(self.appdata)
        self.metabolite_list = MetaboliteList(self.appdata)
        self.tabs.addTab(self.reaction_list, "Reactions")
        self.tabs.addTab(self.metabolite_list, "Metabolites")

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
        self.mode_navigator = ModeNavigator(self.appdata)
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
        self.map_tabs.tabCloseRequested.connect(self.delete_map)
        self.mode_navigator.changedCurrentMode.connect(self.update_mode)
        self.mode_navigator.modeNavigatorClosed.connect(self.update)

        self.update()

    def fit_mapview(self):
        self.map_tabs.currentWidget().fit()

    def scroll_down(self):
        vSB = self.console.children()[2].verticalScrollBar()
        max_scroll = vSB.maximum()
        vSB.setValue(max_scroll-100)

    def handle_changed_reaction(self, old_id: str, reaction: cobra.Reaction):
        self.parent.unsaved_changes()
        for mmap in self.appdata.project.maps:
            if old_id in self.appdata.project.maps[mmap]["boxes"].keys():
                self.appdata.project.maps[mmap]["boxes"][reaction.id] = self.appdata.project.maps[mmap]["boxes"].pop(
                    old_id)

        # TODO update only relevant reaction boxes on maps
        self.update_maps()

    def handle_deleted_reaction(self, reaction: cobra.Reaction):
        self.appdata.project.cobra_py_model.remove_reactions(
            [reaction], remove_orphans=True)

        self.parent.unsaved_changes()
        for mmap in self.appdata.project.maps:
            if reaction.id in self.appdata.project.maps[mmap]["boxes"].keys():
                self.appdata.project.maps[mmap]["boxes"].pop(reaction.id)

        # TODO update only relevant reaction boxes on maps
        self.update_maps()

    def handle_changed_metabolite(self, old_id: str, metabolite: cobra.Metabolite):
        self.parent.unsaved_changes()
        # TODO update only relevant reaction boxes on maps
        self.update_maps()

    def shutdown_kernel(self):
        self.console.kernel_client.stop_channels()
        self.console.kernel_manager.shutdown_kernel()

    def switch_to_reaction(self, reaction: str):
        self.tabs.setCurrentIndex(0)
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

    def add_map(self):
        while True:
            name = "Map "+str(self.map_counter)
            self.map_counter += 1
            if name not in self.appdata.project.maps.keys():
                break
        m = CnaMap(name)

        self.appdata.project.maps[name] = m
        mmap = MapView(self.appdata, name)
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

        idx = self.map_tabs.currentIndex()
        if idx >= 0:
            m = self.map_tabs.widget(idx)
            m.update_selected(x)

    def update_mode(self):
        if len(self.appdata.project.modes) > self.mode_navigator.current:
            values = self.appdata.project.modes[self.mode_navigator.current]

            # set values
            self.appdata.project.scen_values.clear()
            self.appdata.project.comp_values.clear()
            for i in values:
                self.appdata.project.comp_values[i] = (values[i], values[i])

        self.appdata.modes_coloring = True
        self.update()
        self.appdata.modes_coloring = False

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
        idx = self.map_tabs.currentIndex()
        if idx >= 0:
            m = self.map_tabs.widget(idx)
            m.update()

    def update_map(self, idx):
        m = self.map_tabs.widget(idx)
        if m is not None:
            m.update()

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
        self.scroll_down()


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
