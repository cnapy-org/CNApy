"""The PyNetAnalyzer species list"""
from PySide2.QtGui import QPainter, QDrag, QIcon
from PySide2.QtCore import Qt, QRectF, QMimeData
from PySide2.QtWidgets import (QWidget, QGraphicsItem, QGraphicsScene, QGraphicsView, QLineEdit, QTextEdit, QLabel,
                               QGraphicsSceneDragDropEvent, QGraphicsSceneMouseEvent, QSizePolicy)
from PySide2.QtCore import Slot, Signal
from PySide2.QtWidgets import (QGraphicsItem, QAction, QApplication, QFileDialog,
                               QGraphicsScene, QHBoxLayout, QVBoxLayout, QLineEdit,
                               QMainWindow, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QWidget, QPushButton, QStyle)

import cobra
import copy


class SpeciesList(QWidget):
    """A list of species"""

    def __init__(self, appdata):
        QWidget.__init__(self)
        self.appdata = appdata

        self.species_list = QTreeWidget()
        # self.species_list.setHeaderLabels(["Name", "Reversible"])
        self.species_list.setHeaderLabels(["Name"])
        self.species_list.setSortingEnabled(True)

        for r in self.appdata.cobra_py_model.metabolites:
            self.add_species(r)

        self.species_mask = SpeciesMask(appdata)
        self.species_mask.hide()

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.species_list)
        self.layout.addWidget(self.species_mask)
        self.setLayout(self.layout)

        self.species_list.currentItemChanged.connect(self.species_selected)
        self.species_mask.changedspeciesList.connect(self.update)

    def clear(self):
        self.species_list.clear()
        self.species_mask.hide()

    def add_species(self, species):
        item = QTreeWidgetItem(self.species_list)
        item.setText(0, species.name)
        item.setData(2, 0, species)

    def species_selected(self, item, _column):
        print("species_selected")
        self.species_mask.show()
        species: cobra.Metabolite = item.data(2, 0)
        self.species_mask.id.setText(species.name)
        # self.species_mask.equation.setText(species.build_species_string())
        # self.rate_default.setText(self.current_species.name)
        # self.species_mask.variance.setText(self.current_species.name)
        # self.species_mask.comments.setText(species.name)

        self.species_mask.old = species
        self.species_mask.changed = False
        self.species_mask.update()

    def update(self):
        self.species_list.clear()
        for m in self.appdata.cobra_py_model.metabolites:
            self.add_species(m)

    itemActivated = Signal(str)


class SpeciesMask(QWidget):
    """The input mask for a species"""

    def __init__(self, appdata):
        QWidget.__init__(self)
        self.appdata = appdata
        self.old = None
        self.is_valid = True
        self.changed = False
        layout = QVBoxLayout()
        l = QHBoxLayout()
        label = QLabel("species identifier:")
        self.id = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.id)
        layout.addItem(l)

        l = QVBoxLayout()
        label = QLabel("Notes and Comments:")
        self.comments = QTextEdit()
        self.comments.setFixedHeight(200)
        l.addWidget(label)
        l.addWidget(self.comments)
        layout.addItem(l)

        l = QHBoxLayout()
        self.apply_button = QPushButton("apply changes")
        self.apply_button.setEnabled(False)
        self.add_map_button = QPushButton("add species to map")
        self.add_map_button.setEnabled(False)

        l.addWidget(self.apply_button)
        l.addWidget(self.add_map_button)
        layout.addItem(l)

        self.setLayout(layout)

        self.id.textChanged.connect(self.species_id_changed)
        # self.equation.textChanged.connect(self.species_equation_changed)
        self.apply_button.clicked.connect(self.apply)

    def apply(self):
        self.old.name = self.id.text()
        self.changedspeciesList.emit()
        self.changed = False
        self.update()

    def verify_id(self):
        print("TODO species id changed! please verify")
        self.is_valid = True

    def species_id_changed(self):
        print("species_id_changed")
        if self.id == self.id.text():
            return
        self.changed = True
        self.verify_id()
        self.update()

    def update(self):
        print("update")

        if self.is_valid & self.changed:
            self.apply_button.setEnabled(True)
        else:
            self.apply_button.setEnabled(False)

    changedspeciesList = Signal()
