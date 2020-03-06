from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QGraphicsScene, QHBoxLayout,
                               QTabWidget, QTabBar, QPushButton,
                               QWidget)

from gui_elements.reactions_list import ReactionList
from gui_elements.species_list import SpeciesList
from gui_elements.map_view import MapView
from gui_elements.console import Console
from cnadata import CnaMap


class CentralWidget(QWidget):
    """The PyNetAnalyzer central widget"""

    def __init__(self, app):
        QWidget.__init__(self)
        self.app = app
        self.tabs = QTabWidget()
        self.reaction_list = ReactionList(self.app.appdata)
        self.specie_list = SpeciesList(self.app.appdata)
        self.tabs.addTab(self.reaction_list, "Reactions")
        self.tabs.addTab(self.specie_list, "Species")
        self.maps = []

        self.console = Console(self.app)
        self.tabs.addTab(self.console, "Console")
        self.tabs.setTabsClosable(True)

        self.add_tab_button = QPushButton("add map")
        self.tabs.setCornerWidget(
            self.add_tab_button, corner=Qt.TopRightCorner)

        # disable close button on reactions, species and console tab
        self.tabs.tabBar().setTabButton(0, QTabBar.RightSide, None)
        self.tabs.tabBar().setTabButton(1, QTabBar.RightSide, None)
        self.tabs.tabBar().setTabButton(2, QTabBar.RightSide, None)

        layout = QHBoxLayout()
        layout.addWidget(self.tabs)
        self.setLayout(layout)

        self.reaction_list.changedMap.connect(self.update_map)
        self.reaction_list.changedModel.connect(self.update_model_view)
        self.specie_list.changedModel.connect(self.update_model_view)
        self.add_tab_button.clicked.connect(self.add_map)
        self.tabs.tabCloseRequested.connect(self.remove_map)

    def switch_to_reaction(self, reaction: str):
        # print("centralwidget::switch_to_reaction")
        self.tabs.setCurrentIndex(0)
        self.reaction_list.setCurrentItem(reaction)

    def update_reaction_value(self, reaction: str, value: str):
        if self.app.appdata.low > float(value):
            self.app.appdata.low = float(value)
        if self.app.appdata.high < float(value):
            self.app.appdata.high = float(value)
        self.app.appdata.values[reaction] = float(value)
        self.reaction_list.update()

    def add_map(self):
        m = CnaMap("Map")
        self.app.appdata.maps.append(m)
        self.tabs.setCurrentIndex(2 + len(self.app.appdata.maps))
        map = MapView(self.app.appdata.maps[len(
            self.app.appdata.maps)-1], self.app.appdata.values)
        map.doubleClickedReaction.connect(self.switch_to_reaction)
        map.reactionValueChanged.connect(self.update_reaction_value)
        self.tabs.addTab(map, m["name"])
        self.update_maps()

    def remove_map(self, idx: int):
        print(idx)
        del self.app.appdata.maps[idx-3]
        self.update_maps()

    def update_model_view(self):
        # print("centralwidget::update_model_view")
        self.reaction_list.update()
        self.specie_list.update()
        self.update_maps()

    def update_maps(self):
        print("update_maps", str(self.tabs.count()))
        for idx in range(3, self.tabs.count()):
            self.tabs.removeTab(3)

        count = 0
        for m in self.app.appdata.maps:
            map = MapView(
                self.app.appdata.maps[count], self.app.appdata.values)
            map.show()
            map.doubleClickedReaction.connect(self.switch_to_reaction)
            map.reactionValueChanged.connect(self.update_reaction_value)
            self.tabs.addTab(map, m["name"])
            map.update()
            count += 1

    def update_map(self, idx: int):
        print("centralwidget::update_map", str(idx))
        m = self.tabs.widget(3+idx)
        m.update()
        self.tabs.setCurrentIndex(3+idx)
