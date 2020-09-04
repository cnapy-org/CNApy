from ast import literal_eval as make_tuple

from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QLineEdit, QPushButton, QTabBar, QTabWidget,
                               QVBoxLayout, QWidget)

from cnapy.cnadata import CnaData, CnaMap
from cnapy.gui_elements.console import Console
from cnapy.gui_elements.map_view import MapView
from cnapy.gui_elements.modenavigator import ModeNavigator
from cnapy.gui_elements.reactions_list import ReactionList
from cnapy.gui_elements.species_list import SpeciesList


class CentralWidget(QWidget):
    """The PyNetAnalyzer central widget"""

    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        self.appdata: CnaData = parent.appdata

        self.searchbar = QLineEdit()
        self.searchbar.textChanged.connect(self.update_selected)

        self.tabs = QTabWidget()
        self.reaction_list = ReactionList(self.appdata)
        self.specie_list = SpeciesList(self.appdata)
        self.tabs.addTab(self.reaction_list, "Reactions")
        self.tabs.addTab(self.specie_list, "Species")
        self.maps: list = []

        self.console = Console(self.parent)
        self.tabs.addTab(self.console, "Console")
        self.tabs.setTabsClosable(True)

        self.add_tab_button = QPushButton("add map")
        self.tabs.setCornerWidget(
            self.add_tab_button, corner=Qt.TopRightCorner)

        # disable close button on reactions, species and console tab
        self.tabs.tabBar().setTabButton(0, QTabBar.RightSide, None)
        self.tabs.tabBar().setTabButton(1, QTabBar.RightSide, None)
        self.tabs.tabBar().setTabButton(2, QTabBar.RightSide, None)

        self.mode_navigator = ModeNavigator(self.appdata)
        layout = QVBoxLayout()
        layout.addWidget(self.searchbar)
        layout.addWidget(self.tabs)
        layout.addWidget(self.mode_navigator)
        self.setLayout(layout)

        self.reaction_list.jumpToMap.connect(self.jump_to_map)
        self.reaction_list.changedModel.connect(self.update)
        self.specie_list.changedModel.connect(self.update)
        self.add_tab_button.clicked.connect(self.add_map)
        self.tabs.tabCloseRequested.connect(self.remove_map)
        self.mode_navigator.changedCurrentMode.connect(self.update)

        self.update()

    def switch_to_reaction(self, reaction: str):
        # print("centralwidget::switch_to_reaction")
        self.tabs.setCurrentIndex(0)
        self.reaction_list.setCurrentItem(reaction)

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
        map.doubleClickedReaction.connect(self.switch_to_reaction)
        map.reactionValueChanged.connect(self.update_reaction_value)
        self.tabs.addTab(map, m["name"])
        self.update_maps()
        self.tabs.setCurrentIndex(2 + len(self.appdata.project.maps))

    def remove_map_tabs(self):
        for idx in range(3, self.tabs.count()):
            self.tabs.removeTab(3)

    def remove_map(self, idx: int):
        del self.appdata.project.maps[idx-3]
        self.recreate_maps()

    def update_selected(self):
        # print("centralwidget::update_selected")
        idx = self.tabs.currentIndex()
        if idx == 0:
            x = self.searchbar.text()
            self.reaction_list.update_selected(x)
        elif idx > 2:
            x = self.searchbar.text()
            m = self.tabs.widget(idx)
            m.update_selected(x)

    def update(self):
        # print("centralwidget::update")
        if len(self.appdata.project.modes) == 0:
            self.mode_navigator.hide()
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
            map.doubleClickedReaction.connect(self.switch_to_reaction)
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
            self.specie_list.update()
        elif idx == 2:
            pass
        elif idx > 0:
            self.update_map(idx-2)

    def update_map(self, idx: int):
        print("centralwidget::update_map", str(idx))
        m = self.tabs.widget(2+idx)
        m.update()

    def jump_to_map(self, idx: int, reaction):
        print("centralwidget::jump_to_map", str(idx))
        m = self.tabs.widget(2+idx)
        self.tabs.setCurrentIndex(2+idx)

        m.update()
        # self.searchbar.setText(reaction)
        m.focus_reaction(reaction)
        m.highlight_reaction(reaction)
