"""The dialog for calculating minimal cut sets"""

import io
import os
import traceback
import scipy
from random import randint
from importlib import find_loader as module_exists
from qtpy.QtCore import Qt, Slot
from qtpy.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QCompleter,
                            QDialog, QGroupBox, QHBoxLayout, QHeaderView,
                            QLabel, QLineEdit, QMessageBox, QPushButton,
                            QRadioButton, QTableWidget, QVBoxLayout, QSpacerItem)
import cobra
from cobra.util.solver import interface_to_str
from cnapy.appdata import AppData
import cnapy.utils as utils
from mcs import SD_Module, lineqlist2str, linexprdict2str
from mcs.names import *
from cnapy.flux_vector_container import FluxVectorContainer

MCS_STR = 'MCS'
MCS_BILVL_STR = 'MCS bilevel'
OPTKNOCK_STR = 'OptKnock'
ROBUSTKNOCK_STR = 'RobustKnock'
OPTCOUPLE_STR = 'OptCouple'
MODULE_TYPES = [MCS_STR, MCS_BILVL_STR, OPTKNOCK_STR, ROBUSTKNOCK_STR, OPTCOUPLE_STR]
CURR_MODULE = 'current_module'

def BORDER_COLOR(HEX): # string that defines style sheet for changing the color of the module-box
    return "QGroupBox#EditModule "+\
                "{ border: 1px solid "+HEX+";"+\
                "  padding: 12 5 0 0 em ;"+\
                "  margin: 0 0 0 0 em};"

