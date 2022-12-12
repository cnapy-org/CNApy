"""The CNApy OptMDFpathway dialog"""
import cobra
import copy
from numpy import exp
from qtpy.QtCore import Qt, Signal, Slot
from qtpy.QtWidgets import (QDialog, QHBoxLayout, QLabel, QComboBox,
                            QMessageBox, QPushButton, QVBoxLayout)

from cnapy.appdata import AppData
from cnapy.gui_elements.central_widget import CentralWidget
from cnapy.utils import QComplReceivLineEdit
from straindesign import fba, linexpr2dict, linexprdict2str, avail_solvers
from straindesign.names import *
from cnapy.sd_class_interface import LinearProgram, Solver, Status
from cnapy.sd_ci_optmdfpathway import create_optmdfpathway_milp, STANDARD_R, STANDARD_T
from typing import Dict
from cobra.util.solver import interface_to_str
import re


def make_model_irreversible(cobra_model: cobra.Model,
                            forward_id:str = "_FWD", reverse_id: str="_REV") -> cobra.Model:
    # Create
    cobra_reaction_ids = [x.id for x in cobra_model.reactions]
    for cobra_reaction_id in cobra_reaction_ids:
        cobra_reaction: cobra.Reaction = cobra_model.reactions.get_by_id(cobra_reaction_id)

        create_forward = False
        create_reverse = False
        if cobra_reaction.lower_bound < 0:
            create_reverse = True
        elif (cobra_reaction.lower_bound == 0) and (cobra_reaction.upper_bound == 0):
            create_reverse = True
            create_forward = True
        elif (cobra_reaction.id.startswith("EX_")):
            create_reverse = True
            create_forward = True
        else:
            continue

        if cobra_reaction.upper_bound > 0:
            create_forward = True

        if create_forward:
            forward_reaction_id = cobra_reaction.id + forward_id
            forward_reaction = copy.deepcopy(cobra_reaction)
            forward_reaction.id = forward_reaction_id
            if cobra_reaction.lower_bound >= 0:
                forward_reaction.lower_bound = cobra_reaction.lower_bound
            else:
                forward_reaction.lower_bound = 0
            cobra_model.add_reactions([forward_reaction])

        if create_reverse:
            reverse_reaction_id = cobra_reaction.id + reverse_id
            reverse_reaction = copy.deepcopy(cobra_reaction)
            reverse_reaction.id = reverse_reaction_id

            metabolites_to_add = {}
            for metabolite in reverse_reaction.metabolites:
                metabolites_to_add[metabolite] = reverse_reaction.metabolites[metabolite] * -2
            reverse_reaction.add_metabolites(metabolites_to_add)

            if cobra_reaction.upper_bound < 0:
                reverse_reaction.lower_bound = -cobra_reaction.upper_bound
            else:
                reverse_reaction.lower_bound = 0
            reverse_reaction.upper_bound = -cobra_reaction.lower_bound

            cobra_model.add_reactions([reverse_reaction])

        if create_forward or create_reverse:
            cobra_model.remove_reactions([cobra_reaction])

    return cobra_model


