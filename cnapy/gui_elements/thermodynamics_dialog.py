"""The CNApy OptMDFpathway dialog"""
import cobra
import cobra.util.solver
import copy
import pickle
from contextlib import redirect_stdout, redirect_stderr
from numpy import exp
from qtpy.QtCore import Qt, QThread, Signal, Slot
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
from cnapy.sd_class_interface import (
    LinearProgram,
    Result,
    Solver,
    Status,
    ObjectiveDirection,
)
from cnapy.sd_ci_optmdfpathway import create_optmdfpathway_milp, STANDARD_R, STANDARD_T
from typing import Dict
from cobra.util.solver import interface_to_str
from cnapy.core_gui import model_optimization_with_exceptions
import re
from cnapy.gui_elements.solver_buttons import get_solver_buttons
from straindesign.names import CPLEX, GLPK, GUROBI, SCIP
from enum import Enum


class ThermodynamicAnalysisTypes(Enum):
    OPTMDFPATHWAY = 1
    THERMODYNAMIC_FBA = 2
    BOTTLENECK_ANALYSIS = 3


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
            forward_reaction = cobra.Reaction(id=forward_reaction_id, name=cobra_reaction.name)
            forward_reaction.add_metabolites(cobra_reaction.metabolites)
            if cobra_reaction.lower_bound >= 0:
                forward_reaction.lower_bound = cobra_reaction.lower_bound
            else:
                forward_reaction.lower_bound = 0.0
            forward_reaction.upper_bound = cobra_reaction.upper_bound
            cobra_model.add_reactions([forward_reaction])

        if create_reverse:
            reverse_reaction_id = cobra_reaction.id + reverse_id
            reverse_reaction = cobra.Reaction(id=reverse_reaction_id, name=cobra_reaction.name)
            reverse_reaction.add_metabolites(cobra_reaction.metabolites)
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


class ComputationViewer(QDialog):
    """A dialog that shows the status of an ongoing computation"""

    def __init__(self):
        super().__init__()

        self.setWindowTitle("Computation is running...")

        self.setMinimumWidth(620)
        self.layout = QVBoxLayout()

        buttons_layout = QHBoxLayout()
        cancel = QPushButton("Cancel")
        cancel.setMaximumWidth(120)
        cancel.clicked.connect(self.cancel)
        buttons_layout.addWidget(cancel)
        self.layout.addItem(buttons_layout)

        self.setLayout(self.layout)
        self.show()

    @Slot()
    def close_window(self):
        self.deleteLater()
        self.accept()

    @Slot()
    def cancel(self):
        self.cancel_computation.emit()
        self.deleteLater()
        self.reject()

    cancel_computation = Signal()


class ComputationThread(QThread):
    def __init__(self, linear_program: LinearProgram):
        # super().__init__()
        QThread.__init__(self)
        self.linear_program: LinearProgram = linear_program

    def run(self):
        try:
            with redirect_stdout(self), redirect_stderr(self):
                solution = self.linear_program.run_solve()
                self.send_solution.emit(pickle.dumps(solution))
                self.finished_computation.emit()
        except Exception:
            self.send_solution.emit(pickle.dumps("ERROR"))
            self.finished_computation.emit()

    def flush(self):
        pass

    # the output from the computation needs to be passed as a signal because
    # all Qt widgets must run on the main thread and their methods cannot be safely called
    # from other threads
    send_solution = Signal(bytes)
    finished_computation = Signal()


