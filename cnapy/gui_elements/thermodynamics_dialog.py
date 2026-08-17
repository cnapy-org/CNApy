"""The CNApy OptMDFpathway dialog

This dialog now uses ``OptMDFAnalysis`` from ``optmdfpathway.py`` directly on
the project's cobrapy model (ΔG'° / Cmin / Cmax are read straight from the
model's own reaction/metabolite annotations), instead of converting through
cobrak. This has two consequences for the dialog compared to the previous
cobrak-based version:

* OptMDFpathway and thermodynamic bottleneck analysis are no longer two
  separate computations that each rebuild the whole optimization problem
  from scratch. Given one ``OptMDFAnalysis`` instance, finding the current
  thermodynamic bottleneck (``find_bottleneck()``) is just another cheap
  query against the already-solved problem, so both analyses are now part
  of the single "OptMDFpathway" analysis type below (the old
  ``BOTTLENECK_ANALYSIS`` type has been folded into it). Any other CNApy
  code that used to construct this dialog with
  ``ThermodynamicAnalysisTypes.BOTTLENECK_ANALYSIS`` should be updated to
  use ``ThermodynamicAnalysisTypes.OPTMDFPATHWAY`` instead.
* Because the ``OptMDFAnalysis`` object is kept alive for as long as the
  dialog stays open (it is no longer auto-closed after a computation), the
  user can now iteratively relax the reaction(s) currently limiting the MDF
  and resolve -- one step at a time, or automatically down to a target MDF
  -- watching how the optimum shifts as bottlenecks are removed. This
  mirrors the iterative bottleneck-relaxation workflow demonstrated in
  ``optmdfpathway.py``'s own ``__main__`` section (``OptMDFAnalysis.step()``
  / ``.run()``).
"""
from enum import Enum
from typing import Optional, Set

import cobra
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

from cnapy.optmdfpathway import OptMDFAnalysis, OptMDFResult


class ThermodynamicAnalysisTypes(Enum):
    # OptMDFpathway now always also makes the current thermodynamic
    # bottleneck (if any) available and lets the user relax it iteratively
    # -- what used to be the separate BOTTLENECK_ANALYSIS type is simply
    # part of this workflow now (see the module docstring above).
    OPTMDFPATHWAY = 1
    THERMODYNAMIC_FBA = 2


