"""The dialog for calculating minimal cut sets"""

from contextlib import redirect_stdout, redirect_stderr
import io
import json
import os
from typing import Dict
import pickle
import traceback
import numpy as np
from straindesign import SDModule, lineqlist2str, linexprdict2str, compute_strain_designs, \
                                    linexpr2dict, select_solver
from straindesign.names import *
from straindesign.strainDesignSolutions import SDSolutions
from random import randint
from qtpy.QtCore import Qt, Slot, Signal, QThread
from qtpy.QtWidgets import (QButtonGroup, QCheckBox, QComboBox, QCompleter,
                            QDialog, QGroupBox, QHBoxLayout, QHeaderView, QAbstractButton,
                            QLabel, QLineEdit, QMessageBox, QPushButton, QApplication,
                            QRadioButton, QTableWidget, QVBoxLayout, QSplitter,
                            QWidget, QFileDialog, QTextEdit, QLayout, QScrollArea)
import optlang_enumerator.mcs_computation as mcs_computation
import cobra
from cobra.util.solver import interface_to_str
from cnapy.appdata import AppData
from cnapy.gui_elements.solver_buttons import get_solver_buttons
from cnapy.utils import QTableCopyable, QComplReceivLineEdit, QTableItem, show_unknown_error_box
from cnapy.core_gui import get_last_exception_string, has_community_error_substring, except_likely_community_model_error
import logging

PROTECT_STR = 'Protect (MCS)'
SUPPRESS_STR = 'Suppress (MCS)'
OPTKNOCK_STR = 'OptKnock'
ROBUSTKNOCK_STR = 'RobustKnock'
OPTCOUPLE_STR = 'OptCouple'
NESTED_OPT = 'Nested_Optimization'
MODULE_TYPES = [PROTECT_STR, SUPPRESS_STR, OPTKNOCK_STR, ROBUSTKNOCK_STR, OPTCOUPLE_STR]

def BORDER_COLOR(HEX): # string that defines style sheet for changing the color of the module-box
    return "QGroupBox#EditModule "+\
                "{ border: 1px solid "+HEX+";"+\
                "  padding: 12 5 0 0 em ;"+\
                "  margin: 0 0 0 0 em};"

def BACKGROUND_COLOR(HEX,id): # string that defines style sheet for changing the color of the module-box
    return "QLineEdit#"+id+" "+\
                "{ background: "+HEX+"};"

def FONT_COLOR(HEX): # string that defines style sheet for changing the color of the module-box
    return "QLabel { color: "+HEX+"};"

