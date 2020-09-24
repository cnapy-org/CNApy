"""The cnapy dialog for calculating minimal cut sets"""
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QGroupBox, QCheckBox, QHeaderView, QTableWidget, QTableWidgetItem, QSizePolicy, QLabel, QTreeWidget, QTreeWidgetItem, QButtonGroup, QComboBox, QDialog, QHBoxLayout,
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

        self.target_list = QTableWidget(1, 4)
        self.target_list.setHorizontalHeaderLabels(
            ["region no", "T", "≥/≤", "t"])
        self.target_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.target_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.target_list.horizontalHeader().resizeSection(0, 100)
        self.target_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.target_list.horizontalHeader().resizeSection(2, 50)
        item = QTableWidgetItem("1")
        self.target_list.setItem(0, 0, item)
        combo = QComboBox(self.target_list)
        combo.insertItem(1, "≤")
        combo.insertItem(2, "≥")
        self.target_list.setCellWidget(0, 2, combo)
        item = QTableWidgetItem("0")
        self.target_list.setItem(0, 3, item)

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
        self.desired_list = QTableWidget(1, 4)
        self.desired_list.setHorizontalHeaderLabels(
            ["region no", "D", "≥/≤", "d"])
        self.desired_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.desired_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.desired_list.horizontalHeader().resizeSection(0, 100)
        self.desired_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.desired_list.horizontalHeader().resizeSection(2, 50)
        item = QTableWidgetItem("1")
        self.desired_list.setItem(0, 0, item)
        combo = QComboBox(self.desired_list)
        combo.insertItem(1, "≤")
        combo.insertItem(2, "≥")
        self.desired_list.setItem(0, 0, item)
        self.desired_list.setCellWidget(0, 2, combo)
        item = QTableWidgetItem("0")
        self.desired_list.setItem(0, 3, item)
        s2.addWidget(self.desired_list)

        s21 = QVBoxLayout()
        self.add_desire = QPushButton("+")
        self.rem_desire = QPushButton("-")
        s21.addWidget(self.add_desire)
        s21.addWidget(self.rem_desire)
        s2.addItem(s21)
        self.layout.addItem(s2)

        s3 = QHBoxLayout()

        self.gen_kos = QGroupBox("Gene KOs")
        self.gen_kos.setCheckable(True)
        sg1 = QHBoxLayout()
        s31 = QVBoxLayout()
        l = QLabel("Max. Solutions")
        s31.addWidget(l)
        l = QLabel("Max. Size")
        s31.addWidget(l)
        l = QLabel("Time Limit [sec]")
        s31.addWidget(l)

        sg1.addItem(s31)

        s32 = QVBoxLayout()
        self.max_solu = QLineEdit("inf")
        self.max_solu.setMaximumWidth(50)
        s32.addWidget(self.max_solu)
        self.max_size = QLineEdit("7")
        self.max_size.setMaximumWidth(50)
        s32.addWidget(self.max_size)
        self.time_limit = QLineEdit("inf")
        self.time_limit.setMaximumWidth(50)
        s32.addWidget(self.time_limit)

        sg1.addItem(s32)
        self.gen_kos.setLayout(sg1)

        g3 = QGroupBox("Solver")
        s33 = QVBoxLayout()
        self.bg1 = QButtonGroup()
        self.solver_cplex_matlab = QRadioButton("CPLEX (MATLAB)")
        s33.addWidget(self.solver_cplex_matlab)
        self.bg1.addButton(self.solver_cplex_matlab)
        self.solver_cplex_java = QRadioButton("CPLEX (Java)")
        s33.addWidget(self.solver_cplex_java)
        self.bg1.addButton(self.solver_cplex_java)
        self.solver_intlinprog = QRadioButton("intlinprog")
        s33.addWidget(self.solver_intlinprog)
        self.bg1.addButton(self.solver_intlinprog)
        g3.setLayout(s33)

        g4 = QGroupBox("MCS search")
        s34 = QVBoxLayout()
        # l = QLabel("MCS search")
        # s34.addWidget(l)
        self.bg2 = QButtonGroup()
        self.any_mcs = QRadioButton("any MCS (fast)")
        s34.addWidget(self.any_mcs)
        self.bg2.addButton(self.any_mcs)
        self.mcs_by_cardinality = QRadioButton("by cardinality")
        s34.addWidget(self.mcs_by_cardinality)
        self.bg2.addButton(self.mcs_by_cardinality)
        self.smalles_mcs_first = QRadioButton("smallest MCS first")
        s34.addWidget(self.smalles_mcs_first)
        self.bg2.addButton(self.smalles_mcs_first)
        g4.setLayout(s34)

        s3.addWidget(self.gen_kos)
        s3.addWidget(g3)
        s3.addWidget(g4)

        self.layout.addItem(s3)

        s4 = QVBoxLayout()
        self.consider_scenario = QCheckBox(
            "Consider constraint given by scenario")
        s4.addWidget(self.consider_scenario)
        self.advanced = QCheckBox(
            "Advanced: Define knockout/addition costs for genes/reactions")
        self.advanced.setEnabled(False)
        s4.addWidget(self.advanced)
        self.layout.addItem(s4)

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
