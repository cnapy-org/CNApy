"""The CNApy OptMDFpathway dialog"""
import cobra
import cobra.util.solver
import copy
from numpy import exp
from qtpy.QtCore import Qt, Signal, Slot
from qtpy.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QGroupBox,
)

from cnapy.appdata import AppData
from cnapy.gui_elements.central_widget import CentralWidget
from straindesign import avail_solvers
from straindesign.names import *
from cnapy.sd_class_interface import LinearProgram, Solver, Status, ObjectiveDirection
from cnapy.sd_ci_optmdfpathway import create_optmdfpathway_milp, STANDARD_R, STANDARD_T
from typing import Dict
from cobra.util.solver import interface_to_str
from cnapy.core import model_optimization_with_exceptions
import re
from cnapy.gui_elements.solver_buttons import get_solver_buttons
from straindesign.names import CPLEX, GLPK, GUROBI, SCIP


def make_model_irreversible(
    cobra_model: cobra.Model, forward_id: str = "_FWD", reverse_id: str = "_REV"
) -> cobra.Model:
    # Create
    cobra_reaction_ids = [x.id for x in cobra_model.reactions]
    for cobra_reaction_id in cobra_reaction_ids:
        cobra_reaction: cobra.Reaction = cobra_model.reactions.get_by_id(
            cobra_reaction_id
        )

        create_forward = False
        create_reverse = False
        if cobra_reaction.lower_bound < 0:
            create_reverse = True
        elif (cobra_reaction.lower_bound == 0) and (cobra_reaction.upper_bound == 0):
            create_reverse = True
            create_forward = True
        elif cobra_reaction.id.startswith("EX_"):
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
                metabolites_to_add[metabolite] = (
                    reverse_reaction.metabolites[metabolite] * -2
                )
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


