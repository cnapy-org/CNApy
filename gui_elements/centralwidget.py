from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QGraphicsScene, QHBoxLayout,
                               QTabWidget, QPushButton,
                               QWidget)

from gui_elements.reactions_list import ReactionList
from gui_elements.species_list import SpeciesList
from gui_elements.map_view import MapView
from gui_elements.console import Console


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

        self.scene = QGraphicsScene()
        self.map = MapView(self.app.appdata, self.scene)
        self.map.show()
        self.tabs.addTab(self.map, "Map")

        self.console = Console(self.app)
        self.tabs.addTab(self.console, "Console")
        self.tabs.setTabsClosable(True)

        self.add_tab_button = QPushButton("add map")
        self.tabs.setCornerWidget(
            self.add_tab_button, corner=Qt.TopRightCorner)

        layout = QHBoxLayout()
        layout.addWidget(self.tabs)
        self.setLayout(layout)

        self.reaction_list.changedMap.connect(self.update_map)
        self.reaction_list.changedModel.connect(self.update_model_view)
        self.specie_list.changedModel.connect(self.update_model_view)
        self.map.doubleClickedReaction.connect(self.switch_to_reaction)
        self.map.reactionValueChanged.connect(self.update_reaction_value)

    def switch_to_reaction(self, reaction: str):
        print("update_model_view")
        self.tabs.setCurrentIndex(0)
        self.reaction_list.setCurrentItem(reaction)

    def update_reaction_value(self, reaction: str, value: str):
        if self.app.appdata.low > float(value):
            self.app.appdata.low = float(value)
        if self.app.appdata.high < float(value):
            self.app.appdata.high = float(value)
        self.app.appdata.values[reaction] = float(value)
        self.reaction_list.update()

    def update_model_view(self):
        print("update_model_view")
        self.reaction_list.update()
        self.specie_list.update()

    def update_map(self):
        print("update_map")
        self.map.update()
        self.tabs.setCurrentIndex(2)
