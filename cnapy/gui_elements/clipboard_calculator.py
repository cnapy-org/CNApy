"""The cnapy clipboard calculator dialog"""
from qtpy.QtWidgets import (QButtonGroup, QComboBox, QDialog, QHBoxLayout,
                            QLineEdit, QPushButton, QRadioButton,
                            QVBoxLayout)

from cnapy.cnadata import CnaData


class ClipboardCalculator(QDialog):
    """A dialog to perform arithmetics with the clipboard"""

    def __init__(self, appdata: CnaData):
        QDialog.__init__(self)
        self.setWindowTitle("Clipboard calculator")

        self.appdata = appdata
        self.layout = QVBoxLayout()
        l1 = QHBoxLayout()
        self.left = QVBoxLayout()
        self.l1 = QRadioButton("Current values")
        self.l2 = QRadioButton("Clipboard values")
        h1 = QHBoxLayout()
        self.l3 = QRadioButton()
        self.left_value = QLineEdit("0")
        h1.addWidget(self.l3)
        h1.addWidget(self.left_value)
        self.lqb = QButtonGroup()
        self.lqb.addButton(self.l1)
        self.l1.setChecked(True)
        self.lqb.addButton(self.l2)
        self.lqb.addButton(self.l3)

        self.left.addWidget(self.l1)
        self.left.addWidget(self.l2)
        self.left.addItem(h1)
        op = QVBoxLayout()
        self.op = QComboBox()
        self.op.insertItem(1, "+")
        self.op.insertItem(2, "-")
        self.op.insertItem(3, "*")
        self.op.insertItem(4, "\\")
        op.addWidget(self.op)
        self.right = QVBoxLayout()
        self.r1 = QRadioButton("Current values")
        self.r2 = QRadioButton("Clipboard values")
        h2 = QHBoxLayout()
        self.r3 = QRadioButton()
        self.right_value = QLineEdit("0")
        h2.addWidget(self.r3)
        h2.addWidget(self.right_value)

        self.rqb = QButtonGroup()
        self.rqb.addButton(self.r1)
        self.r1.setChecked(True)
        self.rqb.addButton(self.r2)
        self.rqb.addButton(self.r3)

        self.right.addWidget(self.r1)
        self.right.addWidget(self.r2)
        self.right.addItem(h2)
        l1.addItem(self.left)
        l1.addItem(op)
        l1.addItem(self.right)
        self.layout.addItem(l1)

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
        l = {}
        r = {}
        if self.l1.isChecked():
            l = self.appdata.comp_values
        elif self.l2.isChecked():
            l = self.appdata.clipboard

        if self.r1.isChecked():
            r = self.appdata.comp_values
        elif self.r2.isChecked():
            r = self.appdata.clipboard

        for key in self.appdata.comp_values:
            if self.l3.isChecked():
                lv = (float(self.left_value.text()),
                      float(self.left_value.text()))
            else:
                lv = l[key]
            if self.r3.isChecked():
                rv = (float(self.right_value.text()),
                      float(self.right_value.text()))
            else:
                rv = r[key]

            res = self.combine(lv, rv)
            self.appdata.comp_values[key] = res

        self.accept()

    def combine(self, lv, rv):
        (llb, lub) = lv
        (rlb, rub) = rv
        if self.op.currentText() == "+":
            return (llb+rlb, lub+rub)
        if self.op.currentText() == "-":
            return (llb-rlb, lub-rub)
        if self.op.currentText() == "*":
            return (llb*rlb, lub*rub)
        if self.op.currentText() == "\\":
            return (llb/rlb, lub/rub)