class SDDialog(QDialog):
    """A dialog to perform strain design computations"""

    def __init__(self, appdata: AppData, central_widget):
        QDialog.__init__(self)
        self.setWindowTitle("Strain Design Computation")

        self.appdata = appdata
        self.central_widget = central_widget
        self.eng = appdata.engine
        self.out = io.StringIO()
        self.err = io.StringIO()

        self.completer = QCompleter(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        
        numr = len(self.appdata.project.cobra_py_model.reactions)
        if numr > 2:
            r1 = self.appdata.project.cobra_py_model.reactions[randint(0,numr)].id
            r2 = self.appdata.project.cobra_py_model.reactions[randint(0,numr)].id
            r3 = self.appdata.project.cobra_py_model.reactions[randint(0,numr)].id
            self.placeholder_eq = 'e.g.: "'+r1+' - "'+r2+'" <= 2" or "'+r3+'" = -1.5"'
            placeholder_expr = 'e.g.: "'+r1+'" or "-0.75 '+r2+' + '+r3+'"'
            placeholder_rid = 'e.g.: "'+r1+'"'
        else:
            self.placeholder_eq = 'e.g.: "R1 - R2 <= 2" or "R3 = -1.5"'
            placeholder_expr = 'e.g.: "R1" or "-0.75 R2 + R3"'
            placeholder_rid = 'e.g.: "R1"'
        
        self.modules = []
        self.layout = QVBoxLayout()
        modules_box = QGroupBox("Strain Design module(s)")
        
        # layout for modules list and buttons
        modules_layout = QHBoxLayout()
        self.module_list = QTableWidget(0, 2)
        module_add_rem_buttons = QVBoxLayout()
        modules_layout.addWidget(self.module_list)
        modules_layout.addItem(module_add_rem_buttons)
        
        # modules list
        self.module_list.setFixedWidth(190)
        self.module_list.setHorizontalHeaderLabels(["Module Type",""])
        # self.module_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.module_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.module_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.module_list.horizontalHeader().resizeSection(0, 110)
        self.module_list.horizontalHeader().resizeSection(1, 60)
        # self.modules = [None]
        # combo = QComboBox(self.module_list)
        # combo.insertItems(0,MODULE_TYPES)
        # combo.currentTextChanged.connect(self.sel_module_type)
        # self.module_list.setCellWidget(0, 0, combo)
        # module_edit_button = QPushButton("Edit ...")
        # module_edit_button.clicked.connect(self.edit_module)
        # module_edit_button.setMaximumWidth(60)
        # self.module_list.setCellWidget(0, 1, module_edit_button)

        # module add and remove buttons
        add_module_button = QPushButton("+")
        add_module_button.clicked.connect(self.add_module)
        add_module_button.setMaximumWidth(20)
        rem_module_button = QPushButton("-")
        rem_module_button.clicked.connect(self.rem_module)
        rem_module_button.setMaximumWidth(20)
        module_add_rem_buttons.addWidget(add_module_button)
        module_add_rem_buttons.addWidget(rem_module_button)
        module_add_rem_buttons.addStretch()
        
        # edit module area
        self.module_spec_box = QGroupBox("Module 1 specifications (MCS)")
        self.module_spec_box.setObjectName("EditModule")
        self.module_spec_box.setStyleSheet(BORDER_COLOR("#b0b0b0"))
        module_spec_layout = QVBoxLayout()
        module_spec_layout.setAlignment(Qt.AlignTop)
        self.module_edit = {}
        
        # module sense
        self.module_edit[MODULE_SENSE+"_label"] = QLabel("Maintain (desired) or eliminate (undesired) flux region")
        self.module_edit[MODULE_SENSE] = QComboBox()
        module_spec_layout.addWidget(self.module_edit[MODULE_SENSE+"_label"] )
        self.module_edit[MODULE_SENSE].insertItems(1,[UNDESIRED,DESIRED])
        module_spec_layout.addWidget(self.module_edit[MODULE_SENSE])
        
        # Outer objective
        self.module_edit[OUTER_OBJECTIVE+"_label"] = QLabel("Outer objective (maximized)")
        self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(True)
        self.module_edit[OUTER_OBJECTIVE] = ReceiverLineEdit(self)
        self.module_edit[OUTER_OBJECTIVE].setCompleter(self.completer)
        self.module_edit[OUTER_OBJECTIVE].setPlaceholderText(placeholder_expr)
        self.module_edit[OUTER_OBJECTIVE].setHidden(True)
        module_spec_layout.addWidget(self.module_edit[OUTER_OBJECTIVE+"_label"] )
        module_spec_layout.addWidget(self.module_edit[OUTER_OBJECTIVE])
        
        # Inner objective
        self.module_edit[INNER_OBJECTIVE+"_label"] = QLabel("Inner objective (maximized)")
        self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(True)
        self.module_edit[INNER_OBJECTIVE] = ReceiverLineEdit(self)
        self.module_edit[INNER_OBJECTIVE].setCompleter(self.completer)
        self.module_edit[INNER_OBJECTIVE].setPlaceholderText(placeholder_expr)
        self.module_edit[INNER_OBJECTIVE].setHidden(True)
        module_spec_layout.addWidget(self.module_edit[INNER_OBJECTIVE+"_label"])
        module_spec_layout.addWidget(self.module_edit[INNER_OBJECTIVE])
        
        optcouple_layout = QHBoxLayout()
        # Product ID
        optcouple_layout_prod = QVBoxLayout()
        self.module_edit[PROD_ID+"_label"]  = QLabel("Product synthesis reaction ID")
        self.module_edit[PROD_ID+"_label"].setHidden(True)
        self.module_edit[PROD_ID] = ReceiverLineEdit(self)
        self.module_edit[PROD_ID].setCompleter(self.completer)
        self.module_edit[PROD_ID].setPlaceholderText(placeholder_rid)
        self.module_edit[PROD_ID].setHidden(True)
        optcouple_layout_prod.addWidget(self.module_edit[PROD_ID+"_label"])
        optcouple_layout_prod.addWidget(self.module_edit[PROD_ID])
        optcouple_layout.addItem(optcouple_layout_prod)
        #
        # minimal growth coupling potential
        optcouple_layout_mingcp = QVBoxLayout()
        self.module_edit[MIN_GCP+"_label"] = QLabel("Minimal growth coupling potential (float)")
        self.module_edit[MIN_GCP+"_label"].setHidden(True)
        self.module_edit[MIN_GCP] = ReceiverLineEdit(self)
        self.module_edit[MIN_GCP].setHidden(True)
        self.module_edit[MIN_GCP].setPlaceholderText("e.g. 1.3")
        optcouple_layout_mingcp.addWidget(self.module_edit[MIN_GCP+"_label"])
        optcouple_layout_mingcp.addWidget(self.module_edit[MIN_GCP])
        optcouple_layout.addItem(optcouple_layout_mingcp)
        module_spec_layout.addItem(optcouple_layout)
        
        # module constraints
        self.module_edit[CONSTRAINTS+"_label"] = QLabel("Constraints")
        module_spec_layout.addWidget(self.module_edit[CONSTRAINTS+"_label"])
        constr_list_layout = QHBoxLayout()
        constr_list_layout.setAlignment(Qt.AlignLeft)
        module_spec_layout.addItem(constr_list_layout)
        
        # layout for constraint list and buttons
        self.module_edit[CONSTRAINTS] = QTableWidget(0, 1)
        self.module_edit[CONSTRAINTS].horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.module_edit[CONSTRAINTS].setHorizontalHeaderLabels([" "])
        # constr_entry = ReceiverLineEdit(self)
        # constr_entry.setCompleter(self.completer)
        # constr_entry.setPlaceholderText(self.placeholder_eq)
        # self.module_edit[CONSTRAINTS].setCellWidget(0, 0, constr_entry)
        # self.active_receiver = constr_entry
        constr_list_layout.addWidget(self.module_edit[CONSTRAINTS])
        
        # buttons to add and remove constraint
        constraint_add_rem_buttons = QVBoxLayout()
        self.module_edit["add_constr_button"] = QPushButton("+")
        self.module_edit["add_constr_button"].clicked.connect(self.add_constr)
        self.module_edit["add_constr_button"].setMaximumWidth(20)
        self.module_edit["rem_constr_button"] = QPushButton("-")
        self.module_edit["rem_constr_button"].clicked.connect(self.rem_constr)
        self.module_edit["rem_constr_button"].setMaximumWidth(20)
        constraint_add_rem_buttons.addWidget(self.module_edit["add_constr_button"])
        constraint_add_rem_buttons.addWidget(self.module_edit["rem_constr_button"])
        constraint_add_rem_buttons.addStretch()
        constr_list_layout.addItem(constraint_add_rem_buttons)
                        
        # validate module button
        module_buttons_layout = QHBoxLayout()
        self.module_edit["module_apply_button"] = QPushButton("Apply")
        self.module_edit["module_apply_button"].clicked.connect(self.module_apply)
        self.module_edit["module_apply_button"].setProperty(CURR_MODULE,0)
        self.module_edit["module_del_button"] = QPushButton("Delete")
        self.module_edit["module_del_button"].clicked.connect(self.rem_module,True)
        module_buttons_layout.addWidget(self.module_edit["module_apply_button"])
        module_buttons_layout.addWidget(self.module_edit["module_del_button"])
        module_spec_layout.addItem(module_buttons_layout)
        
        self.module_spec_box.setLayout(module_spec_layout)

        modules_layout.addWidget(self.module_spec_box)

        # complete box
        modules_box.setLayout(modules_layout)
        
        self.update_module_edit()
        
        self.show()
        print("hi")
        
        # self.target_list.setCellWidget(0, 0, item)
        # item2 = ReceiverLineEdit(self)
        # item2.setCompleter(completer)
        # self.target_list.setCellWidget(0, 1, item2)
        # self.active_receiver = item2
        
        # self.s12 = ()

        self.layout.addWidget(modules_box)
        # self.layout.addItem(s1)
        
        avail_solvers = []
        if module_exists('swiglpk'):
            avail_solvers += ['glpk']
        if module_exists('cplex'):
            avail_solvers += ['cplex']
        if module_exists('gurobipy'):
            avail_solvers += ['gurobi']
        if module_exists('pyscipopt'):
            avail_solvers += ['scip']

        s3 = QHBoxLayout()

        sgx = QVBoxLayout()
        self.gen_kos = QCheckBox("Gene KOs")
        self.exclude_boundary = QCheckBox(
            "Exclude boundary\nreactions as cuts")
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
        sgx.addWidget(self.exclude_boundary)
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
        self.solver_cplex_java = QRadioButton("CPLEX (Octave)")
        self.solver_cplex_java.setToolTip("Only enabled with Octave and CPLEX")
        s33.addWidget(self.solver_cplex_java)
        self.bg1.addButton(self.solver_cplex_java)
        self.solver_intlinprog = QRadioButton("intlinprog (MATLAB)")
        self.solver_intlinprog.setToolTip("Only enabled with MATLAB")
        s33.addWidget(self.solver_intlinprog)
        self.bg1.addButton(self.solver_intlinprog)
        self.solver_glpk = QRadioButton("GLPK (Octave/MATLAB)")
        s33.addWidget(self.solver_glpk)
        self.bg1.addButton(self.solver_glpk)
        self.bg1.buttonClicked.connect(self.configure_solver_options)
        g3.setLayout(s33)
        s3.addWidget(g3)

        g4 = QGroupBox("MCS search")
        s34 = QVBoxLayout()
        self.bg2 = QButtonGroup()
        self.any_mcs = QRadioButton("any MCS (fast)")
        self.any_mcs.setChecked(True)
        s34.addWidget(self.any_mcs)
        self.bg2.addButton(self.any_mcs)

        # Search type: by cardinality only with CPLEX/Gurobi possible
        self.mcs_by_cardinality = QRadioButton("by cardinality")
        s34.addWidget(self.mcs_by_cardinality)
        self.bg2.addButton(self.mcs_by_cardinality)

        self.smalles_mcs_first = QRadioButton("smallest MCS first")
        s34.addWidget(self.smalles_mcs_first)
        self.bg2.addButton(self.smalles_mcs_first)


        # Disable incompatible combinations
        deactivate_external_solvers = False
        if (appdata.selected_engine == 'None') or (self.eng is None) or (not appdata.cna_ok):  # Hotfix
            deactivate_external_solvers = True

        if not deactivate_external_solvers:
            # The following try-except block is added as a workaround as long as the
            # current CNA version cannot be directly read.
            try:
                self.solver_cplex_matlab.setEnabled(
                    self.eng.is_cplex_matlab_ready())
                self.solver_cplex_java.setEnabled(self.eng.is_cplex_java_ready())
                self.solver_intlinprog.setEnabled(self.appdata.is_matlab_set())
            except Exception:  # Either a Matlab or an Octave error due to a wrong configuration of CellNetAnalyzer
                msgBox = QMessageBox()
                msgBox.setWindowTitle("CellNetAnalyzer error!")
                msgBox.setTextFormat(Qt.RichText)
                msgBox.setText("<p>Error when loading CellNetAnalyzer. MCS calculation only possible with cobrapy solvers.<br>"
                               "This error may be resolved in one of the following ways:<br>"
                               "1. Check that you have the latest CellNetAnalyzer version and that you have set in in CNApy's configuration correctly.<br>"
                               "2. If CellNetAnalyzer is up-to-date and correctly set in CNApy and this error still occurs, check that you can successfully run CellNetAnalyzer using MATLAB or Octave. "
                               "</p>")
                msgBox.setIcon(QMessageBox.Warning)
                msgBox.exec()
                deactivate_external_solvers = True

        if deactivate_external_solvers:
            self.solver_cplex_matlab.setEnabled(False)
            self.solver_cplex_java.setEnabled(False)
            self.solver_glpk.setEnabled(False)
            self.solver_intlinprog.setEnabled(False)

        self.configure_solver_options()

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
        self.cancel = QPushButton("Close")
        buttons.addWidget(self.cancel)
        self.layout.addItem(buttons)

        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.compute_mcs.clicked.connect(self.compute)

        self.central_widget.broadcastReactionID.connect(self.receive_input)

    @Slot(str)
    def receive_input(self, text):
        completer_mode = self.active_receiver.completer().completionMode()
        # temporarily disable completer popup
        self.active_receiver.completer().setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
        self.active_receiver.insert(text)
        self.active_receiver.completer().setCompletionMode(completer_mode)

    @Slot()
    def configure_solver_options(self):  # called when switching solver
        self.gen_kos.setEnabled(True)
        self.exclude_boundary.setChecked(False)
        self.exclude_boundary.setEnabled(False)
        if self.solver_cplex_matlab.isChecked() or self.solver_cplex_java.isChecked():
            self.mcs_by_cardinality.setEnabled(True)
        else:
            self.mcs_by_cardinality.setEnabled(False)
            if self.mcs_by_cardinality.isChecked():
                self.any_mcs.setChecked(True)

    def add_module(self):
        i = self.module_list.rowCount()
        self.module_list.insertRow(i)
        
        combo = QComboBox(self.module_list)
        combo.insertItems(0,MODULE_TYPES)
        combo.currentTextChanged.connect(self.sel_module_type)
        self.module_list.setCellWidget(i, 0, combo)
        module_edit_button = QPushButton("Edit ...")
        module_edit_button.clicked.connect(self.edit_module)
        module_edit_button.setMaximumWidth(60)
        self.module_list.setCellWidget(i, 1, module_edit_button)
        self.modules.append(None)
        if i == 0:
            self.module_edit["module_apply_button"].setProperty(CURR_MODULE,i)
            self.update_module_edit()

    def rem_module(self,*args):
        if self.module_list.rowCount() == 0:
            return
        current_module = self.module_edit["module_apply_button"].property(CURR_MODULE)
        if args:
            i = current_module
        if self.module_list.selectedIndexes():
            i = self.module_list.selectedIndexes()[0].row()
        else:
            i = self.module_list.rowCount()-1
        self.module_list.removeRow(i)
        self.modules.pop(i)
        if i == current_module:
            last_module = self.module_list.rowCount()-1
            self.module_edit["module_apply_button"].setProperty(CURR_MODULE,last_module)
            self.update_module_edit()
        
    def edit_module(self):
        current_module = self.module_edit["module_apply_button"].property(CURR_MODULE)
        # if current module is valid, load the module that was newly selected
        valid, module = self.verify_module(current_module)
        if valid:
            self.modules[current_module] = module
        else:
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#ff726b"))
            return
        selected_module = self.module_list.selectedIndexes()[0].row()
        self.module_edit["module_apply_button"].setProperty(CURR_MODULE,selected_module)
        self.update_module_edit()
        
    def sel_module_type(self):
        i = self.module_list.selectedIndexes()[0].row()
        self.modules[i] = None
        if i == self.module_edit["module_apply_button"].property(CURR_MODULE):
            self.update_module_edit()
        
    def add_constr(self):
        i = self.module_edit[CONSTRAINTS].rowCount()
        self.module_edit[CONSTRAINTS].insertRow(i)
        constr_entry = ReceiverLineEdit(self)
        constr_entry.setCompleter(self.completer)
        constr_entry.setPlaceholderText(self.placeholder_eq)
        self.active_receiver = constr_entry
        self.module_edit[CONSTRAINTS].setCellWidget(i, 0, constr_entry)

    def rem_constr(self):
        if self.module_edit[CONSTRAINTS].rowCount() == 0:
            return
        if self.module_edit[CONSTRAINTS].selectedIndexes():
            i = self.module_edit[CONSTRAINTS].selectedIndexes()[0].row()
        else:
            i = self.module_edit[CONSTRAINTS].rowCount()-1
        self.module_edit[CONSTRAINTS].removeRow(i)
    
    def module_apply(self):
        current_module = self.module_edit["module_apply_button"].property(CURR_MODULE)
        valid, module = self.verify_module(current_module)
        if valid:
            self.modules[current_module] = module
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#8bff87"))
        else:
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#ff726b"))
    
    def update_module_edit(self):
        if not self.modules: # remove everything
            self.module_spec_box.setTitle('Please add a module')
            self.module_edit["module_apply_button"].setHidden(	    True)
            self.module_edit["module_del_button"].setHidden(	    True)
            self.module_edit[CONSTRAINTS].setHidden(	            True)
            self.module_edit[CONSTRAINTS+"_label"].setHidden(	    True)
            self.module_edit["rem_constr_button"].setHidden(	    True)
            self.module_edit["add_constr_button"].setHidden(	    True)
            self.module_edit[MODULE_SENSE].setHidden(	            True)
            self.module_edit[MODULE_SENSE+"_label"].setHidden(	    True)
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	True)
            self.module_edit[INNER_OBJECTIVE].setHidden(			True)
            self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(	True)
            self.module_edit[OUTER_OBJECTIVE].setHidden( 			True)
            self.module_edit[PROD_ID+"_label"].setHidden( 			True)
            self.module_edit[PROD_ID].setHidden( 					True)
            self.module_edit[MIN_GCP+"_label"].setHidden( 			True)
            self.module_edit[MIN_GCP].setHidden( 					True)
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#b0b0b0"))
            return
        else:
            self.module_edit["module_apply_button"].setHidden(	    False)
            self.module_edit["module_del_button"].setHidden(	    False)
            self.module_edit[CONSTRAINTS].setHidden(	            False)
            self.module_edit[CONSTRAINTS+"_label"].setHidden(	    False)
            self.module_edit["rem_constr_button"].setHidden(	    False)
            self.module_edit["add_constr_button"].setHidden(	    False)
        current_module = self.module_edit["module_apply_button"].property(CURR_MODULE)
        module_type = self.module_list.cellWidget(current_module,0).currentText()
        self.module_spec_box.setTitle('Module '+str(current_module+1)+' specifications ('+module_type+')')
        if not self.modules[current_module]:
            self.module_edit[MODULE_SENSE].setCurrentText("")
            self.module_edit[INNER_OBJECTIVE].setText("")
            self.module_edit[OUTER_OBJECTIVE].setText("")
            self.module_edit[PROD_ID].setText("")
            self.module_edit[MIN_GCP].setText("")
            for _ in range(self.module_edit[CONSTRAINTS].rowCount()):
                self.module_edit[CONSTRAINTS].removeRow(0)
            # uncomment this to add an empty constraint by default
            # self.module_edit[CONSTRAINTS].insertRow(0)
            # constr_entry = ReceiverLineEdit(self)
            # constr_entry.setCompleter(self.completer)
            # self.active_receiver = constr_entry
            # self.module_edit[CONSTRAINTS].setCellWidget(0, 0, constr_entry)
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#b0b0b0"))
        else:
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#8bff87"))
            mod = {}
            mod[MODULE_SENSE]    = self.modules[current_module][MODULE_SENSE]
            mod[CONSTRAINTS]     = self.modules[current_module][CONSTRAINTS]
            mod[INNER_OBJECTIVE] = self.modules[current_module][INNER_OBJECTIVE]
            mod[OUTER_OBJECTIVE] = self.modules[current_module][OUTER_OBJECTIVE]
            mod[PROD_ID]         = self.modules[current_module][PROD_ID]
            mod[MIN_GCP]         = self.modules[current_module][MIN_GCP]
            
            # remove all former constraints and refill again from module
            for _ in range(self.module_edit[CONSTRAINTS].rowCount()):
                self.module_edit[CONSTRAINTS].removeRow(0)
            constr_entry = [None for _ in range(len(mod[CONSTRAINTS]))]
            for i,c in enumerate(mod[CONSTRAINTS]):
                text = lineqlist2str(c)
                self.module_edit[CONSTRAINTS].insertRow(i)
                constr_entry[i] = ReceiverLineEdit(self)
                constr_entry[i].setText(text)
                constr_entry[i].setCompleter(self.completer)
                self.module_edit[CONSTRAINTS].setCellWidget(i, 0, constr_entry[i])
            # load other information from module
            if mod[MODULE_SENSE]:
                self.module_edit[MODULE_SENSE].setCurrentText(mod[MODULE_SENSE])
            if mod[INNER_OBJECTIVE]:
                self.module_edit[INNER_OBJECTIVE].setText(\
                    linexprdict2str(mod[INNER_OBJECTIVE]))
            if mod[OUTER_OBJECTIVE]:
                self.module_edit[OUTER_OBJECTIVE].setText(\
                    linexprdict2str(mod[OUTER_OBJECTIVE]))
            if mod[PROD_ID]:
                self.module_edit[PROD_ID].setText(\
                    linexprdict2str(mod[PROD_ID]))
            if mod[MIN_GCP]:
                self.module_edit[MIN_GCP].setText(str(mod[MIN_GCP]))

        if module_type == MCS_STR:
            self.module_edit[MODULE_SENSE].setHidden(	            False)
            self.module_edit[MODULE_SENSE+"_label"].setHidden(	    False)
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	True)
            self.module_edit[INNER_OBJECTIVE].setHidden(			True)
            self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(	True)
            self.module_edit[OUTER_OBJECTIVE].setHidden( 			True)
            self.module_edit[PROD_ID+"_label"].setHidden( 			True)
            self.module_edit[PROD_ID].setHidden( 					True)
            self.module_edit[MIN_GCP+"_label"].setHidden( 			True)
            self.module_edit[MIN_GCP].setHidden( 					True)
        elif module_type == MCS_BILVL_STR:
            self.module_edit[MODULE_SENSE].setHidden(	            False)
            self.module_edit[MODULE_SENSE+"_label"].setHidden(	    False)
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[INNER_OBJECTIVE].setHidden(			False)
            self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(	True)
            self.module_edit[OUTER_OBJECTIVE].setHidden( 			True)
            self.module_edit[PROD_ID+"_label"].setHidden( 			True)
            self.module_edit[PROD_ID].setHidden( 					True)
            self.module_edit[MIN_GCP+"_label"].setHidden( 			True)
            self.module_edit[MIN_GCP].setHidden( 					True)
        elif module_type == OPTKNOCK_STR:
            self.module_edit[MODULE_SENSE].setHidden(	            True)
            self.module_edit[MODULE_SENSE+"_label"].setHidden(	    True)
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[INNER_OBJECTIVE].setHidden(			False)
            self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[OUTER_OBJECTIVE].setHidden( 			False)
            self.module_edit[PROD_ID+"_label"].setHidden( 			True)
            self.module_edit[PROD_ID].setHidden( 					True)
            self.module_edit[MIN_GCP+"_label"].setHidden( 			True)
            self.module_edit[MIN_GCP].setHidden( 					True)
        elif module_type == ROBUSTKNOCK_STR:
            self.module_edit[MODULE_SENSE].setHidden(	            True)
            self.module_edit[MODULE_SENSE+"_label"].setHidden(	    True)
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[INNER_OBJECTIVE].setHidden(			False)
            self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[OUTER_OBJECTIVE].setHidden( 			False)
            self.module_edit[PROD_ID+"_label"].setHidden( 			True)
            self.module_edit[PROD_ID].setHidden( 					True)
            self.module_edit[MIN_GCP+"_label"].setHidden( 			True)
            self.module_edit[MIN_GCP].setHidden( 					True)
        elif module_type == OPTCOUPLE_STR:
            self.module_edit[MODULE_SENSE].setHidden(	            True)
            self.module_edit[MODULE_SENSE+"_label"].setHidden(	    True)
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[INNER_OBJECTIVE].setHidden(			False)
            self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(	True)
            self.module_edit[OUTER_OBJECTIVE].setHidden( 			True)
            self.module_edit[PROD_ID+"_label"].setHidden( 			False)
            self.module_edit[PROD_ID].setHidden( 					False)
            self.module_edit[MIN_GCP+"_label"].setHidden( 			False)
            self.module_edit[MIN_GCP].setHidden( 					False)
    
    def verify_module(self,*args):
        module_no = args[0]
        module_type = self.module_list.cellWidget(module_no,0).currentText()
        # retrieve module infos from gui
        constraints = [self.module_edit[CONSTRAINTS].cellWidget(i,0).text() \
                            for i in range(self.module_edit[CONSTRAINTS].rowCount())]
        module_sense = self.module_edit[MODULE_SENSE].currentText()
        inner_objective = self.module_edit[INNER_OBJECTIVE].text()
        outer_objective = self.module_edit[OUTER_OBJECTIVE].text()
        prod_id = self.module_edit[PROD_ID].text()
        min_gcp = self.module_edit[MIN_GCP].text()
        if min_gcp:
            min_gcp = float(min_gcp)
        else:
            min_gcp = 0.0
        # adapt model
        try:
            with self.appdata.project.cobra_py_model as model:
                if self.consider_scenario.isChecked():  # integrate scenario into model bounds
                    for r in self.appdata.project.scen_values.keys():
                        model.reactions.get_by_id(r).bounds = self.appdata.project.scen_values[r]
                if module_type == MCS_STR:
                    module = SD_Module(model,module_type=MCS_LIN, \
                                        module_sense=module_sense, constraints=constraints)
                elif module_type == MCS_BILVL_STR:
                    module = SD_Module(model,module_type=MCS_BILVL, inner_objective=inner_objective,\
                                        inner_opt_sense=MAXIMIZE, module_sense=module_sense, \
                                        constraints=constraints)
                elif module_type == OPTKNOCK_STR:
                    module = SD_Module(model,module_type=OPTKNOCK, inner_objective=inner_objective,\
                                        inner_opt_sense=MAXIMIZE, outer_objective=outer_objective,\
                                        outer_opt_sense=MAXIMIZE, constraints=constraints)
                elif module_type == ROBUSTKNOCK_STR:
                    module = SD_Module(model,module_type=ROBUSTKNOCK, inner_objective=inner_objective,\
                                        inner_opt_sense=MAXIMIZE, outer_objective=outer_objective,\
                                        outer_opt_sense=MAXIMIZE, constraints=constraints)
                elif module_type == OPTCOUPLE_STR:
                    module = SD_Module(model,module_type=OPTCOUPLE, inner_objective=inner_objective,\
                                        inner_opt_sense=MAXIMIZE, prod_id=prod_id,\
                                        min_gcp=min_gcp, constraints=constraints)
            return True, module
        except:
            return False, None
            # paint frame red

    def compute(self):
        mcs_equation_errors = self.check_for_mcs_equation_errors()


    def compute_legacy(self):
        self.setCursor(Qt.BusyCursor)
        # create CobraModel for matlab
        with self.appdata.project.cobra_py_model as model:
            if self.consider_scenario.isChecked():  # integrate scenario into model bounds
                for r in self.appdata.project.scen_values.keys():
                    model.reactions.get_by_id(
                        r).bounds = self.appdata.project.scen_values[r]
            cobra.io.save_matlab_model(model, os.path.join(
                self.appdata.cna_path, "cobra_model.mat"), varname="cbmodel")
        self.eng.eval("load('cobra_model.mat')",
                      nargout=0)

        try:
            self.eng.eval("cnap = CNAcobra2cna(cbmodel);",
                          nargout=0,
                          stdout=self.out, stderr=self.err)
        except Exception:
            output = io.StringIO()
            traceback.print_exc(file=output)
            exstr = output.getvalue()
            print(exstr)
            utils.show_unknown_error_box(exstr)
            return

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
        elif self.mcs_by_cardinality.isChecked():
            self.eng.eval("mcs_search_mode = 'search_2';", nargout=0)
        elif self.smalles_mcs_first.isChecked():
            self.eng.eval("mcs_search_mode = 'search_3';", nargout=0)

        rows = self.module_list.rowCount()
        for i in range(0, rows):
            p1 = self.module_list.cellWidget(i, 0).text()
            p2 = self.module_list.cellWidget(i, 1).text()
            if self.module_list.cellWidget(i, 2).currentText() == '≤':
                p3 = "<="
            else:
                p3 = ">="
            p4 = self.module_list.cellWidget(i, 3).text()
            cmd = "dg_T = {[" + p1+"], '" + p2 + \
                "', '" + p3 + "', [" + p4 + "']};"
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
                self.eng.eval("[mcs] = cnapy_compute_mcs(cnap, genes, maxSolutions, maxSize, milp_time_limit, gKOs, advanced_on, solver, mcs_search_mode, dg_T,dg_D);",
                              nargout=0)
            except Exception:
                output = io.StringIO()
                traceback.print_exc(file=output)
                exstr = output.getvalue()
                print(exstr)
                utils.show_unknown_error_box(exstr)
                return
            else:
                self.eng.eval("[reaction, mcs, value] = find(mcs);", nargout=0,
                              stdout=self.out, stderr=self.err)
                reactions = self.eng.workspace['reaction']
                mcs = self.eng.workspace['mcs']
                values = self.eng.workspace['value']
        elif self.appdata.is_octave_ready():
            reac_id = self.eng.pull('reac_id')
            reac_id = reac_id[0].tolist()
            try:
                self.eng.eval("[mcs] = cnapy_compute_mcs(cnap, genes, maxSolutions, maxSize, milp_time_limit, gKOs, advanced_on, solver, mcs_search_mode, dg_T,dg_D);",
                              nargout=0)
            except Exception:
                output = io.StringIO()
                traceback.print_exc(file=output)
                exstr = output.getvalue()
                print(exstr)
                utils.show_unknown_error_box(exstr)
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
            # omcs = []
            # print(mcs, type(mcs), type(reac_id))
            # print(mcs[-1][0])
            num_mcs = int(mcs[-1][0])
            omcs = scipy.sparse.lil_matrix((num_mcs, len(reac_id)))
            # current_mcs = {}
            for i, reaction in enumerate(reactions):
                # print(mcs[i][0], reaction[0], values[i][0])
                omcs[mcs[i][0]-1, reaction[0]-1] = values[i][0]
            #     reacid = int(reaction[0])
            #     reaction = reac_id[reacid-1]
            #     c_mcs = int(mcs[i][0])
            #     c_value = int(values[i][0])
            #     if c_value == -1:  # -1 stands for removed which is 0 in the ui
            #         c_value = -1.0
            #     if c_mcs > last_mcs:
            #         omcs.append(current_mcs)
            #         last_mcs = c_mcs
            #         current_mcs = {}
            #     current_mcs[reaction] = c_value
            # omcs.append(current_mcs)
            # self.appdata.project.modes = omcs
            self.appdata.project.modes = FluxVectorContainer(omcs, reac_id=reac_id)
            self.central_widget.mode_navigator.current = 0
            QMessageBox.information(self, 'Cut sets found',
                                          str(num_mcs)+' Cut sets have been calculated.')
                                        #   str(len(omcs))+' Cut sets have been calculated.')

        self.central_widget.mode_navigator.set_to_mcs()
        self.central_widget.update_mode()

        self.setCursor(Qt.ArrowCursor)

    def compute_optlang(self):
        max_mcs_num = float(self.max_solu.text())
        max_mcs_size = int(self.max_size.text())
        timeout = float(self.time_limit.text())
        if timeout == float('inf'):
            timeout = None

        if self.smalles_mcs_first.isChecked():
            enum_method = 1
        elif self.mcs_by_cardinality.isChecked():
            enum_method = 2
        elif self.any_mcs.isChecked():
            enum_method = 3
        elif self.mcs_continuous_search.isChecked():
            enum_method = 4

        with self.appdata.project.cobra_py_model as model:
            update_stoichiometry_hash = False
            if self.consider_scenario.isChecked():  # integrate scenario into model bounds
                self.appdata.project.load_scenario_into_model(model)
                if len(self.appdata.project.scen_values) > 0:
                    update_stoichiometry_hash = True
            for r in model.reactions:  # make all reactions bounded for COBRApy FVA
                if r.lower_bound == -float('inf'):
                    r.lower_bound = cobra.Configuration().lower_bound
                    r.set_hash_value()
                    update_stoichiometry_hash = True
                if r.upper_bound == float('inf'):
                    r.upper_bound = cobra.Configuration().upper_bound
                    r.set_hash_value()
                    update_stoichiometry_hash = True
            if self.appdata.use_results_cache and update_stoichiometry_hash:
                model.set_stoichiometry_hash_object()
            reac_id = model.reactions.list_attr("id")
            reac_id_symbols = mcs_computation.get_reac_id_symbols(reac_id)
            rows = self.module_list.rowCount()
            targets = dict()
            for i in range(0, rows):
                p1 = self.module_list.cellWidget(i, 0).text()
                p2 = self.module_list.cellWidget(i, 1).text()
                if len(p1) > 0 and len(p2) > 0:
                    if self.module_list.cellWidget(i, 2).currentText() == '≤':
                        p3 = "<="
                    else:
                        p3 = ">="
                    p4 = float(self.module_list.cellWidget(i, 3).text())
                    targets.setdefault(p1, []).append((p2, p3, p4))
            targets = list(targets.values())
            try:
                targets = [mcs_computation.relations2leq_matrix(mcs_computation.parse_relations(
                    t, reac_id_symbols=reac_id_symbols), reac_id) for t in targets]
            except ValueError:
                QMessageBox.warning(self, "Failed to parse the target region(s)",
                                    "Check that the equations are correct.")
                return

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
            desired = list(desired.values())
            try:
                desired = [mcs_computation.relations2leq_matrix(mcs_computation.parse_relations(
                    d, reac_id_symbols=reac_id_symbols), reac_id) for d in desired]
            except ValueError:
                QMessageBox.warning(self, "Failed to parse the desired region(s)",
                                    "Check that the equations are correct.")
                return

            self.setCursor(Qt.BusyCursor)
            try:
                mcs, err_val = mcs_computation.compute_mcs(model,
                                targets=targets, desired=desired, enum_method=enum_method,
                                max_mcs_size=max_mcs_size, max_mcs_num=max_mcs_num, timeout=timeout,
                                exclude_boundary_reactions_as_cuts=self.exclude_boundary.isChecked(),
                                results_cache_dir=self.appdata.results_cache_dir
                                if self.appdata.use_results_cache else None)
            except mcs_computation.InfeasibleRegion as e:
                QMessageBox.warning(self, 'Cannot calculate MCS', str(e))
                return targets, desired
            except Exception:
                output = io.StringIO()
                traceback.print_exc(file=output)
                exstr = output.getvalue()
                print(exstr)
                utils.show_unknown_error_box(exstr)
                return targets, desired
            finally:
                self.setCursor(Qt.ArrowCursor)

        print(err_val)
        if err_val == 1:
            QMessageBox.warning(self, "Enumeration stopped abnormally",
                                "Result is probably incomplete.\nCheck console output for more information.")
        elif err_val == -1:
            QMessageBox.warning(self, "Enumeration terminated permaturely",
                                "Aborted due to excessive generation of candidates that are not cut sets.\n"
                                "Modify the problem or try a different enumeration setup.")

        if len(mcs) == 0:
            QMessageBox.information(self, 'No cut sets',
                                          'Cut sets have not been calculated or do not exist.')
            return targets, desired

        # omcs = [{reac_id[i]: -1.0 for i in m} for m in mcs]
        omcs = scipy.sparse.lil_matrix((len(mcs), len(reac_id)))
        for i,m in enumerate(mcs):
            for j in m:
                omcs[i, j] = -1.0
        # self.appdata.project.modes = omcs
        self.appdata.project.modes = FluxVectorContainer(omcs, reac_id=reac_id)
        self.central_widget.mode_navigator.current = 0
        QMessageBox.information(self, 'Cut sets found',
                                      str(len(mcs))+' Cut sets have been calculated.')

        self.central_widget.mode_navigator.set_to_mcs()
        self.central_widget.update_mode()
        self.accept()

    def check_left_mcs_equation(self, equation: str) -> str:
        errors = ""

        semantics = []
        reaction_ids = []
        last_part = ""
        counter = 1
        for char in equation+" ":
            if (char == " ") or (char in ("*", "/", "+", "-")) or (counter == len(equation+" ")):
                if last_part != "":
                    try:
                        float(last_part)
                    except ValueError:
                        reaction_ids.append(last_part)
                        semantics.append("reaction")
                    else:
                        semantics.append("number")
                    last_part = ""

                if counter == len(equation+" "):
                    break

            if char in "*":
                semantics.append("multiplication")
            elif char in "/":
                semantics.append("division")
            elif char in ("+", "-"):
                semantics.append("dash")
            elif char not in " ":
                last_part += char
            counter += 1

        if len(reaction_ids) == 0:
            errors += f"EQUATION ERROR in {equation}:\nNo reaction ID is given in the equation\n"

        if semantics.count("division") > 1:
            errors += f"ERROR in {equation}:\nAn equation must not have more than one /"

        last_is_multiplication = False
        last_is_division = False
        last_is_dash = False
        last_is_reaction = False
        prelast_is_reaction = False
        prelast_is_dash = False
        last_is_number = False
        is_start = True
        for semantic in semantics:
            if is_start:
                if semantic in ("multiplication", "division"):
                    errors += f"ERROR in {equation}:\nAn equation must not start with * or /"
                is_start = False

            if (last_is_multiplication or last_is_division) and (semantic in ("multiplication", "division")):
                errors += f"ERROR in {equation}:\n* or / must not follow on * or /\n"
            if last_is_dash and (semantic in ("multiplication", "division")):
                errors += f"ERROR in {equation}:\n* or / must not follow on + or -\n"
            if last_is_number and (semantic == "reaction"):
                errors += f"ERROR in {equation}:\nA reaction must not directly follow on a number without a mathematical operation\n"
            if last_is_reaction and (semantic == "reaction"):
                errors += f"ERROR in {equation}:\nA reaction must not follow on a reaction ID\n"
            if last_is_number and (semantic == "number"):
                errors += f"ERROR in {equation}:\nA number must not follow on a number ID\n"

            if prelast_is_reaction and last_is_multiplication and (semantic == "reaction"):
                errors += f"ERROR in {equation}:\nTwo reactions must not be multiplied together\n"

            if last_is_reaction:
                prelast_is_reaction = True
            else:
                prelast_is_reaction = False

            if last_is_dash:
                prelast_is_dash = True
            else:
                prelast_is_dash = False

            last_is_multiplication = False
            last_is_division = False
            last_is_dash = False
            last_is_reaction = False
            last_is_number = False
            if semantic == "multiplication":
                last_is_multiplication = True
            elif semantic == "division":
                last_is_division = True
            elif semantic == "reaction":
                last_is_reaction = True
            elif semantic == "dash":
                last_is_dash = True
            elif semantic == "number":
                last_is_number = True

        if last_is_dash or last_is_multiplication or last_is_division:
            errors += (f"ERROR in {equation}:\nA reaction must not end "
                       f"with a +, -, * or /")

        if prelast_is_dash and last_is_number:
            errors += (f"ERROR in {equation}:\nA reaction must not end "
                       f"with a separated number term only")

        with self.appdata.project.cobra_py_model as model:
            model_reaction_ids = [x.id for x in model.reactions]
            for reaction_id in reaction_ids:
                if reaction_id not in model_reaction_ids:
                    errors += (f"ERROR in {equation}:\nA reaction with "
                               f"the ID {reaction_id} does not exist in the model\n")

        return errors


    def check_right_mcs_equation(self, equation: str) -> str:
        try:
            float(equation)
        except ValueError:
            error = f"ERROR in {equation}:\nRight equation must be a number\n"
            return error
        else:
            return ""

    def check_for_mcs_equation_errors(self) -> str:
        errors = ""
        rows = self.module_list.rowCount()
        for i in range(0, rows):
            target_left = self.module_list.cellWidget(i, 1).text()
            errors += self.check_left_mcs_equation(target_left)
            target_right = self.module_list.cellWidget(i, 3).text()
            errors += self.check_right_mcs_equation(target_right)

        rows = self.desired_list.rowCount()
        for i in range(0, rows):
            desired_left = self.desired_list.cellWidget(i, 1).text()
            if len(desired_left) > 0:
                errors += self.check_left_mcs_equation(desired_left)

            desired_right = self.desired_list.cellWidget(i, 3).text()
            if len(desired_right) > 0:
                errors += self.check_right_mcs_equation(desired_right)

        return errors

class ReceiverLineEdit(QLineEdit):
    def __init__(self, mcs_dialog):
        super().__init__()
        self.mcs_dialog = mcs_dialog

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.mcs_dialog.active_receiver = self