class OptmdfpathwayDialog(QDialog):
    """A dialog to perform OptMDFpathway"""

    def __init__(self, appdata: AppData, central_widget: CentralWidget) -> None:
        self.FWDID = "_FWDCNAPY"
        self.REVID = "_REVCNAPY"

        QDialog.__init__(self)
        self.setWindowTitle("Perform OptMDFpathway")

        self.appdata = appdata
        self.central_widget = central_widget

        self.reac_ids = self.appdata.project.cobra_py_model.reactions.list_attr("id")
        self.metabolite_ids = self.appdata.project.cobra_py_model.metabolites.list_attr("id")

        self.layout = QVBoxLayout()
        l = QLabel(
            "Perform OptMDFpathway. dG'° values and metabolite concentration "
            "ranges have to be given in relevant annotations.\nWhat shall be shown afterwards?"
        )
        self.layout.addWidget(l)
        editor_layout = QHBoxLayout()
        self.show_combo = QComboBox()
        self.show_combo.insertItems(0, ['fluxes', 'driving forces'])
        self.show_combo.setMinimumWidth(120)
        editor_layout.addWidget(self.show_combo)
        self.layout.addItem(editor_layout)

        l3 = QHBoxLayout()
        self.button = QPushButton("Compute")
        self.cancel = QPushButton("Close")
        l3.addWidget(self.button)
        l3.addWidget(self.cancel)
        self.layout.addItem(l3)
        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

    def compute(self) -> None:
        self.setCursor(Qt.BusyCursor)

        dG0_values: Dict[str, Dict[str, float]] = {}
        for reaction in self.appdata.project.cobra_py_model.reactions:
            reaction: cobra.Reaction = reaction
            if "dG0" in reaction.annotation.keys():
                dG0_values[reaction.id] = {}
                dG0_values[reaction.id+self.FWDID] = {}
                dG0_values[reaction.id+self.REVID] = {}
                dG0_values[reaction.id]["dG0"] = float(reaction.annotation["dG0"])
                dG0_values[reaction.id+self.FWDID]["dG0"] = float(reaction.annotation["dG0"])
                dG0_values[reaction.id+self.REVID]["dG0"] = -float(reaction.annotation["dG0"])
                if "dG0_uncertainty" in reaction.annotation.keys():
                    dG0_values[reaction.id]["uncertainty"] = float(reaction.annotation["dG0_uncertainty"])
                    dG0_values[reaction.id+self.FWDID]["uncertainty"] = float(reaction.annotation["dG0_uncertainty"])
                    dG0_values[reaction.id+self.REVID]["uncertainty"] = float(reaction.annotation["dG0_uncertainty"])
                else:
                    dG0_values[reaction.id]["uncertainty"] = 0.0

        concentration_values: Dict[str, Dict[str, float]] = {}
        for metabolite in self.appdata.project.cobra_py_model.metabolites:
            metabolite: cobra.Metabolite = metabolite
            if ("Cmin" in metabolite.annotation.keys()) and ("Cmax" in metabolite.annotation.keys()):
                concentration_values[metabolite.id] = {}
                concentration_values[metabolite.id]["min"] = float(metabolite.annotation["Cmin"])
                concentration_values[metabolite.id]["max"] = float(metabolite.annotation["Cmax"])

        # optlang_solver_name = interface_to_str(self.appdata.project.cobra_py_model.problem)

        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            solvers = re.search('('+'|'.join(avail_solvers)+')',model.solver.interface.__name__)
            if solvers is not None:
                solver_str = solvers[0]
            if solver_str == "cplex":
                solver = Solver.CPLEX
            elif solver_str == "gurobi":
                solver = Solver.GUROBI
            else:
                solver = Solver.GLPK

            R = STANDARD_R
            T = STANDARD_T
            optmdfpathway_lp = create_optmdfpathway_milp(
                cobra_model=make_model_irreversible(cobra_model=model, forward_id=self.FWDID, reverse_id=self.REVID),
                dG0_values=dG0_values,
                concentration_values=concentration_values,
                extra_constraints=[],
                ratio_constraints=[],
                R=R,
                T=T,
            )
            optmdfpathway_lp.construct_solver_object(
                solver=solver,
            )
            solution = optmdfpathway_lp.run_solve()

            if solution.status == Status.INFEASIBLE:
                QMessageBox.warning(self, "Infeasible",
                                    "No solution exists, the problem is infeasible")
            elif solution.status == Status.TIME_LIMIT:
                QMessageBox.warning(self, "Time limit hit",
                                    "No solution could be calculated as the time limit was hit.")
            elif solution.status == Status.UNBOUNDED:
                QMessageBox.warning(self, "Unbounded",
                                    "The OptMDF is unbounded (inf) so that no optimization solution can be shown.")
            elif solution.status == Status.OPTIMAL:
                self.set_boxes(solution=solution.values)

            self.setCursor(Qt.ArrowCursor)
            self.accept()

    def set_boxes(self, solution: Dict[str, float]):
        # Combine FWD and REV flux solutions
        combined_solution = {}
        for var_id in solution.keys():
            if var_id.endswith(self.FWDID):
                key = var_id.replace(self.FWDID, "")
                multiplier = 1.0
            elif var_id.endswith(self.REVID):
                key = var_id.replace(self.REVID, "")
                multiplier = -1.0
            else:
                key = var_id
                multiplier = 1.0
            if key not in combined_solution.keys():
                combined_solution[key] = 0.0
            combined_solution[key] += multiplier * solution[var_id]

        # write results into comp_values
        for r in self.reac_ids:
            if self.show_combo.currentText() == "fluxes":
                search_key = r
            elif self.show_combo.currentText() == "driving forces":
                search_key = "f_var_"+r
            if r in combined_solution.keys():
                self.appdata.project.comp_values[r] = (
                    float(combined_solution[r]), float(combined_solution[r]))

        # Write metabolite concentrations
        for metabolite_id in self.metabolite_ids:
            var_id = f"x_{metabolite_id}"
            if var_id in solution.keys():
                print(var_id, solution[var_id])
                self.appdata.project.conc_values[var_id[2:]] = exp(solution[var_id])

        # Show selected reaction-dependent values
        self.appdata.project.comp_values_type = 0
        self.central_widget.update()

        # Show OptMDF
        optmdf = combined_solution["var_B"]
        self.central_widget.kernel_client.execute(f"print('\\nOptMDF: {optmdf} kJ/mol')")
        self.central_widget.show_bottom_of_console()
