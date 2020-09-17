"""The cnapy phase plane plot dialog"""
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QCompleter, QDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QVBoxLayout)


class PhasePlaneDialog(QDialog):
    """A dialog to perform arithmetics with the clipboard"""

    def __init__(self, appdata):
        QDialog.__init__(self)
        self.setWindowTitle("Phase plane plotting")
        self.appdata = appdata

        completer = QCompleter(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)

        self.layout = QVBoxLayout()
        l1 = QHBoxLayout()
        t1 = QLabel("Reaction (x-axis):")
        l1.addWidget(t1)
        self.x_axis = QLineEdit("")
        self.x_axis.setPlaceholderText("Enter reaction Id")
        self.x_axis.setCompleter(completer)
        l1.addWidget(self.x_axis)
        l2 = QHBoxLayout()
        t2 = QLabel("Reaction (y-axis):")
        l2.addWidget(t2)
        self.y_axis = QLineEdit("")
        self.y_axis.setPlaceholderText("Enter reaction Id")
        self.y_axis.setCompleter(completer)
        l2.addWidget(self.y_axis)
        self.layout.addItem(l1)
        self.layout.addItem(l2)
        l3 = QHBoxLayout()
        self.button = QPushButton("Compute")
        self.cancel = QPushButton("Cancel")
        l3.addWidget(self.button)
        l3.addWidget(self.cancel)
        self.layout.addItem(l3)
        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

    def compute(self):
        with self.appdata.project.cobra_py_model as model:
            from cameo import phenotypic_phase_plane
            self.appdata.project.load_scenario_into_model(model)
            x_axis = self.x_axis.text()
            y_axis = self.y_axis.text()
            result = phenotypic_phase_plane(model,
                                            variables=[
                                                model.reactions.get_by_id(y_axis)],
                                            objective=model.reactions.get_by_id(
                                                x_axis),
                                            points=10)
            print(result)
            result.plot()

        self.accept()
