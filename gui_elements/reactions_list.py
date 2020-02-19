"""The PyNetAnalyzer reactions list"""
from PySide2.QtGui import QPainter, QDrag
from PySide2.QtCore import Qt, QRectF, QMimeData
from PySide2.QtWidgets import (QWidget, QGraphicsItem, QGraphicsScene, QGraphicsView, QLineEdit, QTextEdit, QLabel,
                               QGraphicsSceneDragDropEvent, QGraphicsSceneMouseEvent)
from PySide2.QtCore import Slot, Signal
from PySide2.QtWidgets import (QGraphicsItem, QAction, QApplication, QFileDialog,
                               QGraphicsScene, QHBoxLayout, QVBoxLayout, QLineEdit,
                               QMainWindow, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QWidget, QPushButton)


class ReactionList(QWidget):
    """A list of reaction"""

    def __init__(self):
        QWidget.__init__(self)
        self.layout = QVBoxLayout()
        self.layout .setContentsMargins(0, 0, 0, 0)
        self.reaction_list = QTreeWidget()
        self.reaction_list.setHeaderLabels(["Name", "Reversible"])
        self.reaction_list.setSortingEnabled(True)
        self.layout.addWidget(self.reaction_list)
        self.reaction_list.itemActivated.connect(self.reaction_selected)
        self.reaction_mask = ReactionMask()
        self.reaction_mask.hide()
        self.layout.addWidget(self.reaction_mask)

        self.setLayout(self.layout)

    def clear(self):
        self.reaction_list.clear()
        self.reaction_mask.hide()

    def add_reaction(self, reaction):
        item = QTreeWidgetItem(self.reaction_list)
        item.setText(0, reaction.name)
        item.setText(1, str(reaction.reversible))
        item.setData(2, 0, reaction)

    def reaction_selected(self, item, _column):
        # print("something something itemActivated", item, column)
        print(item.data(2, 0).name)
        self.reaction_mask.show()
        self.reaction_mask.update(item.data(2, 0))

    itemActivated = Signal(str)


class ReactionMask(QWidget):
    """The input mask for a reaction"""

    def __init__(self):
        QWidget.__init__(self)
        layout = QVBoxLayout()
        l = QHBoxLayout()
        label = QLabel("Reaction identifier:")
        self.id = QLineEdit()
        self.id.textChanged.connect(self.reaction_data_changed)
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
        label = QLabel("Default rate:")
        self.rate_default = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.rate_default)
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
        l.addWidget(label)
        l.addWidget(self.comments)
        layout.addItem(l)

        l = QVBoxLayout()
        button = QPushButton("add reaction to map")
        l.addWidget(button)
        layout.addItem(l)

        self.setLayout(layout)
        # self.visible = False

    def reaction_data_changed(self):
        print("TODO reaction data changed!")

    def update(self, reaction):
        self.id.setText(reaction.name)