class ThermodynamicDialog(QDialog):
    """A dialog to perform several thermodynamic methods."""

    def __init__(
        self, appdata: AppData, central_widget: CentralWidget, analysis_type: ThermodynamicAnalysisTypes
    ) -> None:
        self.FWDID = "_FWDCNAPY"
        self.REVID = "_REVCNAPY"

        QDialog.__init__(self)
        if analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
            window_title = "Perform OptMDFpathway"
        elif analysis_type == ThermodynamicAnalysisTypes.BOTTLENECK_ANALYSIS:
            window_title = "Perform OptMDFpathway bottleneck analysis"
        elif analysis_type == ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA:
            window_title = "Perform thermodynamic FBA"
        self.setWindowTitle(window_title)

        self.appdata = appdata
        self.central_widget = central_widget
        self.analysis_type = analysis_type

        self.reac_ids = self.appdata.project.cobra_py_model.reactions.list_attr("id")
        self.metabolite_ids = self.appdata.project.cobra_py_model.metabolites.list_attr(
            "id"
        )

        self.layout = QVBoxLayout()
        if analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
            l = QLabel(
                "Perform OptMDFpathway. dG'° values and metabolite concentration "
                "ranges have to be given in relevant annotations."
            )
            self.layout.addWidget(l)
        elif analysis_type == ThermodynamicAnalysisTypes.BOTTLENECK_ANALYSIS:
            l = QLabel(
                "Perform OptMDFpathway bottleneck analysis. dG'° values and metabolite concentration "
                "ranges have to be given in relevant annotations.\nThe minimal amount of bottlenecks and their IDs "
                "to reach the given minimal MDF will be shown in the console afterwards."
            )
            self.layout.addWidget(l)
        elif analysis_type == ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA:
            l = QLabel(
                "Perform thermodynamic Flux Balance Analysis. Based on OptMDFpathway, you can perform an FBA at an OptMDF greater than the given value. "
                "\nE.g., if the OptMDF is greater than 0 kJ/mol, you perform an FBA with enforced thermodynamic feasibility."
                "\nFor this analysis, dG'° values and metabolite concentration "
                "ranges have to be given in relevant annotations.\nThe minimal amount of bottlenecks and their IDs "
                "to reach the given minimal MDF will be shown in the console afterwards."
            )
            self.layout.addWidget(l)

        if (analysis_type == ThermodynamicAnalysisTypes.BOTTLENECK_ANALYSIS) or (analysis_type == ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA):
            lineedit_text = QLabel("MDF to reach [in kJ/mol]:")

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

        if analysis_type == ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA:
            self.at_objective.hide()

        met_concs_text = QLabel(
            "Default 'Cmin' and 'Cmax' values [in M] that will be used when not defined in a metabolite's annotation:"
        )
        self.layout.addWidget(met_concs_text)

        default_concs_layout = QHBoxLayout()

        text_min_default_conc = QLabel("Default Cmin [in M]:")
        self.min_default_conc = QLineEdit()
        self.min_default_conc.setText("1e-6")
        default_concs_layout.addWidget(text_min_default_conc)
        default_concs_layout.addWidget(self.min_default_conc)

        text_max_default_conc = QLabel(" Default Cmax [in M]:")
        self.max_default_conc = QLineEdit()
        self.max_default_conc.setText("0.2")
        default_concs_layout.addWidget(text_max_default_conc)
        default_concs_layout.addWidget(self.max_default_conc)

        self.layout.addItem(default_concs_layout)

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

    def get_solution_from_thread(self, solution) -> None:
        solution = pickle.loads(solution)

        if solution == "ERROR":
            QMessageBox.warning(
                self,
                "Computational error",
                "Something went really wrong. The computation could not run.",
            )
        elif solution.status == Status.INFEASIBLE:
            QMessageBox.warning(
                self, "Infeasible", "No solution exists, the problem is either stoichiometrically or thermodynamically (e.g., the minimal MDF is too high) infeasible"
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
            self.set_boxes(solution=solution.values, objective_value=solution.objective_value)

        self.setCursor(Qt.ArrowCursor)
        self.accept()

    @Slot()
    def compute_in_thread(
        self, linear_program: LinearProgram
    ) -> None:
        # launch progress viewer and computation thread
        self.computation_viewer = ComputationViewer()
        # connect signals to update progress
        self.computation_thread = ComputationThread(linear_program)
        self.computation_thread.finished_computation.connect(
            self.computation_viewer.close_window, Qt.QueuedConnection
        )
        self.computation_thread.send_solution.connect(
            self.get_solution_from_thread, Qt.QueuedConnection
        )
        self.computation_viewer.cancel_computation.connect(
            self.computation_thread.terminate, Qt.QueuedConnection
        )
        # show dialog and launch process
        self.computation_viewer.show()
        self.computation_thread.start()
        self.hide()

    @Slot()
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
                "constraints are set so that no thermodynamic OptMDFpathway can be calculated as "
                "at least one reaction needs a given dG'°. "
                "In order to solve this, please set or calculate (e.g., with eQuilibrator) dG'° "
                "values and either type them directly in as 'dG0' annotations or load them as "
                "JSON or Excel XLSX.",
            )
            return

        concentration_values: Dict[str, Dict[str, float]] = {}
        for metabolite in self.appdata.project.cobra_py_model.metabolites:
            metabolite: cobra.Metabolite = metabolite
            concentration_values[metabolite.id] = {}
            for conc_bound in ("Cmin", "Cmax"):
                if (conc_bound in metabolite.annotation.keys()):
                    try:
                        concentration_values[metabolite.id][conc_bound.replace("C", "")] = float(
                            metabolite.annotation[conc_bound]
                        )
                    except ValueError:
                        QMessageBox.warning(
                            self,
                            f"Wrong {conc_bound} data type",
                            f"The {conc_bound} given in metabolite {metabolite.id} is set as "
                            f"{metabolite.annotation['Cmin']} and does not seem to be a valid number."
                            " Please correct this entry so that it becomes a valid number.",
                        )
                        return
                else:
                    try:
                        if conc_bound == "Cmin":
                            bound_value = float(self.max_default_conc.text())
                        else:
                            bound_value = float(self.max_default_conc.text())
                    except ValueError:
                        QMessageBox.warning(
                            self,
                            f"Wrong default {conc_bound} data type",
                            f"The default {conc_bound} given by you in the dialog is set as "
                            f"{bound_value} and does not seem to be a valid number."
                            " Please correct this entry so that it becomes a valid number.",
                        )
                        return
                    concentration_values[metabolite.id][conc_bound.replace("C", "")] = bound_value

        with self.appdata.project.cobra_py_model as model:
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

            if self.analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
                minimal_optmdf = -float("inf")
            else:
                minimal_optmdf_str = self.min_mdf.text()
                try:
                    minimal_optmdf = float(minimal_optmdf_str)
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Invalid minimal OptMDF",
                        f"The given minimal OptMDF could not be converted into a valid number (such as, e.g., 1.231)."
                        "Aborting calculation...",
                    )
                    return

            R = STANDARD_R
            T = STANDARD_T
            optmdfpathway_lp = create_optmdfpathway_milp(
                cobra_model=make_model_irreversible(model, forward_id=self.FWDID, reverse_id=self.REVID),
                dG0_values=dG0_values,
                concentration_values=concentration_values,
                extra_constraints=extra_constraints,
                ratio_constraints=[],
                R=R,
                T=T,
                add_bottleneck_constraints=self.analysis_type == ThermodynamicAnalysisTypes.BOTTLENECK_ANALYSIS,
                minimal_optmdf=minimal_optmdf,
            )
            if self.analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
                optmdfpathway_lp.set_objective(
                    {"var_B": 1},
                    direction=ObjectiveDirection.MAX,
                )
            elif self.analysis_type == ThermodynamicAnalysisTypes.BOTTLENECK_ANALYSIS:
                optmdfpathway_lp.set_objective(
                    {"bottleneck_z_sum": 1},
                    direction=ObjectiveDirection.MIN,
                )
            elif self.analysis_type == ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA:
                objective_dict = {}
                for (
                    reaction,
                    coefficient,
                ) in cobra.util.solver.linear_reaction_coefficients(model).items():
                    if reaction.reversibility:
                        objective_dict[reaction.id + self.FWDID] = coefficient
                        objective_dict[reaction.id + self.REVID] = -coefficient
                    else:
                        objective_dict[reaction.id] = coefficient

                optmdfpathway_lp.set_objective(
                    objective_dict,
                    direction=ObjectiveDirection.MIN,
                )
            optmdfpathway_lp.construct_solver_object(
                solver=solver,
            )
            # solution = optmdfpathway_lp.run_solve()
            self.compute_in_thread(
                linear_program=optmdfpathway_lp,
            )

    def set_boxes(self, solution: Dict[str, float], objective_value: float):
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
                rounded_df = round(
                    combined_solution["f_var_" + search_key], self.appdata.rounding
                )
                self.appdata.project.df_values[search_key] = rounded_df

        # Write metabolite concentrations
        for metabolite_id in self.metabolite_ids:
            var_id = f"x_{metabolite_id}"
            if var_id in solution.keys():
                rounded_conc = round(exp(solution[var_id]), 9)
                self.appdata.project.conc_values[var_id[2:]] = rounded_conc

        # Show selected reaction-dependent values
        self.appdata.project.comp_values_type = 0
        self.central_widget.update()

        # Show OptMDF
        console_text = "print('\\n"
        if self.analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
            optmdf = combined_solution["var_B"]
            console_text += f"OptMDF: {optmdf} kJ/mol"
        elif self.analysis_type == ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA:
            optmdf = combined_solution["var_B"]
            console_text += f"Reached objective value: {objective_value}"
            console_text += f"\\nReached MDF @ optimum of objective: {optmdf} kJ/mol"
        elif self.analysis_type == ThermodynamicAnalysisTypes.BOTTLENECK_ANALYSIS:
            combined_bottleneck_sum = 0
            for key in combined_solution.keys():
                if key.startswith("bottleneck_z_"):
                    if key == "bottleneck_z_sum":
                        continue
                    if combined_solution[key] > 0.1:
                        console_text += f"\\n* {key.replace('bottleneck_z_', '')}"
                        combined_bottleneck_sum += 1
            console_text += f"\\n↳Total number of thermodynamically deactivated bottlenecks to reach minimal MDF: {combined_bottleneck_sum}"
        console_text += "')"
        self.central_widget.kernel_client.execute(console_text)
        self.central_widget.show_bottom_of_console()
