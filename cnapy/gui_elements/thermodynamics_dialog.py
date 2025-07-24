"""The CNApy OptMDFpathway dialog"""
import cobra
import cobra.util.solver
from numpy import exp
from qtpy.QtCore import Qt, Slot
from qtpy.QtWidgets import (
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
from cnapy.gui_elements.solver_buttons import get_solver_buttons
from enum import Enum
from cobrak.constants import LNCONC_VAR_PREFIX, DF_VAR_PREFIX, MDF_VAR_ID, ALL_OK_KEY, OBJECTIVE_VAR_NAME, TERMINATION_CONDITION_KEY
from cobrak.dataclasses import ExtraLinearConstraint, Solver
from cobrak.lps import perform_lp_optimization, perform_lp_thermodynamic_bottleneck_analysis
from cobrak.io import load_annotated_cobrapy_model_as_cobrak_model
from cobrak.cobrapy_model_functionality import get_fullsplit_cobra_model



class ThermodynamicAnalysisTypes(Enum):
    OPTMDFPATHWAY = 1
    THERMODYNAMIC_FBA = 2
    BOTTLENECK_ANALYSIS = 3


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
        match analysis_type:
            case ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
                label = QLabel(
                    "Perform OptMDFpathway. ΔG'° values and metabolite concentration "
                    "ranges have to be given in relevant annotations."
                )
            case ThermodynamicAnalysisTypes.BOTTLENECK_ANALYSIS:
                label = QLabel(
                    "Perform OptMDFpathway bottleneck analysis. ΔG'° values and metabolite concentration "
                    "ranges have to be given in relevant annotations.\nThe minimal amount of bottlenecks and their IDs "
                    "to reach the given minimal MDF will be shown in the console afterwards."
                )
            case ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA:
                label = QLabel(
                    "Perform thermodynamic Flux Balance Analysis. Based on OptMDFpathway, you can perform an FBA at an OptMDF greater than the given value. "
                    "\nE.g., if the OptMDF is greater than 0 kJ/mol, you perform an FBA with enforced thermodynamic feasibility."
                    "\nFor this analysis, ΔG'° values and metabolite concentration "
                    "ranges have to be given in relevant annotations.\nThe minimal amount of bottlenecks and their IDs "
                    "to reach the given minimal MDF will be shown in the console afterwards."
                )
        self.layout.addWidget(label)

        if (analysis_type == ThermodynamicAnalysisTypes.BOTTLENECK_ANALYSIS) or (analysis_type == ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA):
            lineedit_text = QLabel("MDF to reach [in kJ/mol]:")

            min_mdf_layout = QHBoxLayout()
            self.min_mdf = QLineEdit()
            self.min_mdf.setText("0.01")

            min_mdf_layout.addWidget(lineedit_text)
            min_mdf_layout.addWidget(self.min_mdf)
            self.layout.addItem(min_mdf_layout)

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

    def get_solution_from_thread(self, solution: dict[str, float]) -> None:
        if not solution[ALL_OK_KEY]:
            if TERMINATION_CONDITION_KEY in solution:
                match solution[TERMINATION_CONDITION_KEY]:
                    case 1:
                        warning_title = "Time limit"
                        warning_text = "Solver's time limit hit. Please change solver or problem complexity."
                    case 2:
                        warning_title = "Iterations limit"
                        warning_text = "Solver's iterations limit hit. Please change solver or problem complexity."
                    case 7:
                        warning_title = "Problem unbounded"
                        warning_text = "The problem appears to be unbounded, i.e. there is no constraint limiting the objective values."
                    case 8:
                        warning_title = "Problem infeasible"
                        warning_text = "The problem appears to be infeasible, i.e. the constraints make a solution impossible."
                    case 10:
                        warning_title = "Solver failure"
                        warning_text = "Your solver seems to have crashed. Try another solver."
                    case 11:
                        warning_title = "Internal solver failure"
                        warning_text = "Your solver seems to have crashed. Try another solver."
                    case 15:
                        warning_title = "License problem"
                        warning_text = "License problem with the solver! Check out CNApy's documentation for more about how to solve it for CPLEX and Gurobi, or try another solver."
                    case _:
                        warning_title = "Solver problem"
                        warning_text = "The solution process or the solution failed somehow."
                QMessageBox.warning(
                    self,
                    warning_title,
                    warning_text,
                )
            else:
                QMessageBox.warning(
                    self,
                    "Computational error",
                    "Something went wrong (CNApy could not identify the type of error). The computation could not run. Check your problem's constraints or try a different solver.",
                )
        else:
            self.set_boxes(solution=solution)

        self.setCursor(Qt.ArrowCursor)
        self.accept()

    @Slot()
    def compute_optmdf(self):
        self.setCursor(Qt.BusyCursor)

        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)

            extra_linear_constraints: list[ExtraLinearConstraint] = []
            for constraint in self.appdata.project.scen_values.constraints:
                # e.g., [({'EDD': 1.0}, '>=', 1.0)]
                extra_linear_constraint = ExtraLinearConstraint(
                    stoichiometries={key: value for key, value in constraint[0].items()},
                )

                direction = constraint[1]
                rhs = constraint[2]
                if direction == ">=":
                    extra_linear_constraint.lower_value = rhs
                elif direction == "<=":
                    extra_linear_constraint.upper_value = rhs
                else:  # == "="
                    extra_linear_constraint.lower_value = rhs
                    extra_linear_constraint.upper_value = rhs

                extra_linear_constraints.append(extra_linear_constraint)

            solver_name = self.solver_buttons["group"].checkedButton().property("cobrak_name")

            if self.analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
                min_mdf = -float("inf")
            else:
                try:
                    min_mdf = float(self.min_mdf.text())
                except ValueError:
                    QMessageBox.warning(
                        self,
                        "Invalid minimal OptMDF",
                        "The given minimal OptMDF could not be converted into a valid number (such as, e.g., 1.231)."
                        "Aborting calculation...",
                    )
                    return

            match self.analysis_type:
                case ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
                    objective = {MDF_VAR_ID: 1}
                    direction = +1
                case ThermodynamicAnalysisTypes.BOTTLENECK_ANALYSIS:
                    objective = {"bottleneck_z_sum": 1}
                    direction = -1
                case ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA:
                    objective = {}
                    for (
                        reaction,
                        coefficient,
                    ) in cobra.util.solver.linear_reaction_coefficients(model).items():
                        if reaction.reversibility:
                            objective[reaction.id + self.FWDID] = coefficient
                            objective[reaction.id + self.REVID] = -coefficient
                        else:
                            objective[reaction.id] = coefficient
                    direction = +1

            cobrak_model = load_annotated_cobrapy_model_as_cobrak_model(
                get_fullsplit_cobra_model(
                    model,
                    fwd_suffix=self.FWDID,
                    rev_suffix=self.REVID,
                    add_cobrak_sbml_annotation=True,
                    cobrak_default_min_conc=float(self.min_default_conc.text()),
                    cobrak_default_max_conc=float(self.max_default_conc.text()),
                    cobrak_extra_linear_constraints=extra_linear_constraints,
                    cobrak_kinetic_ignored_metabolites=[],
                    cobrak_no_extra_versions=True,
                    reac_lb_ub_cap=1_000.0,
                )
            )

            if all(cobrak_model.reactions[reac_id].dG0 is None for reac_id in cobrak_model.reactions):
                QMessageBox.warning(
                    self,
                    "No ΔG'° set",
                    "To run a thermodynamic calculation, your model needs at least one reaction with a ΔG'° (annotation 'dG0')."
                    "Check out CNApy's documentation for more",
                )
                self.setCursor(Qt.ArrowCursor)
                return
            if self.analysis_type in (ThermodynamicAnalysisTypes.OPTMDFPATHWAY, ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA):
                solution = perform_lp_optimization(
                    cobrak_model=cobrak_model,
                    objective_target=objective,
                    objective_sense=direction,
                    with_enzyme_constraints=False,
                    with_thermodynamic_constraints=True,
                    with_loop_constraints=False,
                    min_mdf=min_mdf,
                    solver=Solver(name=solver_name),
                    verbose=True,
                )
            elif self.analysis_type == ThermodynamicAnalysisTypes.BOTTLENECK_ANALYSIS:
                bottlenecks, solution = perform_lp_thermodynamic_bottleneck_analysis(
                    cobrak_model=cobrak_model,
                    with_enzyme_constraints=False,
                    min_mdf=min_mdf,
                    solver=Solver(name=solver_name),
                    verbose=True,
                )
                if solution != {}:
                    solution[ALL_OK_KEY] = True
            self.get_solution_from_thread(solution)
        # except Exception:
        #    self.send_solution.emit(pickle.dumps("ERROR"))
        #    self.finished_computation.emit()

    def set_boxes(self, solution: dict[str, float]):
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
            if DF_VAR_PREFIX + search_key in combined_solution.keys():
                rounded_df = round(
                    combined_solution[DF_VAR_PREFIX + search_key], self.appdata.rounding
                )
                self.appdata.project.df_values[search_key] = rounded_df

        # Write metabolite concentrations
        for metabolite_id in self.metabolite_ids:
            var_id = f"{LNCONC_VAR_PREFIX}{metabolite_id}"
            if var_id in solution.keys():
                rounded_conc = round(exp(solution[var_id]), 9)
                self.appdata.project.conc_values[var_id[len(LNCONC_VAR_PREFIX):]] = rounded_conc

        # Show selected reaction-dependent values
        self.appdata.project.comp_values_type = 0
        self.central_widget.update()

        # Show OptMDF
        console_text = "print('\\n"
        if self.analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
            console_text += f"OptMDF: {solution[MDF_VAR_ID]} kJ/mol"
        elif self.analysis_type == ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA:
            console_text += f"Reached objective value: {solution[OBJECTIVE_VAR_NAME]}"
            console_text += f"\\nReached MDF @ optimum of objective: {solution[MDF_VAR_ID]} kJ/mol"
        elif self.analysis_type == ThermodynamicAnalysisTypes.BOTTLENECK_ANALYSIS:
            combined_bottleneck_sum = 0
            for key in combined_solution.keys():
                if key.startswith("zb_var_"):
                    if combined_solution[key] > 0.1:
                        console_text += f"\\n* {key.replace('zb_var_', '')}"
                        combined_bottleneck_sum += 1
            console_text += f"\\n↳Total number of thermodynamically deactivated bottlenecks to reach minimal MDF: {combined_bottleneck_sum}"
        console_text += "')"
        self.central_widget.kernel_client.execute(console_text)
        self.central_widget.show_bottom_of_console()
