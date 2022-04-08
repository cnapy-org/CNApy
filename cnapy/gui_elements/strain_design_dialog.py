"""The dialog for calculating minimal cut sets"""

import io
from mimetypes import guess_all_extensions
import os
import traceback
import scipy
from random import randint
from importlib import find_loader as module_exists
from qtpy.QtWidgets import QAbstractItemView
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
        self.setMinimumWidth(620)

        self.reac_ids = self.appdata.project.cobra_py_model.reactions.list_attr("id")
        
        self.completer = QCompleter(self.reac_ids, self)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        
        if not hasattr(self.appdata.project.cobra_py_model,'genes') or \
            len(self.appdata.project.cobra_py_model.genes) == 0:
                self.completer_ko_ki = self.completer
        else:
            keywords = set( self.appdata.project.cobra_py_model.reactions.list_attr("id")+ \
                            self.appdata.project.cobra_py_model.genes.list_attr("id")+
                            self.appdata.project.cobra_py_model.genes.list_attr("name"))
            if '' in keywords:
                keywords.remove('')
            self.completer_ko_ki = QCompleter(keywords, self)
            self.completer_ko_ki.setCaseSensitivity(Qt.CaseInsensitive)
            
            self.gene_ids = self.appdata.project.cobra_py_model.genes.list_attr("id")
            if set(self.appdata.project.cobra_py_model.genes.list_attr("name")) != set(""):
                self.gene_names = self.appdata.project.cobra_py_model.genes.list_attr("name")
            else:
                self.gene_names = self.gene_ids
                
        
        # Define placeholder strings for text edit fields
        numr = len(self.appdata.project.cobra_py_model.reactions)
        if numr > 2:
            r1 = self.appdata.project.cobra_py_model.reactions[randint(0,numr-1)].id
            r2 = self.appdata.project.cobra_py_model.reactions[randint(0,numr-1)].id
            r3 = self.appdata.project.cobra_py_model.reactions[randint(0,numr-1)].id
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
        self.modules_box = QGroupBox("Strain design module(s)")
        self.modules_box.setMinimumHeight(300)
        
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
        self.module_edit[PROD_ID+"_label"]  = QLabel("Product synth. reac_id")
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
        self.module_edit[MIN_GCP+"_label"] = QLabel("Min. growth-coupling potential")
        self.module_edit[MIN_GCP+"_label"].setHidden(True)
        self.module_edit[MIN_GCP] = ReceiverLineEdit(self)
        self.module_edit[MIN_GCP].setHidden(True)
        self.module_edit[MIN_GCP].setPlaceholderText("(float) e.g.: 1.3")
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
        self.modules_box.setLayout(modules_layout)
        # connect overall module box to editor to the dialog window
        splitter = QSplitter()
        splitter.addWidget(self.modules_box)
        self.layout.addWidget(splitter)
        
        
        # self.layout.addWidget(self.modules_box)
        # refresh modules -> remove in case you want default entries in module constraint list
        self.update_module_edit()
        
        params_layout = QHBoxLayout()
        
        ## Checkboxes for gene-mcs, entries in network map, solvers, kos and kis
        checkboxes = QWidget()
        checkboxes.setObjectName("Checkboxes")
        checkboxes_layout = QVBoxLayout()
        self.gen_kos = QCheckBox(" Gene KOs")
        if not hasattr(self.appdata.project.cobra_py_model,'genes') or \
            len(self.appdata.project.cobra_py_model.genes) == 0:
            self.gen_kos.setEnabled(False)
        self.gen_kos.clicked.connect(self.gen_ko_checked)
        checkboxes_layout.addWidget(self.gen_kos)
        
        self.use_scenario = QCheckBox(
        " Use scenario")
        checkboxes_layout.addWidget(self.use_scenario)
        
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
        checkboxes.setStyleSheet("QWidget#Checkboxes { max-height: 10em };")
        params_layout.addWidget(checkboxes)        
        
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
            
        solver_and_solution_group = QGroupBox("Solver and solution approach")
        solver_and_solution_group.setObjectName("Solver_and_solution")
        solver_and_solution_layout = QHBoxLayout()
        
        solver_buttons_layout = QVBoxLayout()
        self.solver_buttons = {}
        self.solver_buttons["group"] = QButtonGroup()
        # CPLEX
        self.solver_buttons[CPLEX] = QRadioButton("IBM CPLEX")
        self.solver_buttons[CPLEX].setProperty('name',CPLEX)
        if CPLEX not in avail_solvers:
            self.solver_buttons[CPLEX].setEnabled(False)
        solver_buttons_layout.addWidget(self.solver_buttons[CPLEX])
        self.solver_buttons["group"].addButton(self.solver_buttons[CPLEX])
        # Gurobi
        self.solver_buttons[GUROBI] = QRadioButton("Gurobi")
        self.solver_buttons[GUROBI].setProperty('name',GUROBI)
        if GUROBI not in avail_solvers:
            self.solver_buttons[GUROBI].setEnabled(False)
        solver_buttons_layout.addWidget(self.solver_buttons[GUROBI])
        self.solver_buttons["group"].addButton(self.solver_buttons[GUROBI])
        # GLPK
        self.solver_buttons[GLPK] = QRadioButton("GLPK")
        self.solver_buttons[GLPK].setProperty('name',GLPK)
        if GLPK not in avail_solvers:
            self.solver_buttons[GLPK].setEnabled(False)
        solver_buttons_layout.addWidget(self.solver_buttons[GLPK])
        self.solver_buttons["group"].addButton(self.solver_buttons[GLPK])
        # SCIP
        self.solver_buttons[SCIP] = QRadioButton("SCIP")
        self.solver_buttons[SCIP].setProperty('name',SCIP)
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
        self.solution_buttons["any"].setProperty('name',"any")
        self.solution_buttons["any"].setChecked(True)
        self.solution_buttons["group"].addButton(self.solution_buttons["any"])
        solution_buttons_layout.addWidget(self.solution_buttons["any"])
        self.solution_buttons["smallest"] = QRadioButton("smallest MCS first")
        self.solution_buttons["smallest"].setProperty('name',"smallest")
        self.solution_buttons["group"].addButton(self.solution_buttons["smallest"])
        solution_buttons_layout.addWidget(self.solution_buttons["smallest"])
        self.solution_buttons["cardinality"] = QRadioButton("by cardinality")
        self.solution_buttons["cardinality"].setProperty('name',"cardinality")
        self.solution_buttons["group"].addButton(self.solution_buttons["cardinality"])
        solution_buttons_layout.addWidget(self.solution_buttons["cardinality"])
        solver_and_solution_layout.addItem(solution_buttons_layout)
                
        solver_and_solution_group.setLayout(solver_and_solution_layout)
        solver_and_solution_group.setStyleSheet("QGroupBox#Solver_and_solution { max-height: 10em };")
        solver_and_solution_group.setMinimumWidth(300)
        params_layout.addWidget(solver_and_solution_group)

        self.configure_solver_options()
        
        self.layout.addItem(params_layout)

        ## KO and KI costs
        # checkbox
        self.advanced = QCheckBox(
            "Advanced: Define knockout/addition costs for genes/reactions")
        self.layout.addWidget(self.advanced)
        self.advanced.clicked.connect(self.show_ko_ki)
        
        self.ko_ki_box = QGroupBox("Specify knockout and addition candidates")
        print("TO DO: Set KO and KI box to HIDDEN initially..")
        self.ko_ki_box.setHidden(False)
        self.ko_ki_box.setObjectName("ko_ki")
        ko_ki_layout = QVBoxLayout()
        ko_ki_layout.setAlignment(Qt.AlignLeft)
        
        # Filter bar
        ko_ki_filter_layout = QHBoxLayout()
        l = QLabel("Filter: ")
        self.ko_ki_filter = ReceiverLineEdit(self)
        self.ko_ki_filter.setCompleter(self.completer_ko_ki)
        self.ko_ki_filter.textEdited.connect(self.ko_ki_filter_text_changed)
        ko_ki_filter_layout.addWidget(l)
        ko_ki_filter_layout.addWidget(self.ko_ki_filter)
        ko_ki_layout.addItem(ko_ki_filter_layout)
        
        # Tables
        ko_ki_lists_layout = QHBoxLayout()
        
        # reaction list
        reaction_interventions_layout = QVBoxLayout()
        reaction_interventions_layout.setAlignment(Qt.AlignTop)
        self.reaction_itv_list_widget = QWidget()
        self.reaction_itv_list_widget.setFixedWidth(270)
        self.reaction_itv_list = QTableWidget(0, 3)
        self.reaction_itv_list.setEditTriggers(QAbstractItemView.NoEditTriggers);
        self.reaction_itv_list.setFocusPolicy(Qt.NoFocus)
        self.reaction_itv_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.reaction_itv_list.verticalHeader().setDefaultSectionSize(20)
        # self.reaction_itv_list.setStyleSheet("QTableWidget#ko_ki_table::item { padding: 0 0 0 0 px; margin: 0 0 0 0 px }");
        self.reaction_itv_list.setFixedWidth(260)
        self.reaction_itv_list.setMinimumHeight(150)
        self.reaction_itv_list.setHorizontalHeaderLabels(["Reaction","KO N/A KI ","Cost"])
        self.reaction_itv_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.reaction_itv_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.reaction_itv_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.reaction_itv_list.horizontalHeader().resizeSection(0, 100)
        self.reaction_itv_list.horizontalHeader().resizeSection(1, 80)
        self.reaction_itv_list.horizontalHeader().resizeSection(2, 40)
        reaction_interventions_layout.addWidget(self.reaction_itv_list)
        # fill reaction list
        self.reaction_itv = {}
        for i,r in enumerate(self.reac_ids):
            self.reaction_itv_list.insertRow(i)
            l = QLabel(r)
            l.setToolTip(r)
            l.setMaximumWidth(100)
            self.reaction_itv.update({r:\
                                        {'cost': QLineEdit("1.0"),
                                         'button_group': QButtonGroup()}})
            r_ko_ki_button_widget = QWidget()
            r_ko_ki_button_layout = QHBoxLayout()
            r_ko_ki_button_layout.setAlignment(Qt.AlignCenter)
            r_ko_ki_button_layout.setContentsMargins(0,0,0,0)
            r_ko_button = QRadioButton()
            r_na_button = QRadioButton()
            r_ki_button = QRadioButton()
            r_ko_button.setChecked(True)
            self.reaction_itv[r]['button_group'].addButton(r_ko_button,1)
            self.reaction_itv[r]['button_group'].addButton(r_na_button,2)
            self.reaction_itv[r]['button_group'].addButton(r_ki_button,3)
            r_ko_ki_button_layout.addWidget(r_ko_button)
            r_ko_ki_button_layout.addWidget(r_na_button)
            r_ko_ki_button_layout.addWidget(r_ki_button)
            r_ko_ki_button_widget.setLayout(r_ko_ki_button_layout)
            self.reaction_itv_list.setCellWidget(i, 0, l)
            self.reaction_itv_list.setCellWidget(i, 1, r_ko_ki_button_widget)
            self.reaction_itv_list.setCellWidget(i, 2, self.reaction_itv[r]['cost'])
            self.reaction_itv[r]['button_group'].buttonClicked.connect(\
                            lambda state, x=r: self.knock_changed(x,'reac'))
        # buttons
        self.deactivate_ex = QPushButton("Exchange reactions notknockable")
        self.deactivate_ex.clicked.connect(self.set_deactivate_ex)
        reaction_interventions_layout.addWidget(self.deactivate_ex)
        self.all_koable = QPushButton("All knockable")
        self.all_koable.clicked.connect(self.set_all_r_koable)
        reaction_interventions_layout.addWidget(self.all_koable)
        self.none_koable = QPushButton("All notknockable")
        self.none_koable.clicked.connect(self.set_none_r_koable)
        reaction_interventions_layout.addWidget(self.none_koable)
        self.reaction_itv_list_widget.setLayout(reaction_interventions_layout)
        ko_ki_lists_layout.addWidget(self.reaction_itv_list_widget)
        
        # gene list
        gene_interventions_layout = QVBoxLayout()
        gene_interventions_layout.setAlignment(Qt.AlignTop)
        self.gene_itv_list_widget = QWidget()
        self.gene_itv_list_widget.setHidden(True)
        self.gene_itv_list_widget.setFixedWidth(270)
        self.gene_itv_list = QTableWidget(0, 3)
        self.gene_itv_list.setEditTriggers(QAbstractItemView.NoEditTriggers);
        self.gene_itv_list.setFocusPolicy(Qt.NoFocus)
        self.gene_itv_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.gene_itv_list.verticalHeader().setDefaultSectionSize(20)
        self.gene_itv_list.setFixedWidth(260)
        self.gene_itv_list.setMinimumHeight(150)
        self.gene_itv_list.setHorizontalHeaderLabels(["Gene","KO N/A KI ","Cost"])
        self.gene_itv_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.gene_itv_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.gene_itv_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.gene_itv_list.horizontalHeader().resizeSection(0, 90)
        self.gene_itv_list.horizontalHeader().resizeSection(1, 80)
        self.gene_itv_list.horizontalHeader().resizeSection(2, 40)
        gene_interventions_layout.addWidget(self.gene_itv_list)
        # fill gene list
        self.gene_itv = {}
        for i,g in enumerate(self.gene_ids):
            self.gene_itv_list.insertRow(i)
            l = QLabel(self.gene_names[i])
            l.setToolTip(g)
            l.setMaximumWidth(80)
            self.gene_itv.update({g:\
                                        {'cost': QLineEdit("1.0"),
                                         'button_group': QButtonGroup()}})
            g_ko_ki_button_widget = QWidget()
            g_ko_ki_button_layout = QHBoxLayout()
            g_ko_ki_button_layout.setAlignment(Qt.AlignCenter)
            g_ko_ki_button_layout.setContentsMargins(0,0,0,0)
            g_ko_button = QRadioButton()
            g_na_button = QRadioButton()
            g_ki_button = QRadioButton()
            g_ko_button.setChecked(True)
            self.gene_itv[g]['button_group'].addButton(g_ko_button,1)
            self.gene_itv[g]['button_group'].addButton(g_na_button,2)
            self.gene_itv[g]['button_group'].addButton(g_ki_button,3)
            g_ko_ki_button_layout.addWidget(g_ko_button)
            g_ko_ki_button_layout.addWidget(g_na_button)
            g_ko_ki_button_layout.addWidget(g_ki_button)
            g_ko_ki_button_widget.setLayout(g_ko_ki_button_layout)
            self.gene_itv_list.setCellWidget(i, 0, l)
            self.gene_itv_list.setCellWidget(i, 1, g_ko_ki_button_widget)
            self.gene_itv_list.setCellWidget(i, 2, self.gene_itv[g]['cost'])
            self.gene_itv[g]['button_group'].buttonClicked.connect(\
                            lambda state, x=g: self.knock_changed(x,'gene'))
        # buttons
        self.all_koable = QPushButton("All knockable")
        self.all_koable.clicked.connect(self.set_all_g_koable)
        gene_interventions_layout.addWidget(self.all_koable)
        self.none_koable = QPushButton("All notknockable")
        self.none_koable.clicked.connect(self.set_none_g_koable)
        gene_interventions_layout.addWidget(self.none_koable)
        self.gene_itv_list_widget.setLayout(gene_interventions_layout)
        ko_ki_lists_layout.addWidget(self.gene_itv_list_widget)
        
        ko_ki_layout.addItem(ko_ki_lists_layout)
        self.ko_ki_box.setLayout(ko_ki_layout)
        self.layout.addWidget(self.ko_ki_box)
                
        splitter.addWidget(self.ko_ki_box)
        
        ## main buttons
        buttons_layout = QHBoxLayout()
        self.compute_mcs_button = QPushButton("Compute MCS")
        self.compute_mcs_button.clicked.connect(self.compute)
        buttons_layout.addWidget(self.compute_mcs_button)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save)
        buttons_layout.addWidget(self.save_button)
        self.load_button = QPushButton("Load")
        self.load_button.clicked.connect(self.load)
        buttons_layout.addWidget(self.load_button)
        self.cancel_button = QPushButton("Close")
        self.cancel_button.clicked.connect(self.reject)
        buttons_layout.addWidget(self.cancel_button)
        self.layout.addItem(buttons_layout)

        # Finalize
        self.setLayout(self.layout)
        # Connecting the signal
        self.central_widget.broadcastReactionID.connect(self.receive_input)

    @Slot(str)
    def receive_input(self, text):
        completer_mode = self.active_receiver.completer().completionMode()
        # temporarily disable completer popup
        self.active_receiver.completer().setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
        self.active_receiver.insert(text)
        self.active_receiver.completer().setCompletionMode(completer_mode)

    def configure_solver_options(self):  # called when switching solver
        if self.solver_buttons['group'].checkedButton().property('name') in [CPLEX, GUROBI]:
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
        if valid and module:
            self.modules[current_module] = module
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#8bff87"))
        elif not valid:
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#ff726b"))
        return valid
    
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
        if not self.modules:
            return True, None
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
                if self.use_scenario.isChecked():  # integrate scenario into model bounds
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
    
    def gen_ko_checked(self):
        if self.gen_kos.isChecked():
            self.gene_itv_list_widget.setHidden(False)
            self.set_all_g_koable()
        else:
            self.gene_itv_list_widget.setHidden(True)
            self.set_all_r_koable()
        
    def show_ko_ki(self):
        if self.advanced.isChecked():
            self.ko_ki_box.setHidden(False)
        else:
            self.ko_ki_box.setHidden(True)
        self.adjustSize()
    
    def ko_ki_filter_text_changed(self):
        txt = self.ko_ki_filter.text().lower()
        hide_reacs = [True if txt not in r.lower() else False for r in self.reac_ids]
        for i,h in enumerate(hide_reacs):
            self.reaction_itv_list.setRowHidden(i,h)
        hide_genes = [True if txt not in g.lower() and txt not in n.lower() else False \
                        for g,n in zip(self.gene_ids,self.gene_names)]
        for i,h in enumerate(hide_genes):
            self.gene_itv_list.setRowHidden(i,h)
    
    def knock_changed(self,id,gene_or_reac):
        if gene_or_reac == 'reac':
            genes = [g.id for g in self.appdata.project.cobra_py_model.reactions.get_by_id(id).genes]
            r = self.reaction_itv[id]
            checked = r['button_group'].checkedId()
            if checked in [1,3]:
                r['cost'].setText('1.0')
                r['cost'].setEnabled(True)
                r['button_group'].button(1).setEnabled(True)
                r['button_group'].button(3).setEnabled(True)
                for g in [self.gene_itv[s] for s in genes]:
                    g['cost'].setText('')
                    g['cost'].setEnabled(False)
                    g['button_group'].button(1).setDisabled(True)
                    g['button_group'].button(2).setChecked(True)
                    g['button_group'].button(3).setDisabled(True)
            else:
                r['cost'].setText('')
                r['cost'].setDisabled(True)
                for g in [self.gene_itv[s] for s in genes]:
                    g['button_group'].button(1).setEnabled(True)
                    g['button_group'].button(3).setEnabled(True)
        elif gene_or_reac == 'gene':
            reacs = [r.id for r in self.appdata.project.cobra_py_model.genes.get_by_id(id).reactions]
            g = self.gene_itv[id]
            checked = g['button_group'].checkedId()
            g['button_group'].button(1).setEnabled(True)
            g['button_group'].button(3).setEnabled(True)
            if checked in [1,3]:
                g['cost'].setText('1.0')
                g['cost'].setEnabled(True)
                for r in [self.reaction_itv[s] for s in reacs]:
                    r['cost'].setText('')
                    r['cost'].setEnabled(False)
                    r['button_group'].button(1).setDisabled(True)
                    r['button_group'].button(2).setChecked(True)
                    r['button_group'].button(3).setDisabled(True)
            else:
                g['cost'].setText('')
                g['cost'].setDisabled(True)
                for r in [self.reaction_itv[s] for s in reacs]:
                    r['button_group'].button(1).setEnabled(True)
                    r['button_group'].button(3).setEnabled(True)
    
    def set_deactivate_ex(self):
        ex_reacs = [r.id for r in self.appdata.project.cobra_py_model.reactions \
                        if not r.products or not r.reactants]
        for r in ex_reacs:
            self.reaction_itv[r]['button_group'].button(2).setChecked(True)
            self.knock_changed(r,'reac')
    
    def set_all_r_koable(self):
        for r in self.appdata.project.cobra_py_model.reactions.list_attr("id"):
            self.reaction_itv[r]['button_group'].button(1).setChecked(True)
            self.knock_changed(r,'reac')
    
    def set_none_r_koable(self):
        for r in self.appdata.project.cobra_py_model.reactions.list_attr("id"):
            self.reaction_itv[r]['button_group'].button(2).setChecked(True)
            self.knock_changed(r,'reac')
    
    def set_all_g_koable(self):
        for r in self.appdata.project.cobra_py_model.genes.list_attr("id"):
            self.gene_itv[r]['button_group'].button(1).setChecked(True)
            self.knock_changed(r,'gene')

    def set_none_g_koable(self):
        for r in self.appdata.project.cobra_py_model.genes.list_attr("id"):
            self.gene_itv[r]['button_group'].button(2).setChecked(True)
            self.knock_changed(r,'gene')
            
    def parse_inputs(self):
        sd_setup = {} # strain design setup
        sd_setup.update({'model_id' : self.appdata.project.cobra_py_model.id})
        # Save modules. Therefore, first remove cobra model from all modules. It is reinserted afterwards
        [m.pop('model') for m in self.modules]
        sd_setup.update({'modules' : self.modules.copy()})
        [m.update({'model':self.appdata.project.cobra_py_model}) for m in self.modules]
        # other parameters
        sd_setup.update({'gene_kos' : self.gen_kos.isChecked()})
        sd_setup.update({'use_scenario' : self.use_scenario.isChecked()})
        sd_setup.update({'max_sols' : self.max_sols.text()})
        sd_setup.update({'max_size' : self.max_size.text()})
        sd_setup.update({'time_limit' : self.time_limit.text()})
        sd_setup.update({'advanced' : self.advanced.isChecked()})
        sd_setup.update({'solver' : \
            self.solver_buttons['group'].checkedButton().property('name')})
        sd_setup.update({'search_type' : \
            self.solution_buttons["group"].checkedButton().property('name')})
        # only save knockouts and knockins if advanced is selected
        if sd_setup['advanced']:
            koCost = {}
            kiCost = {}
            for r in self.reac_ids:
                but_id = self.reaction_itv[r]['button_group'].checkedId()
                if but_id == 1:
                    koCost.update({r:float(self.reaction_itv[r]['cost'].text())})
                elif but_id == 3:
                    kiCost.update({r:float(self.reaction_itv[r]['cost'].text())})
            sd_setup.update({'koCost' : koCost})
            sd_setup.update({'kiCost' : kiCost})
            # if gene-kos is selected, also save these
            if sd_setup['gene_kos']:
                gkoCost = {}
                gkiCost = {}
                for i,g in enumerate(self.gene_ids):
                    but_id = self.gene_itv[g]['button_group'].checkedId()
                    if but_id == 1:
                        gkoCost.update({self.gene_names[i]:float(self.gene_itv[g]['cost'].text())})
                    elif but_id == 3:
                        gkiCost.update({self.gene_names[i]:float(self.gene_itv[g]['cost'].text())})
                sd_setup.update({'gkoCost' : gkoCost})
                sd_setup.update({'gkiCost' : gkiCost})
        return sd_setup
                
    
    def compute(self):
        valid = self.module_apply()
        if not valid:
            return
        sd_setup = self.parse_inputs()
    
    def save(self):
        valid = self.module_apply()
        if not valid:
            return
        sd_setup = self.parse_inputs()
    
    def load(self):
        pass

class ReceiverLineEdit(QLineEdit):
    def __init__(self, mcs_dialog):
        super().__init__()
        self.mcs_dialog = mcs_dialog

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.mcs_dialog.active_receiver = self