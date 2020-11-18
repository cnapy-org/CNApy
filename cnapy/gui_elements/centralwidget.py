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
                            QTabBar, QTabWidget, QVBoxLayout, QWidget)

FIXED_TABS = 2


class CentralWidget(QWidget):
    """The PyNetAnalyzer central widget"""

    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        self.appdata: CnaData = parent.appdata

        self.searchbar = QLineEdit()
        self.searchbar.textChanged.connect(self.update_selected)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.reaction_list = ReactionList(self.appdata)
        self.metabolite_list = MetaboliteList(self.appdata)
        self.tabs.addTab(self.reaction_list, "Reactions")
        self.tabs.addTab(self.metabolite_list, "Metabolites")
        self.maps: list = []

        # Create an in-process kernel
        kernel_manager = QtInProcessKernelManager()
        kernel_manager.start_kernel(show_banner=False)
        kernel = kernel_manager.kernel
        kernel.gui = 'qt'

        myglobals = globals()
        myglobals["cna"] = self.parent
        kernel_manager.kernel.shell.push(myglobals)
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

        self.add_map_button = QPushButton("add map")
        self.tabs.setCornerWidget(
            self.add_map_button, corner=Qt.TopRightCorner)

        # disable close button on reactions, metabolites and console tab
        self.tabs.tabBar().setTabButton(0, QTabBar.RightSide, None)
        self.tabs.tabBar().setTabButton(1, QTabBar.RightSide, None)

        self.mode_navigator = ModeNavigator(self.appdata)
        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Vertical)
        self.splitter.addWidget(self.searchbar)
        self.splitter.addWidget(self.tabs)
        self.splitter.addWidget(self.mode_navigator)
        self.splitter.addWidget(self.console)
        self.splitter.setCollapsible(0, False)
        self.splitter.setCollapsible(1, False)
        self.console.show()

        layout = QVBoxLayout()
        layout.addWidget(self.splitter)
        self.setLayout(layout)

        self.reaction_list.jumpToMap.connect(self.jump_to_map)
        self.reaction_list.changedModel.connect(self.update)
        self.metabolite_list.changedModel.connect(self.update)
        self.add_map_button.clicked.connect(self.add_map)
        self.tabs.tabCloseRequested.connect(self.delete_map)
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

    def optimize_reaction(self, reaction: str):
        self.parent.fba_optimize_reaction(reaction)

    def update_reaction_value(self, reaction: str, value: str):
        print("update_reaction_value", value)
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

    def add_map(self):
        m = CnaMap("Map")
        self.appdata.project.maps.append(m)
        map = MapView(self.appdata, len(self.appdata.project.maps)-1)
        map.switchToReactionDialog.connect(self.switch_to_reaction)
        map.optimizeReaction.connect(self.optimize_reaction)

        map.reactionValueChanged.connect(self.update_reaction_value)
        self.tabs.addTab(map, m["name"])
        self.update_maps()
        self.tabs.setCurrentIndex(2 + len(self.appdata.project.maps))

    def remove_map_tabs(self):
        for _ in range(FIXED_TABS, self.tabs.count()):
            self.tabs.removeTab(FIXED_TABS)

    def delete_map(self, idx: int):
        diag = ConfirmMapDeleteDialog(self, idx)
        diag.exec()

    def update_selected(self):
        # print("centralwidget::update_selected")

        x = self.searchbar.text()
        idx = self.tabs.currentIndex()
        if idx == 0:
            self.reaction_list.update_selected(x)
        if idx == 1:
            self.metabolite_list.update_selected(x)
        elif idx >= FIXED_TABS:
            m = self.tabs.widget(idx)
            m.update_selected(x)

    def update_mode(self):
        # print("centralwidget::update")
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
        # print("centralwidget::update")
        if len(self.appdata.project.modes) == 0:
            self.mode_navigator.hide()
            self.mode_navigator.current = 0
        else:
            self.mode_navigator.show()
            self.mode_navigator.update()

        self.update_active_tab()

    def update_active_tab(self):
        idx = self.tabs.currentIndex()
        self.update_tab(idx)

    def update_maps(self):
        print("update_maps", str(self.tabs.count()))
        for idx in range(3, self.tabs.count()):
            self.update_tab(idx)

    def recreate_maps(self):
        print("recreate_maps", str(self.tabs.count()))
        last = self.tabs.currentIndex()
        self.tabs.setCurrentIndex(0)
        self.remove_map_tabs()

        count = 0
        for m in self.appdata.project.maps:
            map = MapView(self.appdata, count)
            map.show()
            map.switchToReactionDialog.connect(self.switch_to_reaction)
            map.optimizeReaction.connect(self.optimize_reaction)
            map.reactionValueChanged.connect(self.update_reaction_value)
            self.tabs.addTab(map, m["name"])
            map.update()
            count += 1
        if last >= self.tabs.count():
            self.tabs.setCurrentIndex(self.tabs.count() - 1)
        else:
            self.tabs.setCurrentIndex(last)

    def update_tab(self, idx: int):
        print("centralwidget::update_tab", str(idx))
        if idx == 0:
            self.reaction_list.update()
        elif idx == 1:
            self.metabolite_list.update()
        elif idx >= FIXED_TABS:
            m = self.tabs.widget(idx)
            m.update()

    # def update_map(self, idx: int):
    #     print("centralwidget::update_map", str(idx))
    #     m = self.tabs.widget(2+idx)
    #     m.update()

    def jump_to_map(self, idx: int, reaction):
        print("centralwidget::jump_to_map", str(idx))
        m = self.tabs.widget(FIXED_TABS-1+idx)
        self.tabs.setCurrentIndex(FIXED_TABS-1+idx)

        m.update()
        # self.searchbar.setText(reaction)
        m.focus_reaction(reaction)
        m.highlight_reaction(reaction)


class ConfirmMapDeleteDialog(QDialog):

    def __init__(self, parent, idx):
        super(ConfirmMapDeleteDialog, self).__init__(parent)
        # Create widgets
        self.parent = parent
        self.idx = idx
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
        del self.parent.appdata.project.maps[self.idx-FIXED_TABS]
        self.parent.recreate_maps()
        self.accept()
