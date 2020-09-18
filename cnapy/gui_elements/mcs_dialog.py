"""The cnapy dialog for calculating minimal cut sets"""
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QSizePolicy, QLabel, QTreeWidget, QTreeWidgetItem, QButtonGroup, QComboBox, QDialog, QHBoxLayout,
                               QLineEdit, QPushButton, QRadioButton,
                               QVBoxLayout)

from cnapy.cnadata import CnaData
import cnapy.legacy


class MCSDialog(QDialog):
    """A dialog to perform minimal cut set computation"""

    def __init__(self, appdata: CnaData, centralwidget, engine, out, err):
        QDialog.__init__(self)
        self.appdata = appdata
        self.centralwidget = centralwidget
        self.eng = engine
        self.out = out
        self.err = err

        self.layout = QVBoxLayout()
        l1 = QLabel("Target Region(s)")
        self.layout.addWidget(l1)
        s1 = QHBoxLayout()
        self.target_list = QTreeWidget()
        self.target_list.setHeaderLabels(["region no", "T", "≥/≤", "t"])
        self.target_list.setSortingEnabled(True)
        s1.addWidget(self.target_list)
        s11 = QVBoxLayout()
        self.add_target = QPushButton("+")
        self.rem_target = QPushButton("-")
        s11.addWidget(self.add_target)
        s11.addWidget(self.rem_target)
        s1.addItem(s11)
        self.layout.addItem(s1)

        l2 = QLabel("Desired Region(s)")
        self.layout.addWidget(l2)
        s2 = QHBoxLayout()
        self.desired_list = QTreeWidget()
        self.desired_list.setHeaderLabels(["region no", "D", "≥/≤", "d"])
        self.desired_list.setSortingEnabled(True)
        s2.addWidget(self.desired_list)
        s21 = QVBoxLayout()
        self.add_desire = QPushButton("+")
        self.rem_desire = QPushButton("-")
        s21.addWidget(self.add_desire)
        s21.addWidget(self.rem_desire)
        s2.addItem(s21)
        self.layout.addItem(s2)

        buttons = QHBoxLayout()
        self.save = QPushButton("save")
        self.load = QPushButton("load")
        self.compute_mcs = QPushButton("Compute MCS")
        self.cancel = QPushButton("Cancel")
        buttons.addWidget(self.save)
        buttons.addWidget(self.load)
        buttons.addWidget(self.compute_mcs)
        buttons.addWidget(self.cancel)
        self.layout.addItem(buttons)

        # max width for buttons
        self.add_target.setMaximumWidth(20)
        self.rem_target.setMaximumWidth(20)
        self.add_desire.setMaximumWidth(20)
        self.rem_desire.setMaximumWidth(20)

        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.compute_mcs.clicked.connect(self.compute)

        item = QTreeWidgetItem(self.target_list)
        item.setText(0, "oh")
        item.setText(1, "ah")
        combo = QComboBox()
        combo.insertItem(1, "+")
        combo.insertItem(2, "-")
        # op.addWidget(self.op)

        item.setCellWidget(3, combo)
        # item.setData(3, 0, reaction)

    def compute(self):

        # create CobraModel for matlab
        cnapy.legacy.createCobraModel(self.appdata)

        print(".")
        a = self.eng.eval("startcna(1)", nargout=0,
                          stdout=self.out, stderr=self.err)
        print(".")
        a = self.eng.eval("load('cobra_model.mat')",
                          nargout=0)
        print(".")
        a = self.eng.eval("cnap = CNAcobra2cna(cbmodel);",
                          nargout=0)
        print(".")

        # get some data
        a = self.eng.eval("cnap = compute_mcs(cnap);",
                          nargout=0)

        self.accept()