class SDDialog(QDialog):
    """A dialog to perform strain design computations"""

    def __init__(self, appdata: AppData, sd_setup: Dict = {}):
        QDialog.__init__(self)
        self.setWindowTitle("Strain Design Computation")

        self.appdata = appdata
        self.out = io.StringIO()
        self.err = io.StringIO()
        self.setMinimumWidth(620)
        # screen_geometry = QApplication.desktop().screen().geometry()
        # self.setMaximumWidth(screen_geometry.width()-10)
        # self.setMaximumHeight(screen_geometry.height()-50)

        self.reac_ids = appdata.project.reaction_ids.id_list
        self.reac_wordlist = self.reac_ids

        if not hasattr(self.appdata.project.cobra_py_model,'genes') or \
                len(self.appdata.project.cobra_py_model.genes) == 0:
            self.gene_wordlist = self.reac_wordlist
            self.gene_ids = []
            self.gene_names = []
        else:
            self.gene_wordlist = set(   self.appdata.project.cobra_py_model.reactions.list_attr("id")+ \
                                        self.appdata.project.cobra_py_model.genes.list_attr("id")+
                                        self.appdata.project.cobra_py_model.genes.list_attr("name"))
            if '' in self.gene_wordlist:
                self.gene_wordlist.remove('')

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
        self.current_module = 0
        self.scrollArea = QScrollArea()
        self.layout = QVBoxLayout()
        # self.layout.setAlignment(Qt.Alignment(Qt.AlignTop^Qt.AlignLeft))
        self.layout.setSizeConstraint(QLayout.SetFixedSize)
        self.layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        self.modules_box = QGroupBox("Strain design module(s)")

        # layout for modules list and buttons
        modules_layout = QHBoxLayout()
        self.module_list = QTableWidget(0, 2)
        module_add_rem_buttons = QVBoxLayout()
        modules_layout.addWidget(self.module_list)
        modules_layout.addItem(module_add_rem_buttons)

        # modules list
        self.module_list.setFixedWidth(195)
        self.module_list.setMinimumHeight(40)
        self.module_list.setHorizontalHeaderLabels(["Module Type",""])
        # self.module_list.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        # self.module_list.verticalHeader().setVisible(False)
        self.module_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.module_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.module_list.horizontalHeader().resizeSection(0, 115)
        self.module_list.horizontalHeader().resizeSection(1, 60)
        # -> first entry in module list
        # self.modules = [None]
        # combo = QComboBox(self.module_list)
        # combo.insertItems(0,MODULE_TYPES)
        # combo.currentTextChanged.connect(self.sel_module_type)
        # self.module_list.setCellWidget(0, 0, combo)
        # module_edit_button = QPushButton("Edit...")
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
        self.module_edit[NESTED_OPT] = QCheckBox(" At optimum of an (inner) objective funciton")
        self.module_edit[NESTED_OPT].setChecked(False)
        self.module_edit[NESTED_OPT].clicked.connect(self.nested_opt_checked)
        module_spec_layout.addWidget(self.module_edit[NESTED_OPT])

        # Outer objective
        self.module_edit[OUTER_OBJECTIVE+"_label"] = QLabel("Outer objective (maximized)")
        self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(True)
        self.module_edit[OUTER_OBJECTIVE] = QComplReceivLineEdit(self, self.appdata.project.reaction_ids)
        self.module_edit[OUTER_OBJECTIVE].setPlaceholderText(placeholder_expr)
        self.module_edit[OUTER_OBJECTIVE].setHidden(True)
        self.module_edit[OUTER_OBJECTIVE].textCorrect.connect(self.update_global_objective)
        module_spec_layout.addWidget(self.module_edit[OUTER_OBJECTIVE+"_label"] )
        module_spec_layout.addWidget(self.module_edit[OUTER_OBJECTIVE])

        # Inner objective
        self.module_edit[INNER_OBJECTIVE+"_label"] = QLabel("Inner objective (maximized)")
        self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(True)
        self.module_edit[INNER_OBJECTIVE] = QComplReceivLineEdit(self, self.appdata.project.reaction_ids)
        self.module_edit[INNER_OBJECTIVE].setPlaceholderText(placeholder_expr)
        self.module_edit[INNER_OBJECTIVE].setHidden(True)
        self.module_edit[INNER_OBJECTIVE].textCorrect.connect(self.update_global_objective)
        module_spec_layout.addWidget(self.module_edit[INNER_OBJECTIVE+"_label"])
        module_spec_layout.addWidget(self.module_edit[INNER_OBJECTIVE])

        optcouple_layout = QHBoxLayout()
        # Product ID
        optcouple_layout_prod = QVBoxLayout()
        self.module_edit[PROD_ID+"_label"]  = QLabel("Product synth. reac_id")
        self.module_edit[PROD_ID+"_label"].setHidden(True)
        self.module_edit[PROD_ID] = QComplReceivLineEdit(self, self.appdata.project.reaction_ids)
        self.module_edit[PROD_ID].setPlaceholderText(placeholder_rid)
        self.module_edit[PROD_ID].setHidden(True)
        self.module_edit[PROD_ID].textCorrect.connect(self.update_global_objective)
        optcouple_layout_prod.addWidget(self.module_edit[PROD_ID+"_label"])
        optcouple_layout_prod.addWidget(self.module_edit[PROD_ID])
        optcouple_layout.addItem(optcouple_layout_prod)
        #
        # minimal growth coupling potential
        optcouple_layout_mingcp = QVBoxLayout()
        self.module_edit[MIN_GCP+"_label"] = QLabel("Min. growth-coupling potential")
        self.module_edit[MIN_GCP+"_label"].setHidden(True)
        self.module_edit[MIN_GCP] = QLineEdit(self)
        self.module_edit[MIN_GCP].setHidden(True)
        self.module_edit[MIN_GCP].setPlaceholderText("optional: (float) e.g.: 0.2")
        optcouple_layout_mingcp.addWidget(self.module_edit[MIN_GCP+"_label"])
        optcouple_layout_mingcp.addWidget(self.module_edit[MIN_GCP])
        optcouple_layout.addItem(optcouple_layout_mingcp)
        module_spec_layout.addItem(optcouple_layout)

        # module constraints
        self.module_edit[CONSTRAINTS+"_label"] = QLabel("Constraints")
        module_spec_layout.addWidget(self.module_edit[CONSTRAINTS+"_label"])
        constr_list_layout = QHBoxLayout()
        constr_list_layout.setAlignment(Qt.Alignment(Qt.AlignTop^Qt.AlignLeft))
        module_spec_layout.addItem(constr_list_layout)

        # layout for constraint list and buttons
        self.module_edit[CONSTRAINTS] = QTableWidget(0, 1)
        self.module_edit[CONSTRAINTS].setMaximumHeight(80)
        self.module_edit[CONSTRAINTS].setMinimumHeight(40)
        self.module_edit[CONSTRAINTS].verticalHeader().setDefaultSectionSize(18)
        self.module_edit[CONSTRAINTS].verticalHeader().setVisible(False)
        self.module_edit[CONSTRAINTS].horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.module_edit[CONSTRAINTS].horizontalHeader().setVisible(False)
        # -> first entry in constraint list
        # constr_entry = ComplReceivLineEdit(self,self.reac_wordlist)
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
        self.module_edit["module_apply_button"] = QPushButton("Check module")
        self.module_edit["module_apply_button"].clicked.connect(self.module_apply)
        self.module_edit["module_del_button"] = QPushButton("Delete module")
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
        self.global_objective = QLabel("Please add strain design module(s)...")
        self.global_objective.setProperty("prefix", "Current global objective: ")
        self.global_objective.setWordWrap(True)
        self.global_objective.setMaximumHeight(40)
        self.layout.addWidget(self.global_objective)

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

        max_solutions_layout = QHBoxLayout()
        l = QLabel(" Max. Solutions")
        self.max_solutions = QLineEdit("3")
        self.max_solutions.setMaximumWidth(50)
        max_solutions_layout.addWidget(self.max_solutions)
        max_solutions_layout.addWidget(l)
        checkboxes_layout.addItem(max_solutions_layout)

        max_cost_layout = QHBoxLayout()
        l = QLabel(" Max. Σ intervention costs")
        self.max_cost = QLineEdit("7")
        self.max_cost.setMaximumWidth(50)
        max_cost_layout.addWidget(self.max_cost)
        max_cost_layout.addWidget(l)
        checkboxes_layout.addItem(max_cost_layout)

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
        solver_and_solution_group = QGroupBox("Solver and solution approach")
        solver_and_solution_group.setObjectName("Solver_and_solution")
        solver_and_solution_layout = QHBoxLayout()

        solver_buttons_layout, self.solver_buttons = get_solver_buttons(appdata)
        self.set_optlang_solver_text()
        solver_and_solution_layout.addItem(solver_buttons_layout)

        solution_buttons_layout = QVBoxLayout()
        self.solution_buttons = {}
        self.solution_buttons["group"] = QButtonGroup()
        self.solution_buttons[ANY] = QRadioButton("any solution(s) (fast)")
        self.solution_buttons[ANY].setProperty('name',ANY)
        self.solution_buttons["group"].addButton(self.solution_buttons[ANY])
        solution_buttons_layout.addWidget(self.solution_buttons[ANY])
        self.solution_buttons[BEST] = QRadioButton("best solution(s) first")
        self.solution_buttons[BEST].setProperty('name',BEST)
        self.solution_buttons[BEST].setChecked(True)
        self.solution_buttons["group"].addButton(self.solution_buttons[BEST])
        solution_buttons_layout.addWidget(self.solution_buttons[BEST])
        self.solution_buttons[POPULATE] = QRadioButton("populate")
        self.solution_buttons[POPULATE].setProperty('name',POPULATE)
        self.solution_buttons["group"].addButton(self.solution_buttons[POPULATE])
        solution_buttons_layout.addWidget(self.solution_buttons[POPULATE])
        self.solution_buttons['CONT_SEARCH'] = QRadioButton("continuous search")
        self.solution_buttons['CONT_SEARCH'].setProperty('name','CONT_SEARCH')
        self.solution_buttons["group"].addButton(self.solution_buttons['CONT_SEARCH'])
        solution_buttons_layout.addWidget(self.solution_buttons['CONT_SEARCH'])
        solver_and_solution_layout.addItem(solution_buttons_layout)

        solver_and_solution_group.setLayout(solver_and_solution_layout)
        solver_and_solution_group.setStyleSheet("QGroupBox#Solver_and_solution { max-height: 10em };")
        solver_and_solution_group.setMinimumWidth(300)
        params_layout.addWidget(solver_and_solution_group)

        self.configure_solver_options(self.solver_buttons['group'].checkedButton())
        self.solver_buttons["group"].buttonClicked.connect(self.configure_solver_options)

        self.layout.addItem(params_layout)

        ## KO and KI costs
        # checkbox
        self.advanced = QCheckBox(
            "Advanced: Take into account costs for genes/reactions knockout/addition and for regulatory interventions")
        self.layout.addWidget(self.advanced)
        self.advanced.clicked.connect(self.show_ko_ki)

        self.advanced_layout = QHBoxLayout()

        # layout for regulatory constraint list and buttons
        self.regulatory_box = QGroupBox("Regulatory interventions")
        self.regulatory_box.setHidden(True)
        self.regulatory_box.setObjectName("reg")

        self.regulatory_layout = QVBoxLayout()
        self.regulatory_layout.setAlignment(Qt.AlignLeft)
        # self.regulatory_itv_list_label = QLabel("")
        # self.regulatory_layout.addWidget(self.regulatory_itv_list_label)

        self.regulatory_layout_table = QHBoxLayout()
        self.regulatory_itv_list = QTableWidget(0, 2)
        self.regulatory_itv_list.verticalHeader().setDefaultSectionSize(18)
        self.regulatory_itv_list.verticalHeader().setVisible(False)
        # self.regulatory_itv_list.horizontalHeader().setVisible(False)
        self.regulatory_itv_list.setHorizontalHeaderLabels(["Regulatory constraint","Cost"])
        self.regulatory_itv_list.setMinimumWidth(110)
        self.regulatory_itv_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.regulatory_itv_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.regulatory_itv_list.horizontalHeader().resizeSection(0, 50)
        self.regulatory_itv_list.horizontalHeader().resizeSection(1, 40)
        # # -> first entry in constraint list
        # # regul_entry = ComplReceivLineEdit(self,self.reac_wordlist)
        # # regul_entry.setPlaceholderText(self.placeholder_eq)
        # # self.regulatory_itv_list.setCellWidget(0, 0, regul_entry)
        # # self.regulatory_itv_list.setItem(0, 1, QTableItem())
        # # self.active_receiver = regul_entry
        self.regulatory_layout_table.addWidget(self.regulatory_itv_list)

        # buttons to add and remove regulatory constraints
        reg_add_rem_buttons = QVBoxLayout()
        self.add_reg_constr = QPushButton("+")
        self.add_reg_constr.clicked.connect(self.add_reg)
        self.add_reg_constr.setMaximumWidth(20)
        self.rem_reg_constr = QPushButton("-")
        self.rem_reg_constr.clicked.connect(self.rem_reg)
        self.rem_reg_constr.setMaximumWidth(20)
        reg_add_rem_buttons.addWidget(self.add_reg_constr)
        reg_add_rem_buttons.addWidget(self.rem_reg_constr)
        reg_add_rem_buttons.addStretch()

        self.regulatory_layout_table.addItem(reg_add_rem_buttons)
        self.regulatory_layout.addItem(self.regulatory_layout_table)
        self.regulatory_box.setLayout(self.regulatory_layout)
        self.advanced_layout.addWidget(self.regulatory_box)

        self.ko_ki_box = QGroupBox("Specify knockout and addition candidates")
        self.ko_ki_box.setHidden(True)
        self.ko_ki_box.setObjectName("ko_ki")
        ko_ki_layout = QVBoxLayout()
        ko_ki_layout.setAlignment(Qt.AlignLeft)

        # ko_ki_lists_layout.addWidget(self.reaction_itv_list_widget)

        # Filter bar
        ko_ki_filter_layout = QHBoxLayout()
        l = QLabel("Filter: ")
        self.ko_ki_filter = QComplReceivLineEdit(self,self.gene_wordlist,check=False)
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
        self.reaction_itv_list = QTableCopyable(0, 3)
        self.reaction_itv_list.verticalHeader().setDefaultSectionSize(18)
        self.reaction_itv_list.verticalHeader().setVisible(False)
        # self.reaction_itv_list.setStyleSheet("QTableWidget#ko_ki_table::item { padding: 0 0 0 0 px; margin: 0 0 0 0 px }");
        self.reaction_itv_list.setFixedWidth(220)
        self.reaction_itv_list.setMinimumHeight(35)
        self.reaction_itv_list.setMaximumHeight(150)
        self.reaction_itv_list.setHorizontalHeaderLabels(["Reaction","KO N/A KI ","Cost"])
        self.reaction_itv_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.reaction_itv_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.reaction_itv_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.reaction_itv_list.horizontalHeader().resizeSection(0, 80)
        self.reaction_itv_list.horizontalHeader().resizeSection(1, 80)
        self.reaction_itv_list.horizontalHeader().resizeSection(2, 40)
        reaction_interventions_layout.addWidget(self.reaction_itv_list)
        # fill reaction list
        self.reaction_itv = {}
        for i,r in enumerate(self.reac_ids):
            self.reaction_itv_list.insertRow(i)
            l = QTableItem(r)
            l.setToolTip(r)
            l.setEditable(False)
            # l.setMaximumWidth(100)
            self.reaction_itv.update({r:{'cost': QTableItem("1.0"),
                                         'button_group': QButtonGroup()}})
            self.reaction_itv[r]['cost'].setEditable(True)
            r_ko_ki_button_widget = QWidget()
            r_ko_ki_button_layout = QHBoxLayout()
            r_ko_ki_button_layout.setAlignment(Qt.AlignCenter)
            r_ko_ki_button_layout.setContentsMargins(0,0,0,0)
            r_ko_button = QRadioButton()
            r_na_button = QRadioButton()
            r_ki_button = QRadioButton()
            r_ko_button.setChecked(True)
            r_ko_ki_button_widget.setFocusPolicy(Qt.NoFocus)
            # self.reaction_itv_list.setEditTriggers(QAbstractItemView.NoEditTriggers);
            # self.reaction_itv_list.setFocusPolicy(Qt.NoFocus)
            # self.reaction_itv_list.setSelectionMode(QAbstractItemView.NoSelection)
            self.reaction_itv[r]['button_group'].addButton(r_ko_button,1)
            self.reaction_itv[r]['button_group'].addButton(r_na_button,2)
            self.reaction_itv[r]['button_group'].addButton(r_ki_button,3)
            r_ko_ki_button_layout.addWidget(r_ko_button)
            r_ko_ki_button_layout.addWidget(r_na_button)
            r_ko_ki_button_layout.addWidget(r_ki_button)
            r_ko_ki_button_widget.setLayout(r_ko_ki_button_layout)
            self.reaction_itv_list.setItem(i, 0, l)
            dummy_item = QTableItem()
            dummy_item.setEnabled(False)
            dummy_item.setSelectable(False)
            self.reaction_itv_list.setItem(i, 1, dummy_item)
            self.reaction_itv_list.setCellWidget(i, 1, r_ko_ki_button_widget)
            self.reaction_itv_list.setItem(i, 2, self.reaction_itv[r]['cost'])
            self.reaction_itv[r]['button_group'].buttonClicked.connect(\
                            lambda state, x=r: self.knock_changed(x,'reac'))
        # buttons
        self.deactivate_ex = QPushButton("Exchange reactions non-targetable")
        self.deactivate_ex.clicked.connect(self.set_deactivate_ex)
        reaction_interventions_layout.addWidget(self.deactivate_ex)
        self.all_koable = QPushButton("All targetable")
        self.all_koable.clicked.connect(self.set_all_r_koable)
        reaction_interventions_layout.addWidget(self.all_koable)
        self.none_koable = QPushButton("All non-targetable")
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
        self.gene_itv_list = QTableCopyable(0, 3)
        # self.gene_itv_list.setEditTriggers(QAbstractItemView.NoEditTriggers);
        # self.gene_itv_list.setFocusPolicy(Qt.NoFocus)
        # self.gene_itv_list.setSelectionMode(QAbstractItemView.NoSelection)
        self.gene_itv_list.verticalHeader().setDefaultSectionSize(18)
        self.gene_itv_list.verticalHeader().setVisible(False)
        self.gene_itv_list.setFixedWidth(220)
        self.gene_itv_list.setMinimumHeight(50)
        self.gene_itv_list.setHorizontalHeaderLabels(["Gene","KO N/A KI ","Cost"])
        self.gene_itv_list.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
        self.gene_itv_list.horizontalHeader().setSectionResizeMode(1, QHeaderView.Fixed)
        self.gene_itv_list.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.gene_itv_list.horizontalHeader().resizeSection(0, 80)
        self.gene_itv_list.horizontalHeader().resizeSection(1, 80)
        self.gene_itv_list.horizontalHeader().resizeSection(2, 40)
        gene_interventions_layout.addWidget(self.gene_itv_list)
        # fill gene list
        self.gene_itv = {}
        for i,g in enumerate(self.gene_ids):
            self.gene_itv_list.insertRow(i)
            if self.gene_names[i] != '':
                l = QTableItem(self.gene_names[i])
                l.setToolTip(g)
            else:
                l = QTableItem(g)
            l.setEditable(False)
            # l.setMaximumWidth(80)
            self.gene_itv.update({g:\
                                        {'cost': QTableItem("1.0"),
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
            self.gene_itv_list.setItem(i, 0, l)
            dummy_item = QTableItem()
            dummy_item.setEnabled(False)
            dummy_item.setSelectable(False)
            self.gene_itv_list.setItem(i, 1, dummy_item)
            self.gene_itv_list.setCellWidget(i, 1, g_ko_ki_button_widget)
            self.gene_itv_list.setItem(i, 2, self.gene_itv[g]['cost'])
            self.gene_itv[g]['button_group'].buttonClicked.connect(\
                            lambda state, x=g: self.knock_changed(x,'gene'))
        # buttons
        self.all_koable = QPushButton("All targetable")
        self.all_koable.clicked.connect(self.set_all_g_koable)
        gene_interventions_layout.addWidget(self.all_koable)
        self.none_koable = QPushButton("All non-targetable")
        self.none_koable.clicked.connect(self.set_none_g_koable)
        gene_interventions_layout.addWidget(self.none_koable)
        self.gene_itv_list_widget.setLayout(gene_interventions_layout)
        ko_ki_lists_layout.addWidget(self.gene_itv_list_widget)

        ko_ki_layout.addItem(ko_ki_lists_layout)
        self.ko_ki_box.setLayout(ko_ki_layout)

        self.advanced_layout.addWidget(self.ko_ki_box)
        self.layout.addItem(self.advanced_layout)

        splitter.addWidget(self.ko_ki_box)

        ## main buttons
        buttons_layout = QHBoxLayout()
        self.compute_sd_button = QPushButton("Compute")
        self.compute_sd_button.clicked.connect(self.compute)
        buttons_layout.addWidget(self.compute_sd_button)
        self.save_button = QPushButton("Save")
        self.save_button.clicked.connect(self.save)
        buttons_layout.addWidget(self.save_button)
        self.load_button = QPushButton("Load")
        self.load_button.clicked.connect(self.load)
        buttons_layout.addWidget(self.load_button)
        self.cancel_button = QPushButton("Close")
        self.cancel_button.clicked.connect(self.cancel)
        buttons_layout.addWidget(self.cancel_button)
        self.layout.addItem(buttons_layout)

        # Finalize
        self.setLayout(self.layout)
        self.layout.setSizeConstraint(QLayout.SetFixedSize)
        self.adjustSize()
        self.layout.setSizeConstraint(QLayout.SetMinAndMaxSize)
        # Connecting signals
        try:
            self.appdata.window.centralWidget().broadcastReactionID.connect(self.receive_input)
            self.launch_computation_signal.connect(self.appdata.window.compute_strain_design,Qt.QueuedConnection)
        except:
            print('Signals to main window could not be connected.')

        # load strain design setup if passed to constructor
        if sd_setup != {} and sd_setup != False:
            self.load(sd_setup)

    @Slot(str)
    def receive_input(self, text):
        if hasattr(self,'active_receiver') and hasattr(self.active_receiver,'completer'):
            completer_mode = self.active_receiver.completer.completionMode()
            # temporarily disable completer popup
            self.active_receiver.completer.setCompletionMode(QCompleter.CompletionMode.InlineCompletion)
            self.active_receiver.insert(text+' ')
            self.active_receiver.completer.setCompletionMode(completer_mode)

    @Slot()
    def set_optlang_solver_text(self):
        solver_interface = self.appdata.project.cobra_py_model.problem
        self.optlang_solver_name = interface_to_str(solver_interface)
        self.solver_buttons['OPTLANG'].setText(f"optlang_enumerator ({interface_to_str(solver_interface)})")

    @Slot(QAbstractButton)
    def configure_solver_options(self, button: QAbstractButton):  # called when switching solver
        selected_solver = button.property('name')
        if selected_solver == 'OPTLANG':
            if self.optlang_solver_name != 'cplex' and self.optlang_solver_name != 'gurobi':
                if self.solution_buttons[POPULATE].isChecked() or self.solution_buttons['CONT_SEARCH'].isChecked():
                    self.solution_buttons[ANY].setChecked(True)
                self.solution_buttons[POPULATE].setEnabled(False)
                self.solution_buttons['CONT_SEARCH'].setEnabled(False)
            else:
                self.solution_buttons[POPULATE].setEnabled(True)
                self.solution_buttons['CONT_SEARCH'].setEnabled(True)
        else:
            if self.solution_buttons['CONT_SEARCH'].isChecked():
                self.solution_buttons['CONT_SEARCH'].setChecked(False)
                self.solution_buttons[ANY].setChecked(True)
            self.solution_buttons['CONT_SEARCH'].setEnabled(False)
            if selected_solver in [CPLEX, GUROBI]:
                self.solution_buttons[POPULATE].setEnabled(True)
            else:
                self.solution_buttons[POPULATE].setEnabled(False)
                if self.solution_buttons[POPULATE].isChecked():
                    self.solution_buttons[ANY].setChecked(True)

    def add_module(self):
        i = self.module_list.rowCount()
        self.module_list.insertRow(i)

        combo = QComboBox(self.module_list)
        combo.insertItems(0,MODULE_TYPES)
        combo.currentTextChanged.connect(self.sel_module_type)
        self.module_list.setCellWidget(i, 0, combo)
        module_edit_button = QPushButton("Edit...")
        module_edit_button.clicked.connect(self.edit_module)
        module_edit_button.setMaximumWidth(60)
        self.module_list.setCellWidget(i, 1, module_edit_button)
        self.modules.append(None)
        if i == 0:
            self.current_module = i
            self.update_module_edit()
        self.update_global_objective()

    def rem_module(self,*args):
        if self.module_list.rowCount() == 0:
            self.modules = []
            self.current_module = -1
            return
        if args:
            i = self.current_module
        if self.module_list.selectedIndexes():
            i = self.module_list.selectedIndexes()[0].row()
        else:
            i = self.module_list.rowCount()-1
        self.module_list.removeRow(i)
        self.modules.pop(i)
        if i == self.current_module:
            last_module = self.module_list.rowCount()-1
            self.current_module = last_module
            self.update_module_edit()
        elif i < self.current_module:
            self.current_module -=1
            self.update_module_edit()
        self.update_global_objective()

    def edit_module(self):
        # if current module is valid, load the module that was newly selected
        valid, module = self.verify_module(self.current_module)
        if valid:
            self.modules[self.current_module] = module
        else:
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#de332a"))
            return
        selected_module = self.module_list.selectedIndexes()[0].row()
        self.current_module = selected_module
        self.update_module_edit()

    def sel_module_type(self):
        i = self.module_list.selectedIndexes()[0].row()
        self.modules[i] = None
        self.update_global_objective()
        if i == self.current_module:
            self.update_module_edit()

    def add_constr(self):
        i = self.module_edit[CONSTRAINTS].rowCount()
        self.module_edit[CONSTRAINTS].insertRow(i)
        constr_entry = QComplReceivLineEdit(self, self.appdata.project.reaction_ids, check=True, is_constr=True)
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

    def add_reg(self):
        i = self.regulatory_itv_list.rowCount()
        self.regulatory_itv_list.insertRow(i)
        reg_entry = QComplReceivLineEdit(self,self.gene_wordlist,check=True,is_constr=True)
        reg_entry.setPlaceholderText(self.placeholder_eq)
        self.active_receiver = reg_entry
        self.regulatory_itv_list.setCellWidget(i, 0, reg_entry)
        self.regulatory_itv_list.setItem(i, 1, QTableItem('1.0'))

    def rem_reg(self):
        if self.regulatory_itv_list.rowCount() == 0:
            return
        if self.regulatory_itv_list.selectedIndexes():
            i = self.regulatory_itv_list.selectedIndexes()[0].row()
        else:
            i = self.regulatory_itv_list.rowCount()-1
        self.regulatory_itv_list.removeRow(i)

    def module_apply(self):
        valid, module = self.verify_module(self.current_module)
        if valid and module:
            self.modules[self.current_module] = module
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#59a861"))
        elif not valid:
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#de332a"))
        self.update_global_objective()
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
            self.module_edit[NESTED_OPT].setHidden(	                True)
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
        module_type = self.module_list.cellWidget(self.current_module,0).currentText()
        self.module_spec_box.setTitle('Module '+str(self.current_module+1)+' specifications ('+module_type+')')
        if not self.modules[self.current_module]:
            self.module_edit[INNER_OBJECTIVE].setText("")
            self.module_edit[INNER_OBJECTIVE].check_text(True)
            self.module_edit[OUTER_OBJECTIVE].setText("")
            self.module_edit[OUTER_OBJECTIVE].check_text(True)
            self.module_edit[PROD_ID].setText("")
            self.module_edit[PROD_ID].check_text(True)
            self.module_edit[MIN_GCP].setText("")
            for _ in range(self.module_edit[CONSTRAINTS].rowCount()):
                self.module_edit[CONSTRAINTS].removeRow(0)
            # uncomment this to add an empty constraint by default
            # self.module_edit[CONSTRAINTS].insertRow(0)
            # constr_entry = ComplReceivLineEdit(self,self.reac_wordlist)
            # self.active_receiver = constr_entry
            # self.module_edit[CONSTRAINTS].setCellWidget(0, 0, constr_entry)
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#b0b0b0"))
        else:
            self.module_spec_box.setStyleSheet(BORDER_COLOR("#59a861"))
            mod = {}
            mod[CONSTRAINTS]     = self.modules[self.current_module][CONSTRAINTS]
            mod[INNER_OBJECTIVE] = self.modules[self.current_module][INNER_OBJECTIVE]
            mod[OUTER_OBJECTIVE] = self.modules[self.current_module][OUTER_OBJECTIVE]
            mod[PROD_ID]         = self.modules[self.current_module][PROD_ID]
            mod[MIN_GCP]         = self.modules[self.current_module][MIN_GCP]

            # remove all former constraints and refill again from module
            for _ in range(self.module_edit[CONSTRAINTS].rowCount()):
                self.module_edit[CONSTRAINTS].removeRow(0)
            constr_entry = [None for _ in range(len(mod[CONSTRAINTS]))]
            for i,c in enumerate(mod[CONSTRAINTS]):
                text = lineqlist2str(c)
                self.module_edit[CONSTRAINTS].insertRow(i)
                constr_entry[i] = QComplReceivLineEdit(self, self.appdata.project.reaction_ids, check=True, is_constr=True)
                constr_entry[i].setText(text+' ')
                constr_entry[i].check_text(True)
                constr_entry[i].setPlaceholderText(self.placeholder_eq)
                self.module_edit[CONSTRAINTS].setCellWidget(i, 0, constr_entry[i])
            # load other information from module
            if mod[INNER_OBJECTIVE] and module_type in [PROTECT_STR,SUPPRESS_STR]:
                self.module_edit[NESTED_OPT].setChecked(True)
            else:
                self.module_edit[NESTED_OPT].setChecked(False)
            if mod[INNER_OBJECTIVE]:
                self.module_edit[INNER_OBJECTIVE].setText(\
                    linexprdict2str(mod[INNER_OBJECTIVE])+' ')     # add space character to avoid
                self.module_edit[INNER_OBJECTIVE].check_text(True) # word completion
            if mod[OUTER_OBJECTIVE]:
                self.module_edit[OUTER_OBJECTIVE].setText(\
                    linexprdict2str(mod[OUTER_OBJECTIVE])+' ')
                self.module_edit[OUTER_OBJECTIVE].check_text(True)
            if mod[PROD_ID]:
                self.module_edit[PROD_ID].setText(\
                    linexprdict2str(mod[PROD_ID])+' ')
                self.module_edit[PROD_ID].check_text(True)
            if mod[MIN_GCP]:
                self.module_edit[MIN_GCP].setText(str(mod[MIN_GCP]))

        if module_type == PROTECT_STR:
            self.module_edit[NESTED_OPT].setHidden(	                False)
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[INNER_OBJECTIVE].setHidden(			False)
            self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(	True)
            self.module_edit[OUTER_OBJECTIVE].setHidden( 			True)
            self.module_edit[PROD_ID+"_label"].setHidden( 			True)
            self.module_edit[PROD_ID].setHidden( 					True)
            self.module_edit[MIN_GCP+"_label"].setHidden( 			True)
            self.module_edit[MIN_GCP].setHidden( 					True)
            self.nested_opt_checked()
        elif module_type == SUPPRESS_STR:
            self.module_edit[NESTED_OPT].setHidden(	                False)
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[INNER_OBJECTIVE].setHidden(			False)
            self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(	True)
            self.module_edit[OUTER_OBJECTIVE].setHidden( 			True)
            self.module_edit[PROD_ID+"_label"].setHidden( 			True)
            self.module_edit[PROD_ID].setHidden( 					True)
            self.module_edit[MIN_GCP+"_label"].setHidden( 			True)
            self.module_edit[MIN_GCP].setHidden( 					True)
            self.nested_opt_checked()
        elif module_type == OPTKNOCK_STR:
            self.module_edit[NESTED_OPT].setChecked(                False)
            self.module_edit[NESTED_OPT].setHidden(	                True)
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[INNER_OBJECTIVE].setHidden(			False)
            self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[OUTER_OBJECTIVE].setHidden( 			False)
            self.module_edit[PROD_ID+"_label"].setHidden( 			True)
            self.module_edit[PROD_ID].setHidden( 					True)
            self.module_edit[MIN_GCP+"_label"].setHidden( 			True)
            self.module_edit[MIN_GCP].setHidden( 					True)
        elif module_type == ROBUSTKNOCK_STR:
            self.module_edit[NESTED_OPT].setChecked(                False)
            self.module_edit[NESTED_OPT].setHidden(	                True)
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[INNER_OBJECTIVE].setHidden(			False)
            self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[OUTER_OBJECTIVE].setHidden( 			False)
            self.module_edit[PROD_ID+"_label"].setHidden( 			True)
            self.module_edit[PROD_ID].setHidden( 					True)
            self.module_edit[MIN_GCP+"_label"].setHidden( 			True)
            self.module_edit[MIN_GCP].setHidden( 					True)
        elif module_type == OPTCOUPLE_STR:
            self.module_edit[NESTED_OPT].setChecked(                False)
            self.module_edit[NESTED_OPT].setHidden(	                True)
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[INNER_OBJECTIVE].setHidden(			False)
            self.module_edit[OUTER_OBJECTIVE+"_label"].setHidden(	True)
            self.module_edit[OUTER_OBJECTIVE].setHidden( 			True)
            self.module_edit[PROD_ID+"_label"].setHidden( 			False)
            self.module_edit[PROD_ID].setHidden( 					False)
            self.module_edit[MIN_GCP+"_label"].setHidden( 			False)
            self.module_edit[MIN_GCP].setHidden( 					False)
        self.update_global_objective()

    def verify_module(self,*args):
        self.setCursor(Qt.BusyCursor)
        if not self.modules:
            return True, None
        module_no = args[0]
        module_type = self.module_list.cellWidget(module_no,0).currentText()
        # retrieve module infos from gui
        constraints = [self.module_edit[CONSTRAINTS].cellWidget(i,0).text() \
                            for i in range(self.module_edit[CONSTRAINTS].rowCount())]
        inner_objective = self.module_edit[INNER_OBJECTIVE].text()
        outer_objective = self.module_edit[OUTER_OBJECTIVE].text()
        prod_id = self.module_edit[PROD_ID].text()
        min_gcp = self.module_edit[MIN_GCP].text()
        if module_type in [PROTECT_STR,SUPPRESS_STR] and (not self.module_edit[NESTED_OPT].isChecked() \
                                                    or not self.module_edit[INNER_OBJECTIVE]):
            inner_objective = None
        if min_gcp:
            min_gcp = float(min_gcp)
        else:
            min_gcp = 0.0
        # adapt model
        try:
            with self.appdata.project.cobra_py_model as model:
                if self.use_scenario.isChecked():  # integrate scenario into model bounds
                    self.appdata.project.load_scenario_into_model(model)
                if module_type == PROTECT_STR:
                    module = SDModule(model,module_type=PROTECT, inner_objective=inner_objective,\
                                        inner_opt_sense=MAXIMIZE, constraints=constraints)
                elif module_type == SUPPRESS_STR:
                    module = SDModule(model,module_type=SUPPRESS, inner_objective=inner_objective,\
                                        inner_opt_sense=MAXIMIZE, constraints=constraints)
                elif module_type == OPTKNOCK_STR:
                    module = SDModule(model,module_type=OPTKNOCK, inner_objective=inner_objective,\
                                        inner_opt_sense=MAXIMIZE, outer_objective=outer_objective,\
                                        outer_opt_sense=MAXIMIZE, constraints=constraints)
                elif module_type == ROBUSTKNOCK_STR:
                    module = SDModule(model,module_type=ROBUSTKNOCK, inner_objective=inner_objective,\
                                        inner_opt_sense=MAXIMIZE, outer_objective=outer_objective,\
                                        outer_opt_sense=MAXIMIZE, constraints=constraints)
                elif module_type == OPTCOUPLE_STR:
                    module = SDModule(model,module_type=OPTCOUPLE, inner_objective=inner_objective,\
                                        inner_opt_sense=MAXIMIZE, prod_id=prod_id,\
                                        min_gcp=min_gcp, constraints=constraints)
            self.setCursor(Qt.ArrowCursor)
            return True, module
        except Exception as e:
            QMessageBox.warning(self,"Module invalid",\
                "The current module is either infeasible or "+\
                "syntactic errors persist in the module's specificaiton. \n\n"+\
                "Exception details: \n\n"+str(e))
            self.setCursor(Qt.ArrowCursor)
            return False, None

    @Slot(bool)
    def update_global_objective(self,b=True):
        modules = []
        for i in range(self.module_list.rowCount()):
            modules.append(self.module_list.cellWidget(i,0).currentText())
        if not modules:
            self.global_objective.setStyleSheet(FONT_COLOR('#000000'))
            self.global_objective.setText("Please add strain design module(s)...")
        elif all([m in [PROTECT_STR, SUPPRESS_STR] for m in modules]):
            self.global_objective.setStyleSheet(FONT_COLOR('#59a861'))
            self.global_objective.setText(self.global_objective.property('prefix')+\
                "Minimization of intervention costs (Minimal Cut Set computation)")
        elif sum([1 for m in modules if m in [OPTKNOCK_STR,ROBUSTKNOCK_STR,OPTCOUPLE_STR]]) > 1:
            confl_modules = [(i+1,m) for i,m in enumerate(modules) if m in [OPTKNOCK_STR,ROBUSTKNOCK_STR,OPTCOUPLE_STR]]
            self.global_objective.setStyleSheet(FONT_COLOR('#de332a'))
            self.global_objective.setText("Conflicting modules: "+\
                ", ".join([str(m[0])+" ("+m[1]+")" for m in confl_modules]))
        elif sum([1 for m in modules if m in [OPTKNOCK_STR,ROBUSTKNOCK_STR,OPTCOUPLE_STR]]) == 1:
            main_module = [(self.modules[i],i,m) for i,m in enumerate(modules) if m in [OPTKNOCK_STR,ROBUSTKNOCK_STR,OPTCOUPLE_STR]][0]
            if main_module[0] is not None and main_module[2] != OPTCOUPLE_STR:
                objective = linexprdict2str(main_module[0][OUTER_OBJECTIVE])
                if objective:
                    self.global_objective.setText(self.global_objective.property('prefix')+\
                        "maximize {"+objective+"} (module "+str(main_module[1]+1)+": "+main_module[2]+")")
                    self.global_objective.setStyleSheet(FONT_COLOR('#59a861'))
                    return
            if main_module[0] is not None and main_module[2] == OPTCOUPLE_STR:
                objective = linexprdict2str(main_module[0][INNER_OBJECTIVE])
                prod_id = linexprdict2str(main_module[0][PROD_ID])
                if objective and prod_id:
                    self.global_objective.setText(self.global_objective.property('prefix')+\
                        "maximize coupling potential for "+prod_id+", s.t.: max{"+objective+\
                        "} (module "+str(main_module[1]+1)+": "+main_module[2]+")")
                    self.global_objective.setStyleSheet(FONT_COLOR('#59a861'))
                    return
            if main_module[1] == self.current_module:
                try:
                    if main_module[2] == OPTCOUPLE_STR:
                        objective = linexprdict2str(linexpr2dict(self.module_edit[INNER_OBJECTIVE].text(), self.reac_wordlist))
                        prod_id = linexprdict2str(linexpr2dict(self.module_edit[PROD_ID].text(), self.reac_wordlist))
                        if objective and prod_id:
                            self.global_objective.setText(self.global_objective.property('prefix')+\
                                "maximize coupling potential for "+prod_id+" s.t.: max{"+objective+\
                                "} (module "+str(main_module[1]+1)+": "+main_module[2]+")")
                            self.global_objective.setStyleSheet(FONT_COLOR('#59a861'))
                            return
                        else:
                            raise Exception()
                    else:
                        objective = linexprdict2str(linexpr2dict(self.module_edit[OUTER_OBJECTIVE].text(), self.reac_wordlist))
                        if objective:
                            self.global_objective.setText(self.global_objective.property('prefix')+"maximize {"+\
                            objective+"} (module "+str(main_module[1]+1)+": "+main_module[2]+")")
                            self.global_objective.setStyleSheet(FONT_COLOR('#59a861'))
                            return
                        else:
                            raise Exception()
                except:
                    self.global_objective.setStyleSheet(FONT_COLOR('#000000'))
                    self.global_objective.setText("Editing module ... (module "+#
                                                    str(main_module[1]+1)+": "+main_module[2]+")")
                    return
            self.global_objective.setStyleSheet(FONT_COLOR('#de332a'))
            self.global_objective.setText(self.global_objective.property('prefix')+\
                "Global/Outer objective invalid or missing (module "+str(main_module[1]+1)+": "+main_module[2]+")")


    def nested_opt_checked(self):
        if self.module_edit[NESTED_OPT].isChecked():
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	False)
            self.module_edit[INNER_OBJECTIVE].setHidden(			False)
        else:
            self.module_edit[INNER_OBJECTIVE+"_label"].setHidden(	True)
            self.module_edit[INNER_OBJECTIVE].setHidden(			True)

    def gen_ko_checked(self):
        if self.gen_kos.isChecked():
            self.gene_itv_list_widget.setHidden(False)
            self.set_none_r_koable()
            self.set_all_g_koable()
        else:
            self.gene_itv_list_widget.setHidden(True)
            self.set_all_r_koable()

    def show_ko_ki(self):
        if self.advanced.isChecked():
            self.regulatory_box.setHidden(False)
            self.ko_ki_box.setHidden(False)
        else:
            self.regulatory_box.setHidden(True)
            self.ko_ki_box.setHidden(True)
        self.layout.setSizeConstraint(QLayout.SetFixedSize)
        self.adjustSize()
        self.layout.setSizeConstraint(QLayout.SetMinAndMaxSize)

    def ko_ki_filter_text_changed(self):
        self.setCursor(Qt.BusyCursor)
        txt = self.ko_ki_filter.text().lower().strip()
        hide_reacs = [True if txt not in r.lower() else False for r in self.reac_ids]
        for i,h in enumerate(hide_reacs):
            self.reaction_itv_list.setRowHidden(i,h)
        hide_genes = [True if txt not in g.lower() and txt not in n.lower() else False \
                        for g,n in zip(self.gene_ids,self.gene_names)]
        for i,h in enumerate(hide_genes):
            self.gene_itv_list.setRowHidden(i,h)
        self.setCursor(Qt.ArrowCursor)

    def knock_changed(self,id,gene_or_reac):
        if gene_or_reac == 'reac':
            if id in self.appdata.project.cobra_py_model.reactions:
                genes = [g.id for g in self.appdata.project.cobra_py_model.reactions.get_by_id(id).genes]
            else: # in case it is a scenario reaction
                genes = []
            r = self.reaction_itv[id]
            checked = r['button_group'].checkedId()
            if checked in [1,3]:
                if not r['cost'].text():
                    r['cost'].setText('1.0')
                r['cost'].setEnabled(True)
                r['button_group'].button(1).setEnabled(True)
                r['button_group'].button(3).setEnabled(True)
                for g in [self.gene_itv[s] for s in genes]:
                    g['cost'].setText('')
                    g['cost'].setEnabled(False)
                    g['button_group'].button(1).setEnabled(False)
                    g['button_group'].button(2).setChecked(True)
                    g['button_group'].button(3).setEnabled(False)
            else:
                r['cost'].setText('')
                r['cost'].setEnabled(False)
                for g,gid in zip([self.gene_itv[s] for s in genes],genes):
                    # reactivate only if all genes of this reaction have been deactivated
                    reacs = [t.id for t in self.appdata.project.cobra_py_model.genes.get_by_id(gid).reactions]
                    if all([self.reaction_itv[k]['button_group'].button(2).isChecked() for k in reacs]):
                        g['button_group'].button(1).setEnabled(True)
                        g['button_group'].button(3).setEnabled(True)
        elif gene_or_reac == 'gene':
            reacs = [r.id for r in self.appdata.project.cobra_py_model.genes.get_by_id(id).reactions]
            g = self.gene_itv[id]
            checked = g['button_group'].checkedId()
            g['button_group'].button(1).setEnabled(True)
            g['button_group'].button(3).setEnabled(True)
            if checked in [1,3]:
                if not g['cost'].text():
                    g['cost'].setText('1.0')
                g['cost'].setEnabled(True)
                for r in [self.reaction_itv[s] for s in reacs]:
                    r['cost'].setText('')
                    r['cost'].setEnabled(False)
                    r['button_group'].button(1).setEnabled(False)
                    r['button_group'].button(2).setChecked(True)
                    r['button_group'].button(3).setEnabled(False)
            else:
                g['cost'].setText('')
                g['cost'].setEnabled(False)
                for r,rid in zip([self.reaction_itv[s] for s in reacs],reacs):
                    # reactivate only if all genes of this reaction have been deactivated
                    genes = [t.id for t in self.appdata.project.cobra_py_model.reactions.get_by_id(rid).genes]
                    if all([self.gene_itv[k]['button_group'].button(2).isChecked() for k in genes]):
                        r['button_group'].button(1).setEnabled(True)
                        r['button_group'].button(3).setEnabled(True)

    def set_deactivate_ex(self):
        with self.appdata.project.cobra_py_model as model:
            if self.use_scenario.isChecked():  # integrate scenario into model bounds
                    self.appdata.project.load_scenario_into_model(model)
            ex_reacs = [r.id for r in model.reactions if not r.products or not r.reactants]
            for r in ex_reacs:
                self.reaction_itv[r]['button_group'].button(2).setChecked(True)
                self.knock_changed(r,'reac')

    def set_all_r_koable(self):
        with self.appdata.project.cobra_py_model as model:
            if self.use_scenario.isChecked():  # integrate scenario into model bounds
                    self.appdata.project.load_scenario_into_model(model)
            for r in model.reactions.list_attr("id"):
                self.reaction_itv[r]['button_group'].button(1).setChecked(True)
                self.knock_changed(r,'reac')

    def set_none_r_koable(self):
        with self.appdata.project.cobra_py_model as model:
            if self.use_scenario.isChecked():  # integrate scenario into model bounds
                    self.appdata.project.load_scenario_into_model(model)
            for r in model.reactions.list_attr("id"):
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

    def parse_dialog_inputs(self):
        self.setCursor(Qt.BusyCursor)
        sd_setup = {} # strain design setup
        sd_setup.update({MODEL_ID : self.appdata.project.cobra_py_model.id})
        # Save modules. Therefore, first remove cobra model from all modules. It is reinserted afterwards
        modules = [m.copy() for m in self.modules] # "deep" copy necessary
        [m.pop(MODEL_ID) for m in modules if MODEL_ID in m]
        sd_setup.update({MODULES : modules})
        # other parameters
        sd_setup.update({'gene_kos' : self.gen_kos.isChecked()})
        sd_setup.update({'use_scenario' : self.use_scenario.isChecked()})
        sd_setup.update({MAX_SOLUTIONS : self.max_solutions.text()})
        sd_setup.update({MAX_COST : self.max_cost.text()})
        sd_setup.update({TIME_LIMIT : self.time_limit.text()})
        sd_setup.update({'advanced' : self.advanced.isChecked()})
        sd_setup.update({SOLVER : \
            self.solver_buttons['group'].checkedButton().property('name')})
        sd_setup.update({SOLUTION_APPROACH : \
            self.solution_buttons["group"].checkedButton().property('name')})
        # only save knockouts and knockins if advanced is selected
        if sd_setup['advanced']:
            koCost = {}
            kiCost = {}
            regCost = {self.regulatory_itv_list.cellWidget(i,0).text(): \
                        float(self.regulatory_itv_list.item(i,1).text()) \
                        for i in range(self.regulatory_itv_list.rowCount())}
            sd_setup.update({REGCOST : regCost})
            for r in self.reac_ids:
                but_id = self.reaction_itv[r]['button_group'].checkedId()
                if but_id == 1:
                    koCost.update({r:float(self.reaction_itv[r]['cost'].text())})
                elif but_id == 3:
                    kiCost.update({r:float(self.reaction_itv[r]['cost'].text())})
            sd_setup.update({KOCOST : koCost})
            sd_setup.update({KICOST : kiCost})
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
                sd_setup.update({GKOCOST : gkoCost})
                sd_setup.update({GKICOST : gkiCost})
        self.setCursor(Qt.ArrowCursor)
        return sd_setup

    def save(self):
        # if current module is invalid, abort
        self.setCursor(Qt.BusyCursor)
        valid = self.module_apply()
        if not valid:
            return
        self.setCursor(Qt.ArrowCursor)
        # open file dialog
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            directory=self.appdata.work_directory, filter="*.sdc")[0]
        if not filename or len(filename) == 0:
            return
        elif len(filename)<=4 or filename[-4:] != '.sdc':
            filename += '.sdc'
        # readout strain design setup from dialog
        sd_setup = self.parse_dialog_inputs()
        # dump dictionary into json-file
        with open(filename, 'w') as fp:
            json.dump(sd_setup, fp)

    def load(self, sd_setup = {}):
        if sd_setup == {} or sd_setup == False:
            # open file dialog
            dialog = QFileDialog(self)
            filename: str = dialog.getOpenFileName(
                directory=self.appdata.last_scen_directory, filter="*.sdc")[0]
            if not filename or len(filename) == 0 or not os.path.exists(filename):
                return
            # dump dictionary into json-file
            with open(filename, 'r') as fp:
                try:
                    sd_setup = json.load(fp)
                except json.decoder.JSONDecodeError:
                    QMessageBox.critical(
                        self,
                        'Could not open file',
                        "File could not be opened as it does not seem to be a valid StrainDesign setup. "
                        "Maybe the file got the .sdc ending for other reasons than being a StrainDesign setup or the file is corrupted."
                    )
                    return
        elif type(sd_setup) == str:
            sd_setup = json.loads(sd_setup)
        # warn if strain design setup was constructed for another model
        if sd_setup[MODEL_ID] != self.appdata.project.cobra_py_model.id:
            QMessageBox.information(self,"Model IDs not matching",
                "The strain design setup was specified for a different model. "+\
                "Errors might occur due to non-matching reaction or gene-identifiers.")
        # write back content to dialog
        for m in self.modules[::-1]:
            self.rem_module()
        self.modules = []
        for m in sd_setup[MODULES]:
            self.add_module()
        self.module_list.selectRow(len(self.modules)-1)
        for i,m in enumerate(sd_setup[MODULES]):
            if m[MODULE_TYPE] == PROTECT:
                self.module_list.cellWidget(i, 0).setCurrentText(PROTECT_STR)
            elif m[MODULE_TYPE] == SUPPRESS:
                self.module_list.cellWidget(i, 0).setCurrentText(SUPPRESS_STR)
            elif m[MODULE_TYPE] == OPTKNOCK:
                self.module_list.cellWidget(i, 0).setCurrentText(OPTKNOCK_STR)
            elif m[MODULE_TYPE] == ROBUSTKNOCK:
                self.module_list.cellWidget(i, 0).setCurrentText(ROBUSTKNOCK_STR)
            elif m[MODULE_TYPE] == OPTCOUPLE:
                self.module_list.cellWidget(i, 0).setCurrentText(OPTCOUPLE_STR)
        [m.update({MODEL_ID:self.appdata.project.cobra_py_model.id}) for m in sd_setup[MODULES]]
        self.modules = sd_setup[MODULES]
        self.current_module = len(self.modules)-1
        self.update_module_edit()
        # update checkboxes
        self.gen_kos.setChecked(sd_setup['gene_kos'])
        self.use_scenario.setChecked(sd_setup['use_scenario'])
        self.max_solutions.setText(sd_setup[MAX_SOLUTIONS])
        self.max_cost.setText(sd_setup[MAX_COST])
        self.time_limit.setText(sd_setup[TIME_LIMIT])
        self.advanced.setChecked(sd_setup['advanced'])
        if sd_setup[SOLVER] == 'OPTLANG':
            solver = 'OPTLANG'
        else:
            solver = select_solver(sd_setup[SOLVER],self.appdata.project.cobra_py_model)
        self.solver_buttons[solver].setChecked(True)
        self.solution_buttons[sd_setup[SOLUTION_APPROACH]].setChecked(True)
        self.configure_solver_options(self.solver_buttons[solver])
        # only load knockouts and knockins if advanced is selected
        self.gen_ko_checked()
        self.show_ko_ki()
        # remove all former regulatory constraints and refill again
        for _ in range(self.regulatory_itv_list.rowCount()):
            self.regulatory_itv_list.removeRow(0)
        if sd_setup['advanced']:
            self.set_none_r_koable()
            if REGCOST in sd_setup:
                reg_entry = [None for _ in range(len(sd_setup[REGCOST]))]
                for i, (k, v) in enumerate(sd_setup[REGCOST].items()):
                    self.regulatory_itv_list.insertRow(i)
                    reg_entry[i] = QComplReceivLineEdit(self,self.gene_wordlist,check=True,is_constr=True)
                    reg_entry[i].setText(k+' ')
                    reg_entry[i].check_text(True)
                    reg_entry[i].setPlaceholderText(self.placeholder_eq)
                    self.regulatory_itv_list.setCellWidget(i, 0, reg_entry[i])
                    self.regulatory_itv_list.setItem(i, 1, QTableItem(str(v)))
            if KOCOST in sd_setup:
                for r,v in sd_setup[KOCOST].items():
                    self.reaction_itv[r]['button_group'].button(1).setChecked(True)
                    self.reaction_itv[r]['cost'].setText(str(v))
                    self.knock_changed(r,'reac')
            if KICOST in sd_setup:
                for r,v in sd_setup[KICOST].items():
                    self.reaction_itv[r]['button_group'].button(3).setChecked(True)
                    self.reaction_itv[r]['cost'].setText(str(v))
                    self.knock_changed(r,'reac')
            # if gene-kos is selected, also load these
            if sd_setup['gene_kos']:
                self.set_none_g_koable()
                if GKOCOST in sd_setup:
                    for k,v in sd_setup[GKOCOST].items():
                        if k not in self.gene_ids:
                            g = self.gene_ids[self.gene_names.index(k)]
                        else:
                            g=k
                        self.gene_itv[g]['button_group'].button(1).setChecked(True)
                        self.gene_itv[g]['cost'].setText(str(v))
                        self.knock_changed(g,'gene')
                if GKICOST in sd_setup:
                    for k,v in sd_setup[GKICOST].items():
                        if k not in self.gene_ids:
                                g = self.gene_ids[self.gene_names.index(k)]
                        else:
                            g=k
                        self.gene_itv[g]['button_group'].button(3).setChecked(True)
                        self.gene_itv[g]['cost'].setText(str(v))
                        self.knock_changed(g,'gene')
        self.compute_sd_button.setFocus()

    def compute(self):
        QApplication.setOverrideCursor(Qt.BusyCursor)
        QApplication.processEvents()
        valid = self.module_apply()
        if not valid:
            return
        if not self.modules:
            QMessageBox.information(self,"Please add modules",
                                    "At least one module must be added to the "+\
                                    "strain design problem.")
            return
        if any([True for m in self.modules if m is None]):
            QMessageBox.information(self,"Please complete module setup",
                                    "Some modules were added to the strain design problem "+\
                                    "but not yet set up. Please use the Edit button(s) in the " +\
                                    "module list to ensure all modules were set up correctly.")
            self.current_module = [i for i,m in enumerate(self.modules) if m is None][0]
            self.module_edit()
            return
        bilvl_modules = [i for i,m in enumerate(self.modules) \
                            if m[MODULE_TYPE] in [OPTKNOCK,ROBUSTKNOCK,OPTCOUPLE]]
        sd_setup = self.parse_dialog_inputs()

        if self.solver_buttons['OPTLANG'].isChecked():
            if len(bilvl_modules) > 0:
                QMessageBox.information(self, "Bilevel modules not supported",
                                        "Module types 'OptKnock', " +\
                                        "'RobustKnock' and 'OptCouple' are not supported " +\
                                        "by optlang_enumerator.\nChoose one of the StrainDesign solvers instead.")
                return
            if sd_setup['gene_kos']:
                QMessageBox.information(self, "Gene knock-outs not supported",
                                        "optlang_enumerator only calculates reaction " +\
                                        "knock-outs.\nChoose one of the StrainDesign solvers instead.")
                return
            if len(sd_setup.get(REGCOST, [])) > 0:
                if QMessageBox.information(self, "Regulatory interventions not supported",
                                        "optlang_enumerator does not support regulatory " +\
                                        "interventions.\nAll regulatory interventions will be ignored.",
                                        QMessageBox.Ok | QMessageBox.Cancel) == QMessageBox.Cancel:
                    return
            if any(m[INNER_OBJECTIVE] is not None for m in sd_setup[MODULES]):
                if QMessageBox.information(self, "Inner objectives not supported",
                                        "optlang_enumerator does not support inner objectives.\n" +\
                                        "All inner objectives will be ignored.",
                                        QMessageBox.Ok | QMessageBox.Cancel) == QMessageBox.Cancel:
                    return

            close_sd_dialog = self.compute_optlang(sd_setup)
        else:
            if len(bilvl_modules) > 1:
                QMessageBox.information(self, "Conflicting Modules",
                                        "Only one of the module types 'OptKnock', " +\
                                        "'RobustKnock' and 'OptCouple' can be defined per " +\
                                        "strain design setup.")
                self.current_module = bilvl_modules[0]
                self.module_edit()
                return
            self.launch_computation_signal.emit(json.dumps(sd_setup))
            close_sd_dialog = True

        QApplication.restoreOverrideCursor()
        if close_sd_dialog:
            self.appdata.window.sd_dialog = None
            self.deleteLater()
            self.accept()

    def compute_optlang(self, sd_setup) -> bool:
        max_mcs_num = float(sd_setup[MAX_SOLUTIONS])
        max_mcs_size = int(sd_setup[MAX_COST])
        timeout = float(sd_setup[TIME_LIMIT])
        if timeout == float('inf'):
            timeout = None

        if sd_setup[SOLUTION_APPROACH] == BEST:
            enum_method = 1
        elif sd_setup[SOLUTION_APPROACH] == POPULATE:
            enum_method = 2
        elif sd_setup[SOLUTION_APPROACH] == 'CONT_SEARCH':
            enum_method = 4
        else: # use ANY as default
            enum_method = 3

        with self.appdata.project.cobra_py_model as model:
            update_stoichiometry_hash = False
            if sd_setup['use_scenario']:  # integrate scenario into model bounds
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

            targets = []
            desired = []
            for m in sd_setup[MODULES]:
                om = mcs_computation.relations2leq_matrix(m['constraints'], model.reactions)
                if m['module_type'] == 'suppress':
                   targets.append(om)
                elif m['module_type'] == 'protect':
                    desired.append(om)
                else:
                    raise ValueError(f"Unsupported module type {m['module_type']}")

            knock_in_idx = []
            if sd_setup['advanced']:
                iv_costs = np.ones((len(model.reactions),))
                cuts = np.full((len(model.reactions),), False, dtype=bool)
                for reac_id,cost in sd_setup[KOCOST].items():
                    idx = model.reactions.index(reac_id)
                    cuts[idx] = True
                    iv_costs[idx] = cost
                for reac_id,cost in sd_setup[KICOST].items():
                    idx = model.reactions.index(reac_id)
                    knock_in_idx.append(idx)
                    iv_costs[idx] = cost
            else:
                cuts = None
                iv_costs = None

            try:
                mcs, err_val = mcs_computation.compute_mcs(model,
                                targets=targets, desired=desired, enum_method=enum_method,
                                max_mcs_size=max_mcs_size, max_mcs_num=max_mcs_num, timeout=timeout,
                                cuts=cuts, knock_in_idx=knock_in_idx, intervention_costs=iv_costs,
                                include_model_bounds=True, use_kn_in_dual=True,
                                results_cache_dir=self.appdata.results_cache_dir
                                if self.appdata.use_results_cache else None)
            except mcs_computation.InfeasibleRegion as e:
                QMessageBox.warning(self, 'Cannot calculate MCS', str(e))
                return False
            except Exception:
                exstr = get_last_exception_string()
                if has_community_error_substring(exstr):
                    except_likely_community_model_error()
                else:
                    print(exstr)
                    show_unknown_error_box(exstr)
                return False

            if err_val == 1:
                QMessageBox.warning(self, "Enumeration stopped abnormally",
                                    "Result is probably incomplete.\nCheck console output for more information.")
                return False
            elif err_val == -1:
                QMessageBox.warning(self, "Enumeration terminated permaturely",
                                    "Aborted due to excessive generation of candidates that are not cut sets.\n"
                                    "Modify the problem or try a different enumeration setup.")
                return False

            if len(mcs) == 0:
                QMessageBox.information(self, 'No cut sets',
                                            'Cut sets have not been calculated or do not exist.')
                return False

            for i in range(len(mcs)):
                mcs_dict = {}
                mcs_idx = mcs[i]
                if len(knock_in_idx):
                    ki_idx = set(knock_in_idx)
                    mcs_idx = list(mcs_idx)
                    for idx in ki_idx.intersection(mcs_idx): # active knock-ins
                        mcs_dict[model.reactions[idx].id] = 1
                        mcs_idx.remove(idx)
                        ki_idx.remove(idx)
                    for idx in ki_idx: # inactive knock-ins
                        mcs_dict[model.reactions[idx].id] = 0
                for idx in mcs_idx: # knock-outs
                    mcs_dict[model.reactions[idx].id] = -1
                mcs[i] = mcs_dict
            solutions = SDSolutions(model, mcs, '', sd_setup)
            self.appdata.window.show_strain_designs(solutions)
            return True

    def cancel(self):
        self.appdata.window.sd_dialog = None
        self.deleteLater()
        self.reject()

    launch_computation_signal = Signal(str)

class SDComputationViewer(QDialog):
    """A dialog that shows the status of an ongoing strain design computation"""
    def __init__(self, parent, appdata: AppData, sd_setup):
        super().__init__(parent)

        self.sd_setup = sd_setup
        self.solutions = None
        self.appdata = appdata

        self.setWindowTitle("Strain Design Computation")
        self.setMinimumWidth(620)
        self.layout = QVBoxLayout()
        self.textbox = QTextEdit("Strain design computation progress:")
        self.layout.addWidget(self.textbox)

        buttons_layout = QHBoxLayout()
        self.explore = QPushButton("Explore strain designs")
        self.explore.clicked.connect(self.show_sd)
        self.explore.setMaximumWidth(200)
        self.explore.setEnabled(False)
        edit = QPushButton("Cancel && Edit strain design setup")
        edit.clicked.connect(self.open_strain_design_dialog)
        edit.setMaximumWidth(200)
        cancel = QPushButton("Cancel")
        cancel.setMaximumWidth(120)
        cancel.clicked.connect(self.cancel)
        buttons_layout.addWidget(self.explore)
        buttons_layout.addWidget(edit)
        buttons_layout.addWidget(cancel)
        self.layout.addItem(buttons_layout)

        self.setLayout(self.layout)
        self.show()

    @Slot(bytes)
    def conclude_computation(self,results):
        self.solutions = pickle.loads(results)
        self.setCursor(Qt.ArrowCursor)
        if self.solutions.get_num_sols() > 0:
            self.explore.setEnabled(True)

    @Slot(str)
    def receive_progress_text(self,txt):
        txt = txt.strip("\n\t\r ")
        if txt != "":
            self.textbox.append(txt)
            self.textbox.verticalScrollBar().setValue(self.textbox.verticalScrollBar().maximum())

    @Slot()
    def open_strain_design_dialog(self):
        self.cancel_computation.emit()
        self.appdata.window.strain_design_with_setup(self.sd_setup)
        self.deleteLater()
        self.accept()

    def show_sd(self):
        self.show_sd_signal.emit(pickle.dumps((self.solutions,self.sd_setup)))
        self.deleteLater()
        self.accept()

    def cancel(self):
        self.cancel_computation.emit()
        self.deleteLater()
        self.reject()

    show_sd_signal = Signal(bytes)
    cancel_computation = Signal()

class SDComputationThread(QThread):
    def __init__(self, appdata, sd_setup):
        super().__init__()
        self.appdata = appdata
        self.abort = False
        self.sd_setup = json.loads(sd_setup)
        self.curr_threadID = self.currentThread()
        self.sd_setup.pop(MODEL_ID)
        adv = self.sd_setup.pop('advanced')
        self.gkos = self.sd_setup.pop('gene_kos')
        if not adv and self.gkos: # ensure that gene-kos are computed, even when the
            self.sd_setup[GKOCOST] = None # advanced-button wasn't clicked
        # for debugging purposes write computation setup to file
        # with open('sd_computation.json', 'w') as fp:
        #     json.dump(self.sd_setup,fp)

    def run(self):
        with self.appdata.project.cobra_py_model as model:
            try:
                with redirect_stdout(self), redirect_stderr(self):
                    self.curr_threadID = self.currentThread()
                    logger = logging.getLogger()
                    handler = logging.StreamHandler(stream=self)
                    handler.setFormatter(logging.Formatter('%(message)s'))
                    logger.addHandler(handler)
                    logger.setLevel('INFO')
                    if self.sd_setup.pop('use_scenario'):
                        self.appdata.project.load_scenario_into_model(model)
                    sd_solutions = compute_strain_designs(model, **self.sd_setup)
                    self.finished_computation.emit(pickle.dumps(sd_solutions))
            except Exception as e:
                tb_str = ''.join(traceback.format_exception(None, e, e.__traceback__))
                self.write(tb_str)
                sd_solutions = SDSolutions(model,[],ERROR,self.sd_setup)
                self.finished_computation.emit(pickle.dumps(([],[],ERROR)))

    def write(self, input):
        # avoid that other threads use this as an output
        if self.curr_threadID == self.currentThread():
            if isinstance(input,str):
                self.output_connector.emit(input)
            else:
                self.output_connector.emit(str(input))

    def flush(self):
        pass

    # the output from the strain design computation needs to be passed as a signal because
    # all Qt widgets must run on the main thread and their methods cannot be safely called
    # from other threads
    output_connector = Signal(str)
    finished_computation = Signal(bytes)

class SDViewer(QDialog):
    """A dialog that shows the results of the strain design computation"""
    def __init__(self, appdata: AppData, solutions, with_setup: bool):
        super().__init__()
        if isinstance(solutions, SDSolutions):
            self.solutions = solutions
            self.sd_setup = self.solutions.sd_setup
        else:
            try:
                if with_setup:
                    (self.solutions,self.sd_setup) = pickle.loads(solutions)
                else:
                    self.solutions = pickle.loads(solutions)
            except pickle.UnpicklingError:
                QMessageBox.critical(
                    self,
                    'Could not open file',
                    "File could not be opened as it does not seem to be a valid strain design results file. "
                    "Maybe the file got the .sds ending for other reasons than being a strain design results file or the file is corrupted."
                )
                self.close()
                return
        self.setWindowTitle("Strain Design Solutions")
        self.setWindowModality(Qt.NonModal)
        self.setWindowFlags((self.windowFlags() | Qt.Window) & ~Qt.WindowStaysOnTopHint)
        self.setMinimumWidth(620)
        self.appdata = appdata
        appdata.project.sd_solutions = self.solutions

        self.layout = QVBoxLayout()

        if self.solutions.is_gene_sd:
            self.sd_table = QTableCopyable(0, 3)
        else:
            self.sd_table = QTableCopyable(0, 2)
        self.sd_table.verticalHeader().setDefaultSectionSize(20)
        self.sd_table.verticalHeader().setVisible(False)
        self.layout.addWidget(self.sd_table)

        buttons_layout = QHBoxLayout()
        self.savesds = QPushButton("Save solutions")
        self.savesds.clicked.connect(self.savesdsds)
        self.savesds.setMaximumWidth(120)
        self.savetsv = QPushButton("Save as tsv (tab separated values)")
        self.savetsv.clicked.connect(self.savesdtsv)
        self.savetsv.setMaximumWidth(230)
        self.edit = QPushButton("Discard solutions and edit setup")
        self.edit.clicked.connect(self.open_strain_design_dialog)
        self.edit.setMaximumWidth(200)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.closediag)
        self.close_button.setMaximumWidth(75)
        buttons_layout.addWidget(self.savesds)
        buttons_layout.addWidget(self.savetsv)
        buttons_layout.addWidget(self.edit)
        buttons_layout.addWidget(self.close_button)
        self.layout.addItem(buttons_layout)

        if self.solutions.is_gene_sd:
            (rsd,self.assoc,gsd) = self.solutions.get_gene_reac_sd_assoc_mark_no_ki()
        else:
            rsd = self.solutions.get_reaction_sd_mark_no_ki()
            self.assoc = [i for i in range(len(rsd))]
        itv_bounds = self.solutions.get_reaction_sd_bnds()
        appdata.project.modes = [itv_bounds[self.assoc.index(i)] for i in set(self.assoc)]
        central_widget = appdata.window.centralWidget()
        central_widget.mode_navigator.current = 0
        central_widget.mode_navigator.set_to_strain_design()
        central_widget.update_mode()

        # prepare strain designs
        if self.solutions.is_gene_sd:
            self.sd_table.setMinimumWidth(320)
            self.sd_table.setMinimumHeight(150)
            self.sd_table.setHorizontalHeaderLabels(["Equiv. class","Intervention set",\
                                                     "Reaction-phenotype interventions"])
            self.sd_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
            self.sd_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Interactive)
            self.sd_table.horizontalHeader().resizeSection(0, 90)
            self.sd_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
            self.rsd = ["" for _ in range(len(rsd))]
            for i,s in enumerate(rsd):
                for k,v in s.items():
                    if v > 0:
                        self.rsd[i] += "+"+k
                    elif v < 0:
                        self.rsd[i] += "-"+k
                    elif v == 0:
                        self.rsd[i] += u'\u2205'+k
                    self.rsd[i] += ", "
                self.rsd[i] = self.rsd[i][0:-2]
            self.gsd = ["" for _ in range(len(gsd))]
            for i,s in enumerate(gsd):
                for k,v in s.items():
                    if v > 0:
                        self.gsd[i] += "+"+k
                    elif v < 0:
                        self.gsd[i] += "-"+k
                    elif v == 0:
                        self.gsd[i] += u'\u2205'+k
                    self.gsd[i] += ", "
                self.gsd[i] = self.gsd[i][0:-2]
            for i,a,g in zip(range(len(self.gsd)), self.assoc, self.gsd):
                self.sd_table.insertRow(i)
                item = QTableItem(str(a+1))
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignCenter)
                self.sd_table.setItem(i, 0, item)
                # set non-editable
                item = QTableItem(g)
                item.setEditable(False)
                self.sd_table.setItem(i, 1, item)
                item = QTableItem(self.rsd[a])
                item.setEditable(False)
                self.sd_table.setItem(i, 2, item)
        else:
            self.rsd = ["" for _ in range(len(rsd))]
            for i,s in enumerate(rsd):
                for k,v in s.items():
                    if v > 0:
                        self.rsd[i] += "+"+k
                    elif v < 0:
                        self.rsd[i] += "-"+k
                    elif v == 0:
                        self.rsd[i] += u'\u2205'+k
                    self.rsd[i] += ", "
                self.rsd[i] = self.rsd[i][0:-2]
            self.sd_table.setMinimumWidth(320)
            self.sd_table.setMinimumHeight(150)
            self.sd_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Fixed)
            self.sd_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
            self.sd_table.horizontalHeader().resizeSection(0, 90)
            self.sd_table.setHorizontalHeaderLabels(["Equiv. class","Intervention set"])
            for i,s in enumerate(self.rsd):
                self.sd_table.insertRow(i)
                item = QTableItem(str(i+1))
                item.setEditable(False)
                item.setTextAlignment(Qt.AlignCenter)
                self.sd_table.setItem(i, 0, item)
                item = QTableItem(s)
                item.setEditable(False)
                self.sd_table.setItem(i, 1, item)
        self.sd_table.doubleClicked.connect(self.clicked_row)
        self.setLayout(self.layout)
        self.show()
        if self.solutions.has_complex_regul_itv:
            QMessageBox.information(self,"Non-trivial regulatory interventions",
                                         "The strain design contains 'complex' " +\
                                         "regulatory interventions that cannot be shown " +\
                                         "in the network map. Please refer to table.")
    def clicked_row(self,cell):
        row = cell.row()
        selection = int(self.sd_table.item(row,0).text())-1
        self.appdata.window.centralWidget().mode_navigator.current = selection
        self.appdata.window.centralWidget().update_mode()

    def closediag(self):
        self.appdata.window.sd_sols = None
        self.deleteLater()
        self.reject()

    def savesdtsv(self):
        # open file dialog
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            directory=self.appdata.work_directory, filter="*.tsv")[0]
        if not filename or len(filename) == 0:
            return
        elif len(filename)<=4 or filename[-4:] != '.tsv':
            filename += '.tsv'
        # save strain design list to Excel file
        if self.solutions.is_gene_sd:
            sd_string = "\n".join(["\t".join([str(a),g,self.rsd[a]]) for a,g in zip(self.assoc, self.gsd)])
        else:
            sd_string = "\n".join(self.rsd)
        with open(filename,'w') as fs:
            fs.write(sd_string)

    def savesdsds(self):
        # open file dialog
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            directory=self.appdata.work_directory, filter="*.sds")[0]
        if not filename or len(filename) == 0:
            return
        elif len(filename)<=4 or filename[-4:] != '.sds':
            filename += '.sds'
        self.solutions.save(filename)

    @Slot()
    def open_strain_design_dialog(self):
        self.appdata.window.strain_design_with_setup(json.dumps(self.sd_setup))
        self.appdata.window.sd_sols = None
        self.deleteLater()
        self.accept()
