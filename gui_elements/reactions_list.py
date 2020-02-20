"""The PyNetAnalyzer reactions list"""
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


class ReactionList(QWidget):
    """A list of reaction"""

    def __init__(self, appdata):
        QWidget.__init__(self)
        self.appdata = appdata

        self.add_button = QPushButton("Add new reaction")
        self.add_button.setIcon(QIcon.fromTheme("list-add"))
        policy = QSizePolicy()
        policy.ShrinkFlag = True
        self.add_button.setSizePolicy(policy)

        self.reaction_list = QTreeWidget()
        # self.reaction_list.setHeaderLabels(["Name", "Reversible"])
        self.reaction_list.setHeaderLabels(["Name"])
        self.reaction_list.setSortingEnabled(True)

        for r in self.appdata.cobra_py_model.reactions:
            self.add_reaction(r)

        self.reaction_mask = ReactionMask(appdata)
        self.reaction_mask.hide()

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        l = QHBoxLayout()
        l.setAlignment(Qt.AlignRight)
        l.addWidget(self.add_button)
        self.layout.addItem(l)
        self.layout.addWidget(self.reaction_list)
        self.layout.addWidget(self.reaction_mask)
        self.setLayout(self.layout)

        self.reaction_list.currentItemChanged.connect(self.reaction_selected)
        self.reaction_mask.changedReactionList.connect(self.update)

        self.add_button.clicked.connect(self.add_new_reaction)

    def clear(self):
        self.reaction_list.clear()
        self.reaction_mask.hide()

    def add_reaction(self, reaction):
        item = QTreeWidgetItem(self.reaction_list)
        item.setText(0, reaction.name)
        item.setData(2, 0, reaction)

    def add_new_reaction(self):
        print("add_new_reaction")
        self.reaction_mask.show()
        reaction = cobra.Reaction()

        self.reaction_mask.id.setText("")
        self.reaction_mask.equation.setText(reaction.build_reaction_string())
        # self.rate_default.setText(self.current_reaction.name)
        self.reaction_mask.rate_min.setText(str(reaction.lower_bound))
        self.reaction_mask.rate_max.setText(str(reaction.upper_bound))
        self.reaction_mask.coefficent.setText(
            str(reaction.objective_coefficient))
        # self.reaction_mask.variance.setText(self.current_reaction.name)
        # self.reaction_mask.comments.setText(reaction.name)

        self.reaction_mask.old = None
        self.reaction_mask.changed = False
        self.reaction_mask.update()

    def reaction_selected(self, item, _column):
        print("reaction_selected")
        self.reaction_mask.show()
        reaction: cobra.Reaction = item.data(2, 0)
        self.reaction_mask.id.setText(reaction.name)
        self.reaction_mask.equation.setText(reaction.build_reaction_string())
        # self.rate_default.setText(self.current_reaction.name)
        self.reaction_mask.rate_min.setText(str(reaction.lower_bound))
        self.reaction_mask.rate_max.setText(str(reaction.upper_bound))
        self.reaction_mask.coefficent.setText(
            str(reaction.objective_coefficient))
        # self.reaction_mask.variance.setText(self.current_reaction.name)
        # self.reaction_mask.comments.setText(reaction.name)

        self.reaction_mask.old = reaction
        self.reaction_mask.changed = False
        self.reaction_mask.update()

    def update(self):
        self.reaction_list.clear()
        for r in self.appdata.cobra_py_model.reactions:
            self.add_reaction(r)

    itemActivated = Signal(str)


class ReactionMask(QWidget):
    """The input mask for a reaction"""

    def __init__(self, appdata):
        QWidget.__init__(self)
        self.appdata = appdata
        self.old = None
        self.is_valid = True
        self.changed = False

        layout = QVBoxLayout()
        l = QHBoxLayout()
        label = QLabel("Reaction identifier:")
        self.id = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.id)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Reaction equation:")
        self.equation = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.equation)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Rate min:")
        self.rate_min = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.rate_min)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Rate max:")
        self.rate_max = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.rate_max)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Coefficient in obj. function:")
        self.coefficent = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.coefficent)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Variance of meassures:")
        self.variance = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.variance)
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
        self.add_map_button = QPushButton("add reaction to map")
        self.add_map_button.setEnabled(False)

        l.addWidget(self.apply_button)
        l.addWidget(self.add_map_button)
        layout.addItem(l)

        self.setLayout(layout)

        self.id.textChanged.connect(self.reaction_id_changed)
        self.equation.textChanged.connect(self.reaction_equation_changed)
        # self.rate_min.textChanged.connect(self.reaction_data_changed)
        # self.rate_max.textChanged.connect(self.reaction_data_changed)
        # self.coefficent.textChanged.connect(self.reaction_data_changed)
        # self.variance.textChanged.connect(self.reaction_data_changed)
        # self.comments.textChanged.connect(self.reaction_data_changed)
        self.apply_button.clicked.connect(self.apply)

    def apply(self):
        if self.old is None:
            self.old = cobra.Reaction(self.id.text())
            self.appdata.cobra_py_model.add_reaction(self.old)

        self.old.name = self.id.text()
        self.old.build_reaction_from_string(self.equation.text())
        self.old.lower_bound = float(self.rate_min.text())
        self.old.upper_bound = float(self.rate_max.text())

        self.changedReactionList.emit()
        self.changed = False
        self.update()

    def verify_id(self):
        print("TODO reaction id changed! please verify")
        self.is_valid = True

    def verify_equation(self):
        print("TODO reaction equation changed! please verify")

        with self.appdata.cobra_py_model as model:
            r = cobra.Reaction("test_id")
            model.add_reaction(r)
            try:
                r.build_reaction_from_string(self.equation.text())
            except:
                self.is_valid = False
                self.equation.setStyleSheet("background: #ff9999")
            else:
                self.is_valid = True
                self.equation.setStyleSheet("background: white")

    def reaction_id_changed(self):
        print("reaction_id_changed")
        if self.id == self.id.text():
            return
        self.changed = True
        self.verify_id()
        self.update()

    def reaction_equation_changed(self):
        print("reaction_equation_changed")
        if self.equation == self.equation.text():
            return
        self.changed = True
        self.verify_equation()
        self.update()

    def update(self):
        print("update")
        if self.old is None:
            self.apply_button.setText("add reaction")
        else:
            self.apply_button.setText("apply changes")

        if self.is_valid & self.changed:
            self.apply_button.setEnabled(True)
        else:
            self.apply_button.setEnabled(False)

    changedReactionList = Signal()
