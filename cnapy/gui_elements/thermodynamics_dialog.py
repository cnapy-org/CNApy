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
    QGridLayout,
    QCompleter,
    QAbstractItemView,
    QListWidget,
    QListWidgetItem
)

from cnapy.appdata import AppData
from cnapy.gui_elements.central_widget import CentralWidget
# from cnapy.gui_elements.solver_buttons import get_solver_buttons

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
        self.setWindowModality(Qt.NonModal)

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
        self._ratio_rows = []

        self.layout = QVBoxLayout()
        match analysis_type:
            case ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
                label = QLabel(
                    "Perform OptMDFpathway. ΔG'° values and metabolite concentration "
                    "ranges have to be given in relevant annotations.\n"
                    "After computing, the reaction(s) currently limiting the MDF (the "
                    "thermodynamic bottleneck, if any) are shown in the console below,\n"
                    "and can be relaxed -- one step at a time, or automatically up to "
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

        # Optional concentration-ratio ranges. These are supplied directly to
        # OptMDFAnalysis(concentration_ratios=...) at the outset, so the ratio
        # constraints are part of the initial optimisation problem rather than
        # an after-the-fact bottleneck relaxation.
        ratio_group = QGroupBox("Metabolite concentration ratio ranges (optional)")
        ratio_layout = QVBoxLayout()
        ratio_layout.addWidget(
            QLabel(
                "Constrain c(metabolite 1) / c(metabolite 2) to a range. "
                "Type the metabolite ID; matching IDs are suggested automatically."
            )
        )

        self._ratio_grid = QGridLayout()
        self._ratio_grid.addWidget(QLabel("Metabolite 1"), 0, 0)
        self._ratio_grid.addWidget(QLabel("Metabolite 2"), 0, 1)
        self._ratio_grid.addWidget(QLabel("Minimum ratio"), 0, 2)
        self._ratio_grid.addWidget(QLabel("Maximum ratio"), 0, 3)
        self._ratio_grid.addWidget(QLabel(""), 0, 4)
        ratio_layout.addLayout(self._ratio_grid)

        ratio_buttons = QHBoxLayout()
        self.button_add_ratio = QPushButton("Add ratio range")
        self.button_add_ratio.clicked.connect(self._add_ratio_row)
        ratio_buttons.addWidget(self.button_add_ratio)
        ratio_buttons.addStretch()
        ratio_layout.addLayout(ratio_buttons)
        ratio_group.setLayout(ratio_layout)
        self.layout.addWidget(ratio_group)
        self._add_ratio_row()

        if analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
            target_mdf_text = QLabel(
                "Target MDF for the optional iterative bottleneck relaxation [in kJ/mol]:"
            )
            self.layout.addWidget(target_mdf_text)
            target_mdf_layout = QHBoxLayout()
            self.target_mdf = QLineEdit()
            self.target_mdf.setText("0.0")
            target_mdf_layout.addWidget(self.target_mdf)
            self.layout.addItem(target_mdf_layout)

        # Current MDF is shown persistently while the dialog remains open.
        self.current_mdf_label = QLabel("Current MDF: — kJ/mol")
        self.current_mdf_label.setStyleSheet("font-weight: bold;")
        self.layout.addWidget(self.current_mdf_label)

        if analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
            # Keep the bottleneck-selection pane visible: the user can choose
            # exactly which member(s) of the current bottleneck are relaxed in the
            # next iteration.
            bottleneck_group = QGroupBox("Bottleneck reactions to relax in the next round")
            bottleneck_layout = QVBoxLayout()
            bottleneck_layout.addWidget(
                QLabel(
                    "Check the reaction(s) to relax. A bottleneck can contain multiple "
                    "reactions, but relaxing all of them is not required."
                )
            )
            self.bottleneck_reaction_list = QListWidget()
            self.bottleneck_reaction_list.setSelectionMode(QAbstractItemView.NoSelection)
            self.bottleneck_reaction_list.itemChanged.connect(
                lambda _item: self._update_iteration_buttons()
            )
            bottleneck_layout.addWidget(self.bottleneck_reaction_list)
            bottleneck_buttons = QHBoxLayout()
            self.button_select_all_bottlenecks = QPushButton("Select all")
            self.button_select_no_bottlenecks = QPushButton("Select none")
            self.button_select_all_bottlenecks.clicked.connect(self._select_all_bottleneck_reactions)
            self.button_select_no_bottlenecks.clicked.connect(self._select_no_bottleneck_reactions)
            bottleneck_buttons.addWidget(self.button_select_all_bottlenecks)
            bottleneck_buttons.addWidget(self.button_select_no_bottlenecks)
            bottleneck_buttons.addStretch()
            bottleneck_layout.addLayout(bottleneck_buttons)
            bottleneck_group.setLayout(bottleneck_layout)
            self.layout.addWidget(bottleneck_group)

        l3 = QHBoxLayout()
        self.button_optmdf = QPushButton("Compute")
        l3.addWidget(self.button_optmdf)
        if analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
            self.button_relax_once = QPushButton("Relax selected reaction(s) and resolve")
            self.button_relax_once.setEnabled(False)
            self.button_relax_to_target = QPushButton("Iterate to target MDF")
            self.button_relax_to_target.setEnabled(False)
            l3.addWidget(self.button_relax_once)
            l3.addWidget(self.button_relax_to_target)
            self.button_relax_once.clicked.connect(self.relax_bottleneck_once)
            self.button_relax_to_target.clicked.connect(self.relax_to_target_mdf)
        self.cancel = QPushButton("Close")
        l3.addWidget(self.cancel)
        self.layout.addItem(l3)

        self.setLayout(self.layout)

        self.cancel.clicked.connect(self.reject)
        self.button_optmdf.clicked.connect(self.compute)
 
    # ------------------------------------------------------------------
    # small helpers
    # ------------------------------------------------------------------

    def _make_metabolite_completer(self) -> QCompleter:
        completer = QCompleter(self.metabolite_ids, self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchStartsWith)
        completer.setCompletionMode(QCompleter.PopupCompletion)
        return completer

    def _add_ratio_row(self) -> None:
        row = len(self._ratio_rows) + 1
        met1 = QLineEdit()
        met2 = QLineEdit()
        met1.setPlaceholderText("metabolite ID")
        met2.setPlaceholderText("metabolite ID")
        met1.setCompleter(self._make_metabolite_completer())
        met2.setCompleter(self._make_metabolite_completer())

        ratio_min = QLineEdit()
        ratio_min.setPlaceholderText("> 0")
        ratio_max = QLineEdit()
        ratio_max.setPlaceholderText("> 0")

        remove = QPushButton("Remove")
        remove.clicked.connect(lambda _checked=False, widgets=(met1, met2, ratio_min, ratio_max, remove): self._remove_ratio_row(widgets))

        self._ratio_grid.addWidget(met1, row, 0)
        self._ratio_grid.addWidget(met2, row, 1)
        self._ratio_grid.addWidget(ratio_min, row, 2)
        self._ratio_grid.addWidget(ratio_max, row, 3)
        self._ratio_grid.addWidget(remove, row, 4)
        self._ratio_rows.append((met1, met2, ratio_min, ratio_max, remove))

    def _remove_ratio_row(self, widgets) -> None:
        try:
            idx = self._ratio_rows.index(widgets)
        except ValueError:
            return
        for widget in widgets:
            self._ratio_grid.removeWidget(widget)
            widget.deleteLater()
        self._ratio_rows.pop(idx)
        # Rebuild row positions so rows stay compact.
        for row, row_widgets in enumerate(self._ratio_rows, start=1):
            for col, widget in enumerate(row_widgets):
                self._ratio_grid.addWidget(widget, row, col)

    def _get_concentration_ratios(self):
        ratios = []
        for row_number, (met1, met2, ratio_min, ratio_max, _remove) in enumerate(self._ratio_rows, start=1):
            mi = met1.text().strip()
            mj = met2.text().strip()
            lo_text = ratio_min.text().strip()
            hi_text = ratio_max.text().strip()
            if not mi and not mj and not lo_text and not hi_text:
                continue
            if mi not in self.metabolite_ids or mj not in self.metabolite_ids:
                raise ValueError(
                    f"Ratio row {row_number}: both metabolite IDs must be selected "
                    "from the model's metabolites."
                )
            if mi == mj:
                raise ValueError(f"Ratio row {row_number}: choose two different metabolites.")
            try:
                lo = float(lo_text)
                hi = float(hi_text)
            except ValueError:
                raise ValueError(f"Ratio row {row_number}: minimum and maximum ratios must be valid numbers.") from None
            if lo <= 0 or hi <= 0:
                raise ValueError(f"Ratio row {row_number}: ratio bounds must be positive.")
            if lo > hi:
                raise ValueError(f"Ratio row {row_number}: minimum ratio cannot exceed maximum ratio.")
            ratios.append((mi, mj, lo, hi))
        return ratios

    def _selected_bottleneck_reactions(self):
        return [
            self.bottleneck_reaction_list.item(i).text()
            for i in range(self.bottleneck_reaction_list.count())
            if self.bottleneck_reaction_list.item(i).checkState() == Qt.Checked
        ]

    def _set_bottleneck_reaction_choices(self, reactions) -> None:
        old_checked = set(self._selected_bottleneck_reactions())
        reactions = list(reactions or [])
        self.bottleneck_reaction_list.blockSignals(True)
        try:
            self.bottleneck_reaction_list.clear()
            preserve = bool(old_checked.intersection(reactions))
            for rid in reactions:
                item = QListWidgetItem(rid)
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked if (rid in old_checked if preserve else True) else Qt.Unchecked)
                self.bottleneck_reaction_list.addItem(item)
        finally:
            self.bottleneck_reaction_list.blockSignals(False)

    @Slot()
    def _select_all_bottleneck_reactions(self):
        for i in range(self.bottleneck_reaction_list.count()):
            self.bottleneck_reaction_list.item(i).setCheckState(Qt.Checked)
        self._update_iteration_buttons()

    @Slot()
    def _select_no_bottleneck_reactions(self):
        for i in range(self.bottleneck_reaction_list.count()):
            self.bottleneck_reaction_list.item(i).setCheckState(Qt.Unchecked)
        self._update_iteration_buttons()

    def _update_iteration_buttons(self) -> None:
        has_bottleneck = (
            self.analysis is not None
            and self.current_result is not None
            and self.current_result.status == "optimal"
            and bool(self.current_result.bottleneck_reactions)
        )
        has_selection = bool(self._selected_bottleneck_reactions())
        self.button_relax_once.setEnabled(has_bottleneck and has_selection)
        self.button_relax_to_target.setEnabled(has_bottleneck and has_selection)

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

    # def _apply_selected_solver(self, model: cobra.Model) -> None:
    #     solver_name = self.solver_buttons["group"].checkedButton().property("cobrak_name")
    #     if not solver_name:
    #         return
    #     try:
    #         model.solver = solver_name.lower()
    #     except Exception:
    #         QMessageBox.warning(
    #             self,
    #             "Solver unavailable",
    #             f"Could not switch to solver '{solver_name}'; using the model's "
    #             "current default solver instead.",
    #         )

    # ------------------------------------------------------------------
    # computing / displaying a result
    # ------------------------------------------------------------------

    def process_solution(self, result: OptMDFResult) -> None:
        if result.status != "optimal":
            self.current_mdf_label.setText("Current MDF: — kJ/mol")
            warning_title, warning_text = self._status_message(result.status)
            QMessageBox.warning(self, warning_title, warning_text)
        else:
            self.set_boxes(result)
            self.current_mdf_label.setText(f"Current MDF: {result.mdf:.6g} kJ/mol")
            if self.analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
                self._set_bottleneck_reaction_choices(result.bottleneck_reactions)
                self._update_iteration_buttons()

        self.setCursor(Qt.ArrowCursor)
        # Deliberately not calling self.accept()/self.reject() here: the
        # dialog stays open so the bottleneck-relaxation buttons above stay
        # usable. The user closes the dialog explicitly via "Close".

    @Slot()
    def compute(self):
        self.setCursor(Qt.BusyCursor)

        self.analysis = None
        self.current_result = None
        self._relaxed_so_far = set()
        self.current_mdf_label.setText("Current MDF: — kJ/mol")
        if self.analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
            self._set_bottleneck_reaction_choices([])
            self._update_iteration_buttons()

        # Decouple models ("with" and "deepcopy" do not work) so that no
        # scenario bounds spill into the original model.
        modelstr = cobra.io.to_json(self.appdata.project.cobra_py_model)
        model = cobra.io.from_json(modelstr)
        self.appdata.project.load_scenario_into_model(model)

        # self._apply_selected_solver(model)

        try:
            min_default_conc = float(self.min_default_conc.text())
            max_default_conc = float(self.max_default_conc.text())
            if min_default_conc <= 0 or max_default_conc <= 0 or min_default_conc > max_default_conc:
                raise ValueError
            concentration_ratios = self._get_concentration_ratios()
        except ValueError as exc:
            message = str(exc) or "Default Cmin/Cmax must be valid positive numbers with Cmin <= Cmax."
            QMessageBox.warning(
                self,
                "Invalid concentration / ratio settings",
                message,
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

        try:
            concentration_ratios = self._get_concentration_ratios()
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid concentration ratio", str(exc))
            self.setCursor(Qt.ArrowCursor)
            return

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
                concentration_ratios=concentration_ratios,
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
            self.analysis.shadow_prices()
            if self.analysis_type == ThermodynamicAnalysisTypes.OPTMDFPATHWAY:
                result.bottleneck_reactions = self.analysis.find_bottleneck()
        self.current_result = result

        self.process_solution(result)

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

        selected = self._selected_bottleneck_reactions()
        if not selected:
            QMessageBox.information(
                self,
                "No reaction selected",
                "Select at least one bottleneck reaction to relax.",
            )
            return

        self.setCursor(Qt.BusyCursor)
        self.analysis.relax(selected)
        self._relaxed_so_far.update(selected)

        result = self._solve()
        if result.status == "optimal":
            self.analysis.shadow_prices()
            result.bottleneck_reactions = self.analysis.find_bottleneck()
        self.current_result = result

        self.process_solution(result)

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
            selected = self._selected_bottleneck_reactions()
            if not selected:
                QMessageBox.information(
                    self,
                    "Select bottleneck reaction(s)",
                    "Iteration to the target stopped because no reaction is selected. "
                    "Choose one or more reactions in the bottleneck list and run "
                    "the operation again.",
                )
                break
            self.analysis.relax(selected)
            self._relaxed_so_far.update(selected)
            result = self._solve()
            if result.status != "optimal":
                break
            result.bottleneck_reactions = self.analysis.find_bottleneck()
            self._set_bottleneck_reaction_choices(result.bottleneck_reactions)
            n += 1
            # Do not silently carry the previous selection into a newly found
            # bottleneck; the user should explicitly choose the next relaxation.
            if result.bottleneck_reactions and result.mdf is not None and result.mdf < target_mdf:
                break
        self.current_result = result

        self.process_solution(result)

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
                    "Use 'Relax bottleneck and resolve' or 'Iterate to target MDF' "
                    "to relax them and see how the MDF improves."
                )
            else:
                lines.append(
                    "No thermodynamic bottleneck currently limits the MDF further."
                )

            if self._relaxed_so_far:
                lines.append(
                    f"Reaction(s) relaxed so far this session: {sorted(self._relaxed_so_far)}"
                )

        console_text = "\n".join(lines)
        self.central_widget.console._append_plain_text(console_text, before_prompt=True)
        self.central_widget.show_bottom_of_console()