class ThermodynamicDialog(QDialog):
    """A dialog to perform several thermodynamic methods."""

    def __init__(self, appdata: AppData, central_widget: CentralWidget, bottleneck_analysis: bool) -> None:
        self.FWDID = "_FWDCNAPY"
        self.REVID = "_REVCNAPY"

        QDialog.__init__(self)
        self.setWindowTitle("Perform OptMDFpathway")

        self.appdata = appdata
        self.central_widget = central_widget
        self.bottleneck_analysis = bottleneck_analysis

        self.reac_ids = self.appdata.project.cobra_py_model.reactions.list_attr("id")
        self.metabolite_ids = self.appdata.project.cobra_py_model.metabolites.list_attr(
            "id"
        )

        self.layout = QVBoxLayout()
        if not self.bottleneck_analysis:
            l = QLabel(
                "Perform OptMDFpathway. dG'° values and metabolite concentration "
                "ranges have to be given in relevant annotations."
            )
            self.layout.addWidget(l)
        else:
            l = QLabel(
                "Perform OptMDFpathway bottleneck analysis. dG'° values and metabolite concentration "
                "ranges have to be given in relevant annotations.\nThe minimal amount of bottlenecks and their IDs "
                "to reach the given minimal MDF will be shown in the console afterwards."
            )
            self.layout.addWidget(l)

            lineedit_text = QLabel("MDF to reach [ín kJ/mol]:")

            min_mdf_layout = QHBoxLayout()
            self.min_mdf = QLineEdit()
            self.min_mdf.setText("0.01")

            min_mdf_layout.addWidget(lineedit_text)
            min_mdf_layout.addWidget(self.min_mdf)
            self.layout.addItem(min_mdf_layout)

        self.at_objective = QCheckBox(
            "Set optimized value of current objective as lower boundary constraint"
        )
        self.at_objective.setChecked(True)
        self.layout.addWidget(self.at_objective)

        solver_group = QGroupBox("Solver:")
        solver_buttons_layout, self.solver_buttons = get_solver_buttons(appdata)
        solver_group.setLayout(solver_buttons_layout)
        self.layout.addWidget(solver_group)

        l3 = QHBoxLayout()
        self.button_optmdf = QPushButton("Compute")
        self.cancel = QPushButton("Close")
        l3.addWidget(self.button_optmdf)
        l3.addWidget(self.cancel)
        self.layout.addItem(l3)
        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button_optmdf.clicked.connect(self.compute_optmdf)

    def compute_optmdf(self):
        self.setCursor(Qt.BusyCursor)

        dG0_values: Dict[str, Dict[str, float]] = {}
        for reaction in self.appdata.project.cobra_py_model.reactions:
            reaction: cobra.Reaction = reaction
            if "dG0" in reaction.annotation.keys():
                dG0_values[reaction.id] = {}
                dG0_values[reaction.id + self.FWDID] = {}
                dG0_values[reaction.id + self.REVID] = {}
                dG0_values[reaction.id]["dG0"] = float(reaction.annotation["dG0"])
                try:
                    dG0_values[reaction.id + self.FWDID]["dG0"] = float(
                        reaction.annotation["dG0"]
                    )
                    dG0_values[reaction.id + self.REVID]["dG0"] = -float(
                        reaction.annotation["dG0"]
                    )
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Wrong dG'° data type",
                        f"The dG'° given in reaction {reaction.id} is set as {reaction.annotation['dG0']} "
                        "and does not seem to be a valid number. Please correct this entry.",
                    )
                    return
                if "dG0_uncertainty" in reaction.annotation.keys():
                    dG0_values[reaction.id]["uncertainty"] = float(
                        reaction.annotation["dG0_uncertainty"]
                    )
                    try:
                        dG0_values[reaction.id + self.FWDID]["uncertainty"] = float(
                            reaction.annotation["dG0_uncertainty"]
                        )
                        dG0_values[reaction.id + self.REVID]["uncertainty"] = float(
                            reaction.annotation["dG0_uncertainty"]
                        )
                    except ValueError:
                        QMessageBox.warning(
                            self,
                            "Wrong dG'° uncertainty data type",
                            f"The dG'° uncertainty given in reaction {reaction.id} is set as {reaction.annotation['dG0_uncertainty']} "
                            "and does not seem to be a valid number. Please correct this entry.",
                        )
                        return
                else:
                    dG0_values[reaction.id]["uncertainty"] = 0.0
                    dG0_values[reaction.id + self.FWDID]["uncertainty"] = 0.0
                    dG0_values[reaction.id + self.REVID]["uncertainty"] = 0.0

        if dG0_values == {}:
            QMessageBox.warning(
                self,
                "No dG'° set",
                f"No reaction has a given standard Gibbs free energy (i.e., a dG'° which "
                "is set through the reaction annotation 'dG0'. This means that no thermodynamic "
                "constraints are set so that no thermodynamic OptMDFpathway can be calculated. "
                "In order to solve this, please set or calculate (e.g., with eQuilibrator) dG'° "
                "values and either type them directly in as 'dG0' annotations or load them as "
                "JSON or Excel XLSX.",
            )
            return

        missing_concentrations_str = ""
        concentration_values: Dict[str, Dict[str, float]] = {}
        for metabolite in self.appdata.project.cobra_py_model.metabolites:
            metabolite: cobra.Metabolite = metabolite
            if ("Cmin" in metabolite.annotation.keys()) and (
                "Cmax" in metabolite.annotation.keys()
            ):
                concentration_values[metabolite.id] = {}
                try:
                    concentration_values[metabolite.id]["min"] = float(
                        metabolite.annotation["Cmin"]
                    )
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Wrong Cmin data type",
                        f"The Cmin given in metabolite {metabolite.id} is set as {metabolite.annotation['Cmin']} "
                        "and does not seem to be a valid number. Please correct this entry.",
                    )
                    return
                try:
                    concentration_values[metabolite.id]["max"] = float(
                        metabolite.annotation["Cmax"]
                    )
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Wrong Cmax data type",
                        f"The Cmax given in metabolite {metabolite.id} is set as {metabolite.annotation['Cmax']} "
                        "and does not seem to be a valid number. Please correct this entry.",
                    )
                    return
            else:
                missing_concentrations_str += f"* {metabolite.id}\n"

            if missing_concentrations_str != "":
                QMessageBox.warning(
                    self,
                    "Metabolite(s) without concentration range",
                    f"Some metabolite(s) do not have a given concentration range "
                    "(i.e., Cmin and Cmax in their annotation). This would cause an OptMDFpathway "
                    "computation error. In order to solve this, add concentration ranges (i.e., Cmin "
                    "and Cmax) for these metabolites. If you load concentration ranges from a JSON or Excel XLSX, "
                    "add a 'DEFAULT' concentration range which will be used for all unset metabolites."
                    "The following metabolites are affected:\n"
                    f"{missing_concentrations_str}",
                )
                return

        with self.appdata.project.cobra_py_model as model:
            reaction_ids = [x.id for x in model.reactions]
            self.appdata.project.load_scenario_into_model(model)

            if self.at_objective.isChecked():
                solution = model_optimization_with_exceptions(model)
                if solution.status == "optimal":
                    extra_constraint = {}
                    for (
                        reaction,
                        coefficient,
                    ) in cobra.util.solver.linear_reaction_coefficients(model).items():
                        if reaction.reversibility:
                            extra_constraint[reaction.id + self.FWDID] = coefficient
                            extra_constraint[reaction.id + self.REVID] = -coefficient
                        else:
                            extra_constraint[reaction.id] = coefficient
                    extra_constraint["lb"] = solution.objective_value
                    extra_constraints = [extra_constraint]
                else:
                    QMessageBox.warning(
                        self,
                        solution.status,
                        f"No objective solution exists, the problem status is."
                        "Try the objective optimization with FBA alone for finding the problem, "
                        "or try a different objective.",
                    )
                    return
            else:
                extra_constraints = []

            for constraint in self.appdata.project.scen_values.constraints:
                # e.g., [({'EDD': 1.0}, '>=', 1.0)]
                extra_constraint = {key: value for key, value in constraint[0].items()}

                direction = constraint[1]
                rhs = constraint[2]
                if direction == ">=":
                    extra_constraint["lb"] = rhs
                elif direction == "<=":
                    extra_constraint["ub"] = rhs
                else:  # == "="
                    extra_constraint["lb"] = rhs
                    extra_constraint["ub"] = rhs

                extra_constraints.append(extra_constraint)

            solver_name = self.solver_buttons["group"].checkedButton().property("name")
            if solver_name == CPLEX:
                solver = Solver.CPLEX
            elif solver_name == GUROBI:
                solver = Solver.GUROBI
            elif solver_name == SCIP:
                solver = Solver.SCIP
            elif solver_name == GLPK:
                solver = Solver.GLPK

            if not self.bottleneck_analysis:
                minimal_optmdf = -float("inf")
            else:
                minimal_optmdf_str = self.min_mdf.text()
                try:
                    minimal_optmdf = float(minimal_optmdf_str)
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Invalid minimal OptMDF",
                        f"The given minimal OptMDF could not be converted into a valid number (such as 1.231). Aborting calculation...",
                    )
                    return

            R = STANDARD_R
            T = STANDARD_T
            optmdfpathway_lp = create_optmdfpathway_milp(
                cobra_model=model,
                dG0_values=dG0_values,
                concentration_values=concentration_values,
                extra_constraints=extra_constraints,
                ratio_constraints=[],
                R=R,
                T=T,
                add_bottleneck_constraints=self.bottleneck_analysis,
                minimal_optmdf=minimal_optmdf,
            )
            if not self.bottleneck_analysis:
                optmdfpathway_lp.set_objective(
                    {"var_B": 1},
                    direction=ObjectiveDirection.MAX,
                )
            else:
                optmdfpathway_lp.set_objective(
                    {"bottleneck_z_sum": 1},
                    direction=ObjectiveDirection.MIN,
                )
            optmdfpathway_lp.construct_solver_object(
                solver=solver,
            )
            solution = optmdfpathway_lp.run_solve()

            if solution.status == Status.INFEASIBLE:
                QMessageBox.warning(
                    self, "Infeasible", "No solution exists, the problem is infeasible"
                )
            elif solution.status == Status.TIME_LIMIT:
                QMessageBox.warning(
                    self,
                    "Time limit hit",
                    "No solution could be calculated as the time limit was hit.",
                )
            elif solution.status == Status.UNBOUNDED:
                QMessageBox.warning(
                    self,
                    "Unbounded",
                    "The solution is unbounded (inf) so that no optimization solution can be shown.",
                )
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
        for search_key in self.reac_ids:
            if search_key in combined_solution.keys():
                self.appdata.project.comp_values[search_key] = (
                    float(combined_solution[search_key]),
                    float(combined_solution[search_key]),
                )
            if "f_var_" + search_key in combined_solution.keys():
                self.appdata.project.df_values[search_key] = combined_solution[
                    "f_var_" + search_key
                ]

        # Write metabolite concentrations
        for metabolite_id in self.metabolite_ids:
            var_id = f"x_{metabolite_id}"
            if var_id in solution.keys():
                self.appdata.project.conc_values[var_id[2:]] = round(exp(solution[var_id]), 6)

        # Show selected reaction-dependent values
        self.appdata.project.comp_values_type = 0
        self.central_widget.update()

        # Show OptMDF
        console_text = "print('\\n"
        if not self.bottleneck_analysis:
            optmdf = combined_solution["var_B"]
            console_text += f"OptMDF: {optmdf} kJ/mol"
        else:
            bottleneck_z_sum = combined_solution["bottleneck_z_sum"]
            console_text += f"Number of deactivated bottlenecks to reach minimal MDF: {bottleneck_z_sum}"

            for key in combined_solution.keys():
                if key.startswith("bottleneck_z_"):
                    if key == "bottleneck_z_sum":
                        continue
                    if combined_solution[key] > 0.1:
                        console_text += f"\\n* {key.replace('bottleneck_z_', '')}"
        console_text += "')"
        print(console_text)
        self.central_widget.kernel_client.execute(
            console_text
        )
        self.central_widget.show_bottom_of_console()
