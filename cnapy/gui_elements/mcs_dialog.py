"""The cnapy dialog for calculating minimal cut sets"""

import io
import traceback

import cnapy.legacy as legacy
from cnapy.cnadata import CnaData
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QCompleter,
                            QDialog, QGroupBox, QHBoxLayout, QHeaderView,
                            QLabel, QLineEdit, QMessageBox, QPushButton,
                            QRadioButton, QTableWidget, QVBoxLayout)
# import sympy
import cobra.util.array
import optlang
import cnapy.cMCS_enumerator as cMCS_enumerator
from itertools import groupby

class MCSDialog(QDialog):
    """A dialog to perform minimal cut set computation"""

    def __init__(self, appdata: CnaData, centralwidget):
        QDialog.__init__(self)
        self.appdata = appdata
        self.centralwidget = centralwidget
        self.eng = appdata.engine
        self.out = io.StringIO()
        self.err = io.StringIO()

        self.layout = QVBoxLayout()
        l1 = QLabel("Target Region(s)")
        self.layout.addWidget(l1)
        s1 = QHBoxLayout()

        completer = QCompleter(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)

        self.target_list = QTableWidget(1, 4)
        self.target_list.setHorizontalHeaderLabels(
            ["region no", "T", "≥/≤", "t"])
        self.target_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.target_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.target_list.horizontalHeader().resizeSection(0, 100)
        self.target_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.target_list.horizontalHeader().resizeSection(2, 50)
        item = QLineEdit("1")
        self.target_list.setCellWidget(0, 0, item)
        item2 = QLineEdit("")
        item2.setCompleter(completer)
        self.target_list.setCellWidget(0, 1, item2)
        combo = QComboBox(self.target_list)
        combo.insertItem(1, "≤")
        combo.insertItem(2, "≥")
        self.target_list.setCellWidget(0, 2, combo)
        item = QLineEdit("0")
        self.target_list.setCellWidget(0, 3, item)

        s1.addWidget(self.target_list)

        s11 = QVBoxLayout()
        self.add_target = QPushButton("+")
        self.add_target.clicked.connect(self.add_target_region)
        self.rem_target = QPushButton("-")
        self.rem_target.clicked.connect(self.rem_target_region)
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
        item = QLineEdit("1")
        self.desired_list.setCellWidget(0, 0, item)
        item2 = QLineEdit("")
        item2.setCompleter(completer)
        self.desired_list.setCellWidget(0, 1, item2)
        combo = QComboBox(self.desired_list)
        combo.insertItem(1, "≤")
        combo.insertItem(2, "≥")
        self.desired_list.setCellWidget(0, 2, combo)
        item = QLineEdit("0")
        self.desired_list.setCellWidget(0, 3, item)
        s2.addWidget(self.desired_list)

        s21 = QVBoxLayout()
        self.add_desire = QPushButton("+")
        self.add_desire.clicked.connect(self.add_desired_region)
        self.rem_desire = QPushButton("-")
        self.rem_desire.clicked.connect(self.rem_desired_region)
        s21.addWidget(self.add_desire)
        s21.addWidget(self.rem_desire)
        s2.addItem(s21)
        self.layout.addItem(s2)

        s3 = QHBoxLayout()

        sgx = QVBoxLayout()
        self.gen_kos = QCheckBox("Gene KOs")
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
        sgx.addWidget(self.gen_kos)
        sgx.addItem(sg1)
        s3.addItem(sgx)

        g3 = QGroupBox("Solver")
        s33 = QVBoxLayout()
        self.bg1 = QButtonGroup()
        self.solver_cplex_matlab = QRadioButton("CPLEX (MATLAB)")
        self.solver_cplex_matlab.setToolTip(
            "Only enabled with MATLAB and CPLEX")
        s33.addWidget(self.solver_cplex_matlab)
        self.bg1.addButton(self.solver_cplex_matlab)
        self.solver_cplex_java = QRadioButton("CPLEX (Java)")
        self.solver_cplex_java.setToolTip("Only enabled with Octave and CPLEX")
        s33.addWidget(self.solver_cplex_java)
        self.bg1.addButton(self.solver_cplex_java)
        self.solver_intlinprog = QRadioButton("intlinprog")
        self.solver_intlinprog.setToolTip("Only enabled with MATLAB")
        s33.addWidget(self.solver_intlinprog)
        self.bg1.addButton(self.solver_intlinprog)
        self.solver_glpk = QRadioButton("GLPK")
        s33.addWidget(self.solver_glpk)
        self.bg1.addButton(self.solver_glpk)
        g3.setLayout(s33)
        s3.addWidget(g3)

        self.solver_glpk.setChecked(True)

        g4 = QGroupBox("MCS search")
        s34 = QVBoxLayout()
        self.bg2 = QButtonGroup()
        self.any_mcs = QRadioButton("any MCS (fast)")
        self.any_mcs.setChecked(True)
        s34.addWidget(self.any_mcs)
        self.bg2.addButton(self.any_mcs)

        # Disable incompatible combinations
        if not self.eng.is_cplex_matlab_ready():
            self.solver_cplex_matlab.setEnabled(False)
        if not self.eng.is_cplex_java_ready():
            self.solver_cplex_java.setEnabled(False)
        if self.appdata.is_matlab_set():
            self.solver_cplex_java.setEnabled(False)
        if not self.appdata.is_matlab_set():
            self.solver_cplex_matlab.setEnabled(False)
            self.solver_intlinprog.setEnabled(False)

        print(self.eng.is_cplex_matlab_ready())
        print(self.eng.is_cplex_java_ready())

        # Search type: by cardinality only with CPLEX possible
        self.mcs_by_cardinality = QRadioButton("by cardinality")
        s34.addWidget(self.mcs_by_cardinality)
        self.bg2.addButton(self.mcs_by_cardinality)

        self.smalles_mcs_first = QRadioButton("smallest MCS first")
        s34.addWidget(self.smalles_mcs_first)
        self.bg2.addButton(self.smalles_mcs_first)
        g4.setLayout(s34)

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
        # self.save = QPushButton("save")
        # buttons.addWidget(self.save)
        # self.load = QPushButton("load")
        # buttons.addWidget(self.load)
        self.compute_mcs = QPushButton("Compute MCS")
        buttons.addWidget(self.compute_mcs)
        self.compute_mcs2 = QPushButton("Compute MCS2")
        buttons.addWidget(self.compute_mcs2)
        self.cancel = QPushButton("Close")
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
        self.compute_mcs2.clicked.connect(self.compute2)

    def add_target_region(self):
        i = self.target_list.rowCount()
        self.target_list.insertRow(i)

        completer = QCompleter(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)

        item = QLineEdit("1")
        self.target_list.setCellWidget(i, 0, item)
        item2 = QLineEdit("")
        item2.setCompleter(completer)
        self.target_list.setCellWidget(i, 1, item2)
        combo = QComboBox(self.target_list)
        combo.insertItem(1, "≤")
        combo.insertItem(2, "≥")
        self.target_list.setCellWidget(i, 2, combo)
        item = QLineEdit("0")
        self.target_list.setCellWidget(i, 3, item)

    def add_desired_region(self):
        i = self.desired_list.rowCount()
        self.desired_list.insertRow(i)

        completer = QCompleter(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)

        item = QLineEdit("1")
        self.desired_list.setCellWidget(i, 0, item)
        item2 = QLineEdit("")
        item2.setCompleter(completer)
        self.desired_list.setCellWidget(i, 1, item2)
        combo = QComboBox(self.desired_list)
        combo.insertItem(1, "≤")
        combo.insertItem(2, "≥")
        self.desired_list.setCellWidget(i, 2, combo)
        item = QLineEdit("0")
        self.desired_list.setCellWidget(i, 3, item)

    def rem_target_region(self):
        i = self.target_list.rowCount()
        self.target_list.removeRow(i-1)

    def rem_desired_region(self):
        i = self.desired_list.rowCount()
        self.desired_list.removeRow(i-1)

    def compute(self):
        # create CobraModel for matlab
        self.appdata.createCobraModel()

        print(".")
        self.eng.eval("load('cobra_model.mat')",
                      nargout=0)
        print(".")
        try:
            self.eng.eval("cnap = CNAcobra2cna(cbmodel);",
                          nargout=0,
                          stdout=self.out, stderr=self.err)
        except Exception:
            output = io.StringIO()
            traceback.print_exc(file=output)
            exstr = output.getvalue()
            print(exstr)
            QMessageBox.warning(self, 'Unknown exception occured!',
                                exstr+'\nPlease report the problem to:\n\
                                    \nhttps://github.com/ARB-Lab/CNApy/issues')
            return

        print(".")

        self.eng.eval("genes = [];", nargout=0,
                      stdout=self.out, stderr=self.err)
        cmd = "maxSolutions = " + str(float(self.max_solu.text())) + ";"
        self.eng.eval(cmd, nargout=0, stdout=self.out, stderr=self.err)

        cmd = "maxSize = " + str(int(self.max_size.text())) + ";"
        self.eng.eval(cmd, nargout=0, stdout=self.out, stderr=self.err)

        cmd = "milp_time_limit = " + str(float(self.time_limit.text())) + ";"
        self.eng.eval(cmd, nargout=0, stdout=self.out, stderr=self.err)

        if self.gen_kos.isChecked():
            self.eng.eval("gKOs = 1;", nargout=0)
        else:
            self.eng.eval("gKOs = 0;", nargout=0)
        if self.advanced.isChecked():
            self.eng.eval("advanced_on = 1;", nargout=0)
        else:
            self.eng.eval("advanced_on = 0;", nargout=0)

        if self.solver_intlinprog.isChecked():
            self.eng.eval("solver = 'intlinprog';", nargout=0)
        if self.solver_cplex_java.isChecked():
            self.eng.eval("solver = 'java_cplex_new';", nargout=0)
        if self.solver_cplex_matlab.isChecked():
            self.eng.eval("solver = 'matlab_cplex';", nargout=0)
        if self.solver_glpk.isChecked():
            self.eng.eval("solver = 'glpk';", nargout=0)
        if self.any_mcs.isChecked():
            self.eng.eval("mcs_search_mode = 'search_1';", nargout=0)
        elif self.any_mcs.isChecked():
            self.eng.eval("mcs_search_mode = 'search_2';", nargout=0)
        elif self.smalles_mcs_first.isChecked():
            self.eng.eval("mcs_search_mode = 'search_3';", nargout=0)

        if self.consider_scenario.isChecked():
            self.eng.eval("reac_box_vals = 1;", nargout=0)
        else:
            self.eng.eval("reac_box_vals = 0;", nargout=0)

        rows = self.target_list.rowCount()
        for i in range(0, rows):
            p1 = self.target_list.cellWidget(i, 0).text()
            p2 = self.target_list.cellWidget(i, 1).text()
            if self.target_list.cellWidget(i, 2).currentText() == '≤':
                p3 = "<="
            else:
                p3 = ">="
            p4 = self.target_list.cellWidget(i, 3).text()
            cmd = "dg_T = {[" + p1+"], '" + p2 + \
                "', '" + p3 + "', [" + p4 + "']};"
            print(cmd)
            self.eng.eval(cmd, nargout=0,
                          stdout=self.out, stderr=self.err)

        rows = self.desired_list.rowCount()
        for i in range(0, rows):
            p1 = self.desired_list.cellWidget(i, 0).text()
            p2 = self.desired_list.cellWidget(i, 1).text()
            if self.desired_list.cellWidget(i, 2).currentText() == '≤':
                p3 = "<="
            else:
                p3 = ">="
            p4 = self.desired_list.cellWidget(i, 3).text()
            cmd = "dg_D = {[" + p1+"], '" + p2 + \
                "', '" + p3 + "', [" + p4 + "']};"
            print(cmd)
            self.eng.eval(cmd, nargout=0)

        # get some data
        self.eng.eval("reac_id = cellstr(cnap.reacID).';",
                      nargout=0, stdout=self.out, stderr=self.err)

        mcs = []
        values = []
        reactions = []
        reac_id = []
        if self.appdata.is_matlab_set():
            reac_id = self.eng.workspace['reac_id']
            try:
                self.eng.eval("[mcs] = cnapy_compute_mcs(cnap, genes, maxSolutions, maxSize, milp_time_limit, gKOs, advanced_on, solver, mcs_search_mode, reac_box_vals, dg_T,dg_D);",
                              nargout=0)
            except Exception:
                output = io.StringIO()
                traceback.print_exc(file=output)
                exstr = output.getvalue()
                print(exstr)
                QMessageBox.warning(self, 'Unknown exception occured!',
                                    exstr+'\nPlease report the problem to:\n\
                                    \nhttps://github.com/ARB-Lab/CNApy/issues')
                return
            else:
                self.eng.eval("[reaction, mcs, value] = find(mcs);", nargout=0,
                              stdout=self.out, stderr=self.err)
                reactions = self.eng.workspace['reaction']
                mcs = self.eng.workspace['mcs']
                values = self.eng.workspace['value']
        elif self.appdata.is_octave_ready():
            reac_id = self.eng.pull('reac_id')
            reac_id = reac_id[0]
            try:
                self.eng.eval("[mcs] = cnapy_compute_mcs(cnap, genes, maxSolutions, maxSize, milp_time_limit, gKOs, advanced_on, solver, mcs_search_mode, reac_box_vals, dg_T,dg_D);",
                              nargout=0)
            except Exception:
                output = io.StringIO()
                traceback.print_exc(file=output)
                exstr = output.getvalue()
                print(exstr)
                QMessageBox.warning(self, 'Unknown exception occured!',
                                    exstr+'\nPlease report the problem to:\n\
                                    \nhttps://github.com/ARB-Lab/CNApy/issues')
                return
            else:
                self.eng.eval("[reaction, mcs, value] = find(mcs);", nargout=0,
                              stdout=self.out, stderr=self.err)
                reactions = self.eng.pull('reaction')
                mcs = self.eng.pull('mcs')
                values = self.eng.pull('value')

        if len(mcs) == 0:
            QMessageBox.information(self, 'No cut sets',
                                          'Cut sets have not been calculated or do not exist.')
        else:
            last_mcs = 1
            omcs = []
            current_mcs = {}
            print(reac_id)
            for i in range(0, len(reac_id)):
                reacid = int(reactions[i][0])
                reaction = reac_id[reacid-1]
                c_mcs = int(mcs[i][0])
                c_value = int(values[i][0])
                if c_value == -1:  # -1 stands for removed which is 0 in the ui
                    c_value = 0
                if c_mcs > last_mcs:
                    omcs.append(current_mcs)
                    print(current_mcs)
                    last_mcs = c_mcs
                    current_mcs = {}
                current_mcs[reaction] = c_value
            print(current_mcs)
            omcs.append(current_mcs)
            self.appdata.project.modes = omcs
            self.centralwidget.mode_navigator.current = 0
            QMessageBox.information(self, 'Cut sets found',
                                          str(len(omcs))+' Cut sets have been calculated.')

        self.centralwidget.update_mode()
        self.centralwidget.mode_navigator.title.setText("MCS Navigation")

    def compute2(self):
        max_mcs_num = float(self.max_solu.text())
        max_mcs_size = int(self.max_size.text())
        timeout = float(self.time_limit.text())
        if timeout is float('inf'):
            timeout = None

        # if self.gen_kos.isChecked():
        #     self.eng.eval("gKOs = 1;", nargout=0)
        # else:
        #     self.eng.eval("gKOs = 0;", nargout=0)
        # if self.advanced.isChecked():
        #     self.eng.eval("advanced_on = 1;", nargout=0)
        # else:
        #     self.eng.eval("advanced_on = 0;", nargout=0)

        # if self.solver_intlinprog.isChecked():
        #     self.eng.eval("solver = 'intlinprog';", nargout=0)
        # if self.solver_cplex_java.isChecked():
        #     self.eng.eval("solver = 'java_cplex_new';", nargout=0)
        # if self.solver_cplex_matlab.isChecked():
        #     self.eng.eval("solver = 'matlab_cplex';", nargout=0)
        # if self.solver_glpk.isChecked():
        #     self.eng.eval("solver = 'glpk';", nargout=0)

        if self.smalles_mcs_first.isChecked():
            enum_method = 1
        elif self.mcs_by_cardinality.isChecked():
            enum_method = 2
        elif self.any_mcs.isChecked():
            enum_method = 3

        # if self.consider_scenario.isChecked():
        #     self.eng.eval("reac_box_vals = 1;", nargout=0)
        # else:
        #     self.eng.eval("reac_box_vals = 0;", nargout=0)

        stdf = cobra.util.array.create_stoichiometric_matrix(self.appdata.project.cobra_py_model, array_type='DataFrame')
        rev = [r.reversibility for r in self.appdata.project.cobra_py_model.reactions]
        reac_id = stdf.columns.tolist()
        reac_id_symbols = cMCS_enumerator.get_reac_id_symbols(reac_id)
        # reac_id_symbols = cMCS_enumerator.get_reac_id_symbols(self.appdata.project.cobra_py_model.reactions.list_attr("id"))
        rows = self.target_list.rowCount()
        targets = dict()
        for i in range(0, rows):
            p1 = self.target_list.cellWidget(i, 0).text()
            p2 = self.target_list.cellWidget(i, 1).text()
            if len(p1) > 0 and len(p2) > 0:
                if self.target_list.cellWidget(i, 2).currentText() == '≤':
                    p3 = "<="
                else:
                    p3 = ">="
                p4 = float(self.target_list.cellWidget(i, 3).text())
                targets.setdefault(p1, []).append((p2, p3, p4))
        targets = list(targets.values())
        print(targets)
        targets = [cMCS_enumerator.relations2leq_matrix(cMCS_enumerator.parse_relations(t, reac_id_symbols=reac_id_symbols), reac_id) for t in targets]
        print(targets)

        rows = self.desired_list.rowCount()
        desired = dict()
        for i in range(0, rows):
            p1 = self.desired_list.cellWidget(i, 0).text()
            p2 = self.desired_list.cellWidget(i, 1).text()
            if len(p1) > 0 and len(p2) > 0:
                if self.desired_list.cellWidget(i, 2).currentText() == '≤':
                    p3 = "<="
                else:
                    p3 = ">="
                p4 = float(self.desired_list.cellWidget(i, 3).text())
                desired.setdefault(p1, []).append((p2, p3, p4))
        print(desired)
        desired = list(desired.values())
        desired = [cMCS_enumerator.relations2leq_matrix(cMCS_enumerator.parse_relations(d, reac_id_symbols=reac_id_symbols), reac_id) for d in desired]
        print(desired)

        e = cMCS_enumerator.ConstrainedMinimalCutSetsEnumerator(optlang.glpk_interface, stdf.values, rev, targets, desired=desired,
                                        bigM= 100, threshold=0.1, split_reversible_v=True, irrev_geq=True)
        mcs = e.enumerate_mcs(max_mcs_size=max_mcs_size, max_mcs_num=max_mcs_num, enum_method=enum_method)
        print(mcs)

        if len(mcs) == 0:
            QMessageBox.information(self, 'No cut sets',
                                          'Cut sets have not been calculated or do not exist.')
            return targets, desired
        else:
            omcs = [{reac_id[i]: 0 for i in m} for m in mcs]
            self.appdata.project.modes = omcs
            self.centralwidget.mode_navigator.current = 0
            QMessageBox.information(self, 'Cut sets found',
                                          str(len(omcs))+' Cut sets have been calculated.')

        self.centralwidget.update_mode()
        self.centralwidget.mode_navigator.title.setText("MCS Navigation")
