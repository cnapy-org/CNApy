from ast import literal_eval as make_tuple

from cnapy.cnadata import CnaData, CnaMap
from cnapy.gui_elements.map_view import MapView
from cnapy.gui_elements.metabolite_list import MetaboliteList
from cnapy.gui_elements.modenavigator import ModeNavigator
from cnapy.gui_elements.reactions_list import ReactionList
from qtconsole.inprocess import QtInProcessKernelManager
from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (QDialog, QLabel, QLineEdit, QPushButton, QSplitter,
                            QTabWidget, QVBoxLayout, QWidget)

FIXED_TABS = 2


class CentralWidget(QWidget):
    """The PyNetAnalyzer central widget"""

    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        self.appdata: CnaData = parent.appdata
        self.map_counter = 0
        self.searchbar = QLineEdit()
        self.searchbar.textChanged.connect(self.update_selected)

        self.tabs = QTabWidget()
        self.reaction_list = ReactionList(self.appdata)
        self.metabolite_list = MetaboliteList(self.appdata)
        self.tabs.addTab(self.reaction_list, "Reactions")
        self.tabs.addTab(self.metabolite_list, "Metabolites")

        self.map_tabs = QTabWidget()
        self.map_tabs.setTabsClosable(True)

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
        self.reaction_list.changedModel.connect(self.update)
        self.metabolite_list.changedModel.connect(self.update)
        self.map_tabs.tabCloseRequested.connect(self.delete_map)
        self.mode_navigator.changedCurrentMode.connect(self.update_mode)
        self.mode_navigator.modeNavigatorClosed.connect(self.update)

        self.update()

    def shutdown_kernel(self):
        print('Shutting down kernel...')
        self.console.kernel_client.stop_channels()
        self.console.kernel_manager.shutdown_kernel()

    def switch_to_reaction(self, reaction: str):
        self.tabs.setCurrentIndex(0)
        self.reaction_list.setCurrentItem(reaction)

    def minimize_reaction(self, reaction: str):
        self.parent.fba_optimize_reaction(reaction, min=True)

    def maximize_reaction(self, reaction: str):
        self.parent.fba_optimize_reaction(reaction, min=False)

    def update_reaction_value(self, reaction: str, value: str):
        if value == "":
            self.appdata.project.scen_values.pop(reaction, None)
            self.appdata.project.comp_values.pop(reaction, None)
        else:
            try:
                x = float(value)
                self.appdata.project.scen_values[reaction] = (x, x)
            except:
                (vl, vh) = make_tuple(value)
                self.appdata.project.scen_values[reaction] = (vl, vh)
        self.reaction_list.update()

    def update_reaction_maps(self, reaction: str):
        self.reaction_list.reaction_mask.update_state()

    def tabs_changed(self, idx):
        if idx == 0:
            self.reaction_list.update()
        elif idx == 1:
            self.metabolite_list.update()

    def add_map(self):
        while True:
            name = "Map "+str(self.map_counter)
            self.map_counter += 1
            if name not in self.appdata.project.maps.keys():
                break
        m = CnaMap(name)

        self.appdata.project.maps[name] = m
        map = MapView(self.appdata, name)
        map.switchToReactionDialog.connect(self.switch_to_reaction)
        map.minimizeReaction.connect(self.minimize_reaction)
        map.maximizeReaction.connect(self.maximize_reaction)

        map.reactionValueChanged.connect(self.update_reaction_value)
        map.reactionRemoved.connect(self.update_reaction_maps)
        self.map_tabs.addTab(map, m["name"])
        self.update_maps()
        self.map_tabs.setCurrentIndex(len(self.appdata.project.maps))
        self.reaction_list.reaction_mask.update_state()

    def remove_map_tabs(self):
        for _ in range(0, self.map_tabs.count()):
            self.map_tabs.removeTab(0)

    def delete_map(self, idx: int):
        print("delete map: "+str(idx))
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
        m = self.map_tabs.widget(idx)
        m.update_selected(x)

    def update_mode(self):
        if len(self.appdata.project.modes) > self.mode_navigator.current:
            values = self.appdata.project.modes[self.mode_navigator.current].copy(
            )

            # set values
            self.appdata.project.scen_values.clear()
            self.appdata.project.comp_values.clear()
            for i in values:
                self.appdata.project.comp_values[i] = (values[i], values[i])

        self.update()

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
        m = self.map_tabs.widget(idx)
        if m != None:
            m.update()

    def update_map(self, idx):
        m = self.map_tabs.widget(idx)
        if m != None:
            m.update()

    def update_maps(self):
        print("update_maps", str(self.tabs.count()))
        for idx in range(0, self.map_tabs.count()):
            m = self.map_tabs.widget(idx)
            m.update()

    def recreate_maps(self):
        self.remove_map_tabs()

        for name, map in self.appdata.project.maps.items():
            map = MapView(self.appdata, name)
            map.show()
            map.switchToReactionDialog.connect(self.switch_to_reaction)
            map.minimizeReaction.connect(self.minimize_reaction)
            map.maximizeReaction.connect(self.maximize_reaction)
            map.reactionValueChanged.connect(self.update_reaction_value)
            map.reactionRemoved.connect(self.update_reaction_maps)
            self.map_tabs.addTab(map, name)
            map.update()

    def jump_to_map(self, id: str, reaction: str):
        print("centralwidget::jump_to_map", id, reaction)
        for idx in range(0, self.map_tabs.count()):
            name = self.map_tabs.tabText(idx)
            if name == id:
                m = self.map_tabs.widget(idx)
                self.map_tabs.setCurrentIndex(idx)

                m.update()
                # self.searchbar.setText(reaction)
                m.focus_reaction(reaction)
                m.highlight_reaction(reaction)
                break


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
        print("Delete Map:"+self.name)
        del self.parent.appdata.project.maps[self.name]
        self.parent.map_tabs.removeTab(self.idx)
        self.parent.reaction_list.reaction_mask.update_state()
        self.accept()
