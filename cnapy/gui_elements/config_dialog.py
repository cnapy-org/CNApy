"""The cnapy configuration dialog"""
from PySide2.QtWidgets import (QLabel, QButtonGroup, QComboBox, QDialog, QHBoxLayout,
                               QLineEdit, QPushButton, QRadioButton,
                               QVBoxLayout)

from cnapy.cnadata import CnaData


class ConfigDialog(QDialog):
    """A dialog to set values in cnapy-config.txt"""

    def __init__(self, appdata: CnaData):
        QDialog.__init__(self)
        self.appdata = appdata
        self.layout = QVBoxLayout()
        h1 = QHBoxLayout()
        self.l1 = QLabel("CNA path")
        self.cna_path = QLineEdit("0")
        h1.addWidget(self.l1)
        h1.addWidget(self.cna_path)

        self.layout.addItem(h1)

        l2 = QHBoxLayout()
        self.button = QPushButton("Compute")
        self.cancel = QPushButton("Cancel")
        l2.addWidget(self.button)
        l2.addWidget(self.cancel)
        self.layout.addItem(l2)
        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

    def compute(self):
        pass
