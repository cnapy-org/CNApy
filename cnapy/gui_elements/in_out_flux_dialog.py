"""The in out flux dialog"""
from qtpy.QtWidgets import (QDialog, QHBoxLayout, QLabel,
                            QPushButton, QVBoxLayout, QComboBox)
from cnapy.cnadata import CnaData


class InOutFluxDialog(QDialog):
    """A dialog to plot in out fluxes on a metabolite"""

    def __init__(self, appdata: CnaData):
        QDialog.__init__(self)
        self.setWindowTitle("Compute in/out fluxes")

        self.appdata = appdata

        self.layout = QVBoxLayout()

        t1 = QLabel("Choose metabolite")
        self.layout.addWidget(t1)
        self.metabolite_chooser = QComboBox()
        self.layout.addWidget(self.metabolite_chooser)
        l = QHBoxLayout()
        self.button = QPushButton("Plot")
        self.cancel = QPushButton("Close")
        l.addWidget(self.button)
        l.addWidget(self.cancel)
        self.layout.addItem(l)
        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)
        self.update()

    def update(self):
        for m in self.appdata.project.cobra_py_model.metabolites:
            self.metabolite_chooser.insertItem(0, m.id)

    def compute(self):
        metabolite = self.metabolite_chooser.currentText()
        self.appdata.window.centralWidget().in_out_fluxes(metabolite)
