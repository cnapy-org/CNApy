"""The cnapy clipboard calculator dialog"""
from qtpy.QtWidgets import (QButtonGroup, QComboBox, QDialog, QHBoxLayout,
                            QLineEdit, QMessageBox, QPushButton, QRadioButton,
                            QVBoxLayout)

from cnapy.appdata import AppData


class ClipboardCalculator(QDialog):
    """A dialog to perform arithmetics with the clipboard"""

    def __init__(self, appdata: AppData):
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
        self.op.insertItem(4, "/")
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
        self.close = QPushButton("Close")
        l2.addWidget(self.button)
        l2.addWidget(self.close)
        self.layout.addItem(l2)
        self.setLayout(self.layout)

        # Connecting the signal
        self.close.clicked.connect(self.accept)
        self.button.clicked.connect(self.compute)

    def compute(self):
        l_comp = {}
        r_comp = {}
        if self.l1.isChecked():
            l_comp = self.appdata.project.comp_values

            for (key, value) in self.appdata.project.scen_values.items():
                l_comp[key] = value
        elif self.l2.isChecked():
            try:
                l_comp = self.appdata.clipboard_comp_values
            except AttributeError:
                QMessageBox.warning(
                    None,
                    "No clipboard created yet",
                    "Clipboard arithmetics do not work as no clipboard was created yet. Store values to a clipboard first to solve this problem."
                )
                return

        if self.r1.isChecked():
            r_comp = self.appdata.project.comp_values

            for (key, value) in self.appdata.project.scen_values.items():
                r_comp[key] = value
        elif self.r2.isChecked():
            r_comp = self.appdata.clipboard_comp_values

        for key in self.appdata.project.comp_values:
            if self.l3.isChecked():
                lv_comp = (float(self.left_value.text()),
                           float(self.left_value.text()))
            else:
                lv_comp = l_comp[key]
            if self.r3.isChecked():
                rv_comp = (float(self.right_value.text()),
                           float(self.right_value.text()))
            else:
                rv_comp = r_comp[key]

            res = self.combine(lv_comp, rv_comp)

            if key in self.appdata.project.scen_values.keys():
                self.appdata.project.scen_values[key] = res
            self.appdata.project.comp_values[key] = res

        self.appdata.project.comp_values_type = 0
        self.appdata.window.centralWidget().update()

    def combine(self, lv, rv):
        (llb, lub) = lv
        (rlb, rub) = rv
        if self.op.currentText() == "+":
            return (llb+rlb, lub+rub)
        if self.op.currentText() == "-":
            return (llb-rlb, lub-rub)
        if self.op.currentText() == "*":
            return (llb*rlb, lub*rub)
        if self.op.currentText() == "/":
            return (llb/rlb, lub/rub)
