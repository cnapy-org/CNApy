"""The model info view"""

from qtpy.QtCore import Signal
from qtpy.QtWidgets import (
    QHBoxLayout,  QLabel, QTextEdit, QComboBox, QVBoxLayout, QWidget)

from cnapy.cnadata import CnaData


class ModelInfo(QWidget):
    """A widget that shows infos about the model"""

    def __init__(self, appdata: CnaData):
        QWidget.__init__(self)
        self.appdata = appdata

        self.layout = QVBoxLayout()
        label = QLabel("Description")
        self.layout.addWidget(label)
        self.description = QTextEdit()
        self.description.setPlaceholderText("Enter a project description")
        self.layout.addWidget(self.description)

        h1 = QHBoxLayout()

        label = QLabel("Optimization direction")
        h1.addWidget(label)
        self.opt_direction = QComboBox()
        self.opt_direction.insertItem(1, "minimize")
        self.opt_direction.insertItem(2, "maximize")
        h1.addWidget(self.opt_direction)
        self.layout.addItem(h1)

        self.setLayout(self.layout)

        self.description.textChanged.connect(
            self.description_changed)
        self.opt_direction.currentTextChanged.connect(
            self.opt_direction_changed)

        self.update()

    def update(self):
        if "description" in self.appdata.project.meta_data:
            description = self.appdata.project.meta_data["description"]
        else:
            description = ""

        self.description.textChanged.disconnect(
            self.description_changed)
        self.description.setText(description)

        self.description.textChanged.connect(
            self.description_changed)

        x = self.appdata.project.cobra_py_model.objective_direction

        self.opt_direction.currentTextChanged.disconnect(
            self.opt_direction_changed)

        if x == "max":
            self.opt_direction.setCurrentIndex(1)
        elif x == "min":
            self.opt_direction.setCurrentIndex(0)

        self.opt_direction.currentTextChanged.connect(
            self.opt_direction_changed)

    def description_changed(self):
        self.appdata.project.meta_data["description"] = self.description.toPlainText(
        )
        self.appdata.window.unsaved_changes()

    def opt_direction_changed(self):

        if self.opt_direction.currentIndex() == 0:
            self.appdata.project.cobra_py_model.objective_direction = "min"
            self.optimizationDirectionChanged.emit("min")
        if self.opt_direction.currentIndex() == 1:
            self.appdata.project.cobra_py_model.objective_direction = "max"
            self.optimizationDirectionChanged.emit("max")

    optimizationDirectionChanged = Signal(str)