class ThermodynamicDialog(QDialog):
    """A dialog to perform several thermodynamic methods."""

    #: optlang solver-status -> (message box title, message box text)
    _STATUS_MESSAGES = {
        "infeasible": (
            "Problem infeasible",
            "The problem appears to be infeasible, i.e. the constraints make a solution impossible.",
        ),
        "unbounded": (
            "Problem unbounded",
            "The problem appears to be unbounded, i.e. there is no constraint limiting the objective values.",
        ),
        "infeasible_or_unbounded": (
            "Problem infeasible or unbounded",
            "The solver could not tell infeasibility and unboundedness apart. Try tightening the model's bounds or use another solver.",
        ),
        "time_limit": (
            "Time limit",
            "Solver's time limit hit. Please change solver or problem complexity.",
        ),
        "iteration_limit": (
            "Iterations limit",
            "Solver's iterations limit hit. Please change solver or problem complexity.",
        ),
        "numeric": (
            "Numerical problem",
            "The solver ran into numerical difficulties. Try another solver.",
        ),
    }

    def __init__(
        self, appdata: AppData, central_widget: CentralWidget, analysis_type: ThermodynamicAnalysisTypes
    ) -> None:
        QDialog.__init__(self)

        if analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
            window_title = "Perform OptMDFpathway (incl. bottleneck analysis)"
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

        # Set up once "Compute" has succeeded, and kept alive across button
        # clicks so relaxing a bottleneck and resolving doesn't need to
        # rebuild the model / FVA / MILP from scratch every time.
        self.analysis: Optional[OptMDFAnalysis] = None
        self.current_result: Optional[OptMDFResult] = None
        self._solve = None  # bound to analysis.solve or analysis.solve_fba once built
        self._relaxed_so_far: Set[str] = set()

        self.layout = QVBoxLayout()
        match analysis_type:
            case ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
                label = QLabel(
                    "Perform OptMDFpathway. ΔG'° values and metabolite concentration "
                    "ranges have to be given in relevant annotations.\n"
                    "After computing, the reaction(s) currently limiting the MDF (the "
                    "thermodynamic bottleneck, if any) are shown in the console below, "
                    "and can be relaxed -- one step at a time, or automatically down to "
                    "a target MDF -- to see how the optimum shifts as bottlenecks are "
                    "removed."
                )
            case ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA:
                label = QLabel(
                    "Perform thermodynamic Flux Balance Analysis. Based on OptMDFpathway, you can perform an FBA at an OptMDF greater than the given value. "
                    "\nE.g., if the OptMDF is greater than 0 kJ/mol, you perform an FBA with enforced thermodynamic feasibility."
                    "\nFor this analysis, ΔG'° values and metabolite concentration "
                    "ranges have to be given in relevant annotations.\n"
                    "As with OptMDFpathway, any reaction(s) currently limiting the "
                    "reached MDF can afterwards be relaxed iteratively as well."
                )
        self.layout.addWidget(label)

        if analysis_type == ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA:
            lineedit_text = QLabel("Minimal MDF to enforce [in kJ/mol]:")

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

        target_mdf_text = QLabel(
            "Target MDF for the optional iterative bottleneck relaxation [in kJ/mol]:"
        )
        self.layout.addWidget(target_mdf_text)
        target_mdf_layout = QHBoxLayout()
        self.target_mdf = QLineEdit()
        self.target_mdf.setText("0.0")
        target_mdf_layout.addWidget(self.target_mdf)
        self.layout.addItem(target_mdf_layout)

        solver_group = QGroupBox("Solver:")
        solver_buttons_layout, self.solver_buttons = get_solver_buttons(appdata)
        solver_group.setLayout(solver_buttons_layout)
        self.layout.addWidget(solver_group)

        l3 = QHBoxLayout()
        self.button_optmdf = QPushButton("Compute")
        self.button_relax_once = QPushButton("Relax bottleneck and resolve")
        self.button_relax_once.setEnabled(False)
        self.button_relax_to_target = QPushButton("Iterate to target MDF")
        self.button_relax_to_target.setEnabled(False)
        self.cancel = QPushButton("Close")
        l3.addWidget(self.button_optmdf)
        l3.addWidget(self.button_relax_once)
        l3.addWidget(self.button_relax_to_target)
        l3.addWidget(self.cancel)
        self.layout.addItem(l3)

        self.setLayout(self.layout)

        # Connecting the signals
        self.cancel.clicked.connect(self.reject)
        self.button_optmdf.clicked.connect(self.compute_optmdf)
        self.button_relax_once.clicked.connect(self.relax_bottleneck_once)
        self.button_relax_to_target.clicked.connect(self.relax_to_target_mdf)

    # ------------------------------------------------------------------
    # small helpers
    # ------------------------------------------------------------------

    def _update_iteration_buttons(self) -> None:
        has_bottleneck = (
            self.analysis is not None
            and self.current_result is not None
            and self.current_result.status == "optimal"
            and bool(self.current_result.bottleneck_reactions)
        )
        self.button_relax_once.setEnabled(has_bottleneck)
        self.button_relax_to_target.setEnabled(has_bottleneck)

    def _status_message(self, status: str):
        return self._STATUS_MESSAGES.get(
            status,
            (
                "Solver problem",
                f"The solution process did not reach an optimal solution (solver status: '{status}').",
            ),
        )

    def _build_scenario_constraints(self):
        # ({reaction_id: coefficient}, constraint_type, rhs) triples -- this
        # is exactly what OptMDFAnalysis(scenarios=...) expects, so unlike
        # before, no separate constraint dataclass (ExtraLinearConstraint) is
        # needed at all.
        scenario_constraints = []
        for constraint in self.appdata.project.scen_values.constraints:
            # e.g., [({'EDD': 1.0}, '>=', 1.0)]
            stoichiometry = {key: value for key, value in constraint[0].items()}
            direction = constraint[1]
            rhs = constraint[2]
            if direction not in ("=", "<=", ">="):
                direction = "="
            scenario_constraints.append((stoichiometry, direction, float(rhs)))
        return scenario_constraints

    def _apply_selected_solver(self, model: cobra.Model) -> None:
        solver_name = self.solver_buttons["group"].checkedButton().property("cobrak_name")
        if not solver_name:
            return
        try:
            model.solver = solver_name.lower()
        except Exception:
            QMessageBox.warning(
                self,
                "Solver unavailable",
                f"Could not switch to solver '{solver_name}'; using the model's "
                "current default solver instead.",
            )

    # ------------------------------------------------------------------
    # computing / displaying a result
    # ------------------------------------------------------------------

    def get_solution_from_thread(self, result: OptMDFResult) -> None:
        if result.status != "optimal":
            warning_title, warning_text = self._status_message(result.status)
            QMessageBox.warning(self, warning_title, warning_text)
        else:
            self.set_boxes(result)

        self.setCursor(Qt.ArrowCursor)
        self._update_iteration_buttons()
        # Deliberately not calling self.accept()/self.reject() here: the
        # dialog stays open so the bottleneck-relaxation buttons above stay
        # usable. The user closes the dialog explicitly via "Close".

    @Slot()
    def compute_optmdf(self):
        self.setCursor(Qt.BusyCursor)

        self.analysis = None
        self.current_result = None
        self._relaxed_so_far = set()
        self._update_iteration_buttons()

        # Decouple models ("with" and "deepcopy" do not work) so that no
        # scenario bounds spill into the original model.
        modelstr = cobra.io.to_json(self.appdata.project.cobra_py_model)
        model = cobra.io.from_json(modelstr)
        self.appdata.project.load_scenario_into_model(model)

        self._apply_selected_solver(model)

        try:
            min_default_conc = float(self.min_default_conc.text())
            max_default_conc = float(self.max_default_conc.text())
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid default concentration",
                "Default Cmin/Cmax must be valid numbers (such as, e.g., 1e-6).",
            )
            self.setCursor(Qt.ArrowCursor)
            return

        if self.analysis_type == ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA:
            try:
                min_mdf = float(self.min_mdf.text())
            except ValueError:
                QMessageBox.warning(
                    self,
                    "Invalid minimal OptMDF",
                    "The given minimal OptMDF could not be converted into a valid number "
                    "(such as, e.g., 1.231). Aborting calculation...",
                )
                self.setCursor(Qt.ArrowCursor)
                return
            B_bounds = (min_mdf, 1e4)
        else:
            B_bounds = (-1e4, 1e4)

        if not any(rxn.annotation.get("dG0") is not None for rxn in model.reactions):
            QMessageBox.warning(
                self,
                "No ΔG'° set",
                "To run a thermodynamic calculation, your model needs at least one "
                "reaction with a ΔG'° (annotation 'dG0'). Check out CNApy's "
                "documentation for more",
            )
            self.setCursor(Qt.ArrowCursor)
            return

        try:
            self.analysis = OptMDFAnalysis(
                model,
                Cmin=min_default_conc,
                Cmax=max_default_conc,
                scenarios=self._build_scenario_constraints(),
                B_bounds=B_bounds,
                verbose=True,
            )
        except Exception as e:
            QMessageBox.warning(
                self,
                "Setup error",
                f"Could not set up the thermodynamic analysis:\n{e}",
            )
            self.analysis = None
            self.setCursor(Qt.ArrowCursor)
            self._update_iteration_buttons()
            return

        # OPTMDFPATHWAY maximises the MDF itself (analysis.solve());
        # THERMODYNAMIC_FBA optimises the model's own objective subject to
        # the enforced minimal MDF from B_bounds (analysis.solve_fba()). In
        # both cases the same analysis object is reused for every later
        # relax-and-resolve step below.
        self._solve = (
            self.analysis.solve_fba
            if self.analysis_type == ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA
            else self.analysis.solve
        )

        result = self._solve()
        if result.status == "optimal":
            result.bottleneck_reactions = self.analysis.find_bottleneck()
        self.current_result = result

        self.get_solution_from_thread(result)

    # ------------------------------------------------------------------
    # iterative bottleneck relaxation (see optmdfpathway.py's __main__ demo,
    # i.e. the OptMDFAnalysis.step()/.run() pattern: find the current
    # bottleneck, relax() exactly it, resolve, repeat)
    # ------------------------------------------------------------------

    @Slot()
    def relax_bottleneck_once(self):
        if self.analysis is None or self.current_result is None:
            return
        bottleneck = self.current_result.bottleneck_reactions
        if not bottleneck:
            QMessageBox.information(
                self,
                "No bottleneck",
                "The current MDF is not limited by any reaction's thermodynamics; "
                "there is nothing left to relax.",
            )
            return

        self.setCursor(Qt.BusyCursor)
        self.analysis.relax(bottleneck)
        self._relaxed_so_far.update(bottleneck)

        result = self._solve()
        if result.status == "optimal":
            result.bottleneck_reactions = self.analysis.find_bottleneck()
        self.current_result = result

        self.get_solution_from_thread(result)

    @Slot()
    def relax_to_target_mdf(self):
        if self.analysis is None or self.current_result is None:
            return
        try:
            target_mdf = float(self.target_mdf.text())
        except ValueError:
            QMessageBox.warning(
                self,
                "Invalid target MDF",
                "The given target MDF could not be converted into a valid number "
                "(such as, e.g., 0.0).",
            )
            return

        self.setCursor(Qt.BusyCursor)
        result = self.current_result
        max_iterations = 50  # safety cap against pathological relax loops
        n = 0
        while n < max_iterations:
            bottleneck = result.bottleneck_reactions
            if not bottleneck or (result.mdf is not None and result.mdf >= target_mdf):
                break
            self.analysis.relax(bottleneck)
            self._relaxed_so_far.update(bottleneck)
            result = self._solve()
            if result.status != "optimal":
                break
            result.bottleneck_reactions = self.analysis.find_bottleneck()
            n += 1
        self.current_result = result

        self.get_solution_from_thread(result)

    # ------------------------------------------------------------------
    # writing a result into the CNApy project / console
    # ------------------------------------------------------------------

    def set_boxes(self, result: OptMDFResult):
        # write flux and driving-force results into comp_values / df_values
        for search_key in self.reac_ids:
            if search_key in result.fluxes:
                flux = float(result.fluxes[search_key])
                self.appdata.project.comp_values[search_key] = (flux, flux)
            if search_key in result.driving_forces:
                rounded_df = round(result.driving_forces[search_key], self.appdata.rounding)
                self.appdata.project.df_values[search_key] = rounded_df

        # write metabolite concentrations (OptMDFResult already reports
        # these as actual concentrations in M, not log-concentrations)
        for metabolite_id in self.metabolite_ids:
            if metabolite_id in result.concentrations:
                rounded_conc = round(result.concentrations[metabolite_id], 9)
                self.appdata.project.conc_values[metabolite_id] = rounded_conc

        # Show selected reaction-dependent values
        self.appdata.project.comp_values_type = 0
        self.central_widget.update()

        # Show OptMDF / objective, and the current thermodynamic bottleneck
        lines = []
        if self.analysis_type == ThermodynamicAnalysisTypes.THERMODYNAMIC_FBA:
            lines.append(f"Reached objective value: {result.objective_value}")
            lines.append(f"Reached MDF @ optimum of objective: {result.mdf} kJ/mol")
        else:
            lines.append(f"OptMDF: {result.mdf} kJ/mol")

        if result.bottleneck_reactions:
            lines.append("Thermodynamic bottleneck reaction(s) currently limiting the MDF:")
            for rid in result.bottleneck_reactions:
                lines.append(f"* {rid}")
            lines.append(
                "\u21b3Use 'Relax bottleneck and resolve' or 'Iterate to target MDF' "
                "to relax them and see how the MDF improves."
            )
        else:
            lines.append(
                "\u21b3No thermodynamic bottleneck currently limits the MDF further."
            )

        if self._relaxed_so_far:
            lines.append(
                f"Reaction(s) relaxed so far this session: {sorted(self._relaxed_so_far)}"
            )

        console_text = "print('\\n" + "\\n".join(lines) + "')"
        self.central_widget.kernel_client.execute(console_text)
        self.central_widget.show_bottom_of_console()
