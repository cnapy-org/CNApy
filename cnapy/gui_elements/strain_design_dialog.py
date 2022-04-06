"""The dialog for calculating minimal cut sets"""

import io
from msilib.schema import CheckBox
import os
import traceback
import scipy
from random import randint
from importlib import find_loader as module_exists
from qtpy.QtCore import Qt, Slot
from qtpy.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QCompleter,
                            QDialog, QGroupBox, QHBoxLayout, QHeaderView,
                            QLabel, QLineEdit, QMessageBox, QPushButton,
                            QRadioButton, QTableWidget, QVBoxLayout, QSplitter,
                            QWidget)
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
        
        # Define placeholder strings for text edit fields
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
        
        ## Upper box of the dialog (for defining modules)
        self.modules = []
        self.layout = QVBoxLayout()
        modules_box = QGroupBox("Strain design module(s)")
        
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
        # -> first entry in module list
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
        # -> first entry in constraint list
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
        
        # connect module edit layout to module edit box
        self.module_spec_box.setLayout(module_spec_layout)
        # connect module edit box to the overall module layout
        modules_layout.addWidget(self.module_spec_box)
        # connect overall module layout to overall module box
        modules_box.setLayout(modules_layout)
        # connect overall module box to editor to the dialog window
        splitter = QSplitter()
        splitter.addWidget(modules_box)
        self.layout.addWidget(splitter)
        
        
        # self.layout.addWidget(modules_box)
        # refresh modules -> remove in case you want default entries in module constraint list
        self.update_module_edit()
        


        ## Check boxes for gene-mcs, entries in network map, solvers, kos and kis

        # checkboxes
        checkboxes = QWidget()
        checkboxes_layout = QVBoxLayout()
        self.gen_kos = QCheckBox(" Gene KOs")
        if not hasattr(self.appdata.project.cobra_py_model,'genes') or \
            len(self.appdata.project.cobra_py_model.genes) == 0:
            self.gen_kos.setEnabled(False)
        checkboxes_layout.addWidget(self.gen_kos)
        
        self.consider_scenario = QCheckBox(
        " Consider constraint(s) given by scenario")
        checkboxes_layout.addWidget(self.consider_scenario)
        
        max_sols_layout = QHBoxLayout()
        l = QLabel(" Max. Solutions")
        self.max_sols = QLineEdit("inf")
        self.max_sols.setMaximumWidth(50)
        max_sols_layout.addWidget(self.max_sols)
        max_sols_layout.addWidget(l)
        checkboxes_layout.addItem(max_sols_layout)
        
        max_size_layout = QHBoxLayout()
        l = QLabel(" Max. Size")
        self.max_size = QLineEdit("7")
        self.max_size.setMaximumWidth(50)
        max_size_layout.addWidget(self.max_size)
        max_size_layout.addWidget(l)
        checkboxes_layout.addItem(max_size_layout)
        
        time_limit_layout = QHBoxLayout()
        l = QLabel(" Time Limit [sec]")
        self.time_limit = QLineEdit("inf")
        self.time_limit.setMaximumWidth(50)
        time_limit_layout.addWidget(self.time_limit)
        time_limit_layout.addWidget(l)
        checkboxes_layout.addItem(time_limit_layout)
        
        # add all edit and checkbox-items to dialog
        checkboxes.setLayout(checkboxes_layout)
        self.layout.addWidget(checkboxes)
        
        ## Solver and solving options
        # find available solvers
        avail_solvers = []
        if module_exists('cplex'):
            avail_solvers += [CPLEX]
        if module_exists('gurobipy'):
            avail_solvers += [GUROBI]
        if module_exists('swiglpk'):
            avail_solvers += [GLPK]
        if module_exists('pyscipopt'):
            avail_solvers += [SCIP]
            
        solver_and_solution_group = QGroupBox("Solver and solution process")
        solver_and_solution_layout = QHBoxLayout()
        
        solver_buttons_layout = QVBoxLayout()
        self.solver_buttons = {}
        self.solver_buttons["group"] = QButtonGroup()
        # CPLEX
        self.solver_buttons[CPLEX] = QRadioButton("IBM CPLEX")
        if CPLEX not in avail_solvers:
            self.solver_buttons[CPLEX].setEnabled(False)
        solver_buttons_layout.addWidget(self.solver_buttons[CPLEX])
        self.solver_buttons["group"].addButton(self.solver_buttons[CPLEX])
        # Gurobi
        self.solver_buttons[GUROBI] = QRadioButton("Gurobi")
        if GUROBI not in avail_solvers:
            self.solver_buttons[GUROBI].setEnabled(False)
        solver_buttons_layout.addWidget(self.solver_buttons[GUROBI])
        self.solver_buttons["group"].addButton(self.solver_buttons[GUROBI])
        # GLPK
        self.solver_buttons[GLPK] = QRadioButton("GLPK")
        if GLPK not in avail_solvers:
            self.solver_buttons[GLPK].setEnabled(False)
        solver_buttons_layout.addWidget(self.solver_buttons[GLPK])
        self.solver_buttons["group"].addButton(self.solver_buttons[GLPK])
        # SCIP
        self.solver_buttons[SCIP] = QRadioButton("SCIP")
        if SCIP not in avail_solvers:
            self.solver_buttons[SCIP].setEnabled(False)
        solver_buttons_layout.addWidget(self.solver_buttons[SCIP])
        self.solver_buttons["group"].addButton(self.solver_buttons[SCIP])
        self.solver_buttons["group"].buttonClicked.connect(self.configure_solver_options)
        solver_and_solution_layout.addItem(solver_buttons_layout)
        # check best available solver
        if avail_solvers:
            self.solver_buttons[avail_solvers[0]].setChecked(True)
        
        solution_buttons_layout = QVBoxLayout()
        self.solution_buttons = {}
        self.solution_buttons["group"] = QButtonGroup()
        self.solution_buttons["any"] = QRadioButton("any MCS (fast)")
        self.solution_buttons["any"].setChecked(True)
        self.solution_buttons["group"].addButton(self.solution_buttons["any"])
        solution_buttons_layout.addWidget(self.solution_buttons["any"])
        self.solution_buttons["smallest"] = QRadioButton("smallest MCS first")
        self.solution_buttons["group"].addButton(self.solution_buttons["smallest"])
        solution_buttons_layout.addWidget(self.solution_buttons["smallest"])
        self.solution_buttons["cardinality"] = QRadioButton("by cardinality")
        self.solution_buttons["group"].addButton(self.solution_buttons["cardinality"])
        solution_buttons_layout.addWidget(self.solution_buttons["cardinality"])
        solver_and_solution_layout.addItem(solution_buttons_layout)
                
        solver_and_solution_group.setLayout(solver_and_solution_layout)
        self.layout.addWidget(solver_and_solution_group)

        self.configure_solver_options()

        self.advanced = QCheckBox(
            "Advanced: Define knockout/addition costs for genes/reactions")
        self.advanced.setEnabled(False)
        self.layout.addWidget(self.advanced)
        
        
        buttons = QHBoxLayout()
        self.compute_mcs_button = QPushButton("Compute MCS")
        buttons.addWidget(self.compute_mcs_button)
        self.save_button = QPushButton("Save")
        buttons.addWidget(self.save_button)
        self.load_button = QPushButton("Load")
        buttons.addWidget(self.load_button)
        self.cancel_button = QPushButton("Close")
        buttons.addWidget(self.cancel_button)
       
        self.layout.addItem(buttons)

        # 
        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel_button.clicked.connect(self.reject)
        self.save_button.clicked.connect(self.save)
        self.load_button.clicked.connect(self.load)
        self.compute_mcs_button.clicked.connect(self.compute)

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
        if self.solver_buttons[CPLEX].isChecked() or self.solver_buttons[GUROBI].isChecked():
            self.solution_buttons["cardinality"].setEnabled(True)
        else:
            self.solution_buttons["cardinality"].setEnabled(False)
            if self.solution_buttons["cardinality"].isChecked():
                self.solution_buttons["any"].setChecked(True)

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
        pass
    
    def save(self):
        pass
    
    def load(self):
        pass

class ReceiverLineEdit(QLineEdit):
    def __init__(self, mcs_dialog):
        super().__init__()
        self.mcs_dialog = mcs_dialog

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.mcs_dialog.active_receiver = self