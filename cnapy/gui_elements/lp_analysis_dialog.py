"""The CNApy LP analysis dialog"""
from cobrak.constants import OBJECTIVE_VAR_NAME
from cobrak.printing import print_dict
from qtpy.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QStackedWidget,
    QVBoxLayout,
    QGroupBox,
    QWidget,
    QMessageBox,
)
from straindesign import linexpr2dict

from cnapy.appdata import AppData
from cnapy.core_gui import get_opt_direction_combo_box
from cnapy.gui_elements.central_widget import CentralWidget
from cnapy.gui_elements.model_info import OptimizationDirection
from cnapy.gui_elements.solver_buttons import get_solver_buttons
from cnapy.run_analyses import run_lp_optimization, run_lp_variability_analysis, run_lp_bottleneck_analysis
from cnapy.utils import QComplReceivLineEdit


class LpAnalysisDialog(QDialog):
    """A dialog to perform linear constraint-based methods."""
    def __init__(
        self, appdata: AppData, central_widget: CentralWidget,
    ) -> None:
        QDialog.__init__(self)
        self.setWindowTitle("Perform LP analysis")

        self.appdata = appdata
        self.central_widget = central_widget
        self.model_reac_ids = self.appdata.project.cobra_py_model.reactions.list_attr("id")

        layout = QVBoxLayout()

        analysis_radioboxes = QGroupBox("Analysis form:") # This is the parent container
        self.lp_optimization = QRadioButton("LP optimization")
        self.lp_optimization.toggled.connect(self.handle_analysis_lp_optimization)
        self.lp_variability = QRadioButton("LP variability")
        self.lp_variability.toggled.connect(self.handle_analysis_lp_variability)
        self.lp_bottleneck_analysis = QRadioButton("LP bottleneck analysis")
        self.lp_bottleneck_analysis.toggled.connect(self.handle_analysis_lp_bottleneck)
        self.lp_bottleneck_analysis.setEnabled(False)
        layout_analysis_radioboxes = QHBoxLayout()
        layout_analysis_radioboxes.addWidget(self.lp_optimization)
        layout_analysis_radioboxes.addWidget(self.lp_variability)
        layout_analysis_radioboxes.addWidget(self.lp_bottleneck_analysis)
        analysis_radioboxes.setLayout(layout_analysis_radioboxes) # All buttons in this box form Group 1
        layout.addWidget(analysis_radioboxes)


        self.objective_radioboxes = QGroupBox("Objective:")
        self.objective_stack = QStackedWidget()

        radio_container = QWidget()
        radio_container.setContentsMargins(0, 0, 0, 0)
        vertical_layout = QVBoxLayout(radio_container)
        vertical_layout.setContentsMargins(0, 0, 0, 0)
        radio_layout = QHBoxLayout()
        radio_layout.setContentsMargins(0, 0, 0, 0)

        self.set_model_objective = QRadioButton("Set objective:")
        self.set_objective = QComplReceivLineEdit(
            self,
            self.model_reac_ids,
            is_in_dark_mode=self.appdata.is_in_dark_mode,
        )
        self.set_objective.setText(self.central_widget.model_info.global_objective.text())
        self.set_objective.textCorrect.connect(self.validate_set_objective)
        self.set_mdf_objective = QRadioButton("MDF")
        self.set_mdf_objective.setEnabled(False)
        radio_layout.addWidget(self.set_model_objective)
        radio_layout.addWidget(self.set_objective)
        radio_layout.addWidget(self.set_mdf_objective)
        vertical_layout.addLayout(radio_layout)
        direction_layout = QHBoxLayout()
        direction_layout.setContentsMargins(0, 0, 0, 0)
        opt_direction_text = QLabel("Direction:")
        self.opt_direction: QComboBox = get_opt_direction_combo_box(
            set_start_value=OptimizationDirection[self.appdata.project.cobra_py_model.objective_direction].value,
        )
        direction_layout.addWidget(opt_direction_text)
        direction_layout.addWidget(self.opt_direction)
        vertical_layout.addLayout(direction_layout)
        self.objective_stack.addWidget(radio_container) # Stack Index 0

        label_container = QWidget()
        label_layout = QHBoxLayout(label_container)
        label_layout.setContentsMargins(0, 0, 0, 0)
        self.no_objective_applicable = QLabel("(not applicable with selected analysis form)")
        label_layout.addWidget(self.no_objective_applicable)
        self.objective_stack.addWidget(label_container) # Stack index 1

        objective_group_layout = QVBoxLayout()
        objective_group_layout.addWidget(self.objective_stack)
        self.objective_radioboxes.setLayout(objective_group_layout)
        layout.addWidget(self.objective_radioboxes)


        constraints_group = QGroupBox("Extra constraints:")
        constraints_layout = QVBoxLayout()

        self.with_enzyme_constraints = QCheckBox("With (non-stoichiometric) enzyme constraints")
        self.with_enzyme_constraints.setChecked(False)
        self.with_enzyme_constraints.toggled.connect(self.handle_enzyme_constraints)
        constraints_layout.addWidget(self.with_enzyme_constraints)

        self.protein_pool_layout_container = QWidget()
        protein_pool_layout = QHBoxLayout(self.protein_pool_layout_container)
        protein_pool_layout.setContentsMargins(0, 0, 0, 0)
        text_protein_pool = QLabel("Protein pool [in g/gDW]:")
        self.protein_pool = QLineEdit()
        self.protein_pool.setText("0.25")
        protein_pool_layout.addWidget(text_protein_pool)
        protein_pool_layout.addWidget(self.protein_pool)
        self.protein_pool_layout_container.setEnabled(False)
        constraints_layout.addWidget(self.protein_pool_layout_container)

        self.with_thermodynamic_constraints = QCheckBox("With thermodynamic constraints")
        self.with_thermodynamic_constraints.setChecked(False)
        self.with_thermodynamic_constraints.toggled.connect(self.handle_thermodynamic_constraints)
        constraints_layout.addWidget(self.with_thermodynamic_constraints)

        self.default_concs_layout_container = QWidget()
        default_concs_layout = QHBoxLayout(self.default_concs_layout_container)
        default_concs_layout.setContentsMargins(0, 0, 0, 0)
        text_min_default_conc = QLabel("Default Cmin [in M]:")
        self.min_default_conc = QLineEdit()
        self.min_default_conc.setText("1e-6")
        self.min_default_conc.setMaximumWidth(50)
        default_concs_layout.addWidget(text_min_default_conc)
        default_concs_layout.addWidget(self.min_default_conc)
        text_max_default_conc = QLabel(" Default Cmax [in M]:")
        self.max_default_conc = QLineEdit()
        self.max_default_conc.setText("0.2")
        self.max_default_conc.setMaximumWidth(50)
        default_concs_layout.addWidget(text_max_default_conc)
        default_concs_layout.addWidget(self.max_default_conc)
        text_min_mdf = QLabel(" Minimal MDF [in kJ/mol]:")
        self.min_mdf = QLineEdit()
        self.min_mdf.setText("0.1")
        self.min_mdf.setMaximumWidth(50)
        default_concs_layout.addWidget(text_min_mdf)
        default_concs_layout.addWidget(self.min_mdf)
        constraints_layout.addWidget(self.default_concs_layout_container)
        self.default_concs_layout_container.setEnabled(False)

        constraints_group.setLayout(constraints_layout)
        layout.addWidget(constraints_group)

        
        solver_group = QGroupBox("Solver:")
        solver_buttons_layout, self.solver_buttons = get_solver_buttons(appdata, is_vertical=False, for_straindesign=False)
        solver_group.setLayout(solver_buttons_layout)
        layout.addWidget(solver_group)

        self.run_analysis = QPushButton("Run analysis")
        self.run_analysis.clicked.connect(self.handle_run_analysis)
        self.validate_set_objective()
        layout.addWidget(self.run_analysis)

        self.lp_optimization.setChecked(True)
        self.set_model_objective.setChecked(True)

        self.setLayout(layout)
    
    def _hide_objective_radioboxes(self, to_hide: bool) -> None:
        # Show the "not applicable" label (index 1) or radio buttons (0)
        self.objective_stack.setCurrentIndex(int(to_hide))
        self.validate_set_objective()
    
    def validate_set_objective(self) -> None:
        if self.lp_optimization.isChecked():
            self.run_analysis.setEnabled(self.set_objective.is_valid)
            self.run_analysis.setText(
                "Run analysis" if self.set_objective.is_valid else
                "(cannot run analysis: set objective is invalid, check expression)"
            )
        else:
            self.run_analysis.setEnabled(True)
            self.run_analysis.setText("Run analysis")

    def handle_thermodynamic_constraints(self, is_checked: bool) -> None:
        self.default_concs_layout_container.setEnabled(is_checked)
        self.set_mdf_objective.setEnabled(is_checked)
        self.lp_bottleneck_analysis.setEnabled(is_checked)
        if not is_checked:
            if self.set_mdf_objective.isChecked():
                self.set_model_objective.setChecked(True)
            if self.lp_bottleneck_analysis.isChecked():
                self.lp_optimization.setChecked(True)

    def handle_enzyme_constraints(self, is_checked: bool) -> None:
        self.protein_pool_layout_container.setEnabled(is_checked)
    
    def handle_analysis_lp_optimization(self, is_checked: bool) -> None:
        if not is_checked:
            return
        self._hide_objective_radioboxes(False)

    def handle_analysis_lp_variability(self, is_checked: bool) -> None:
        if not is_checked:
            return
        self._hide_objective_radioboxes(True)

    def handle_analysis_lp_bottleneck(self, is_checked: bool) -> None:
        if not is_checked:
            return
        self._hide_objective_radioboxes(True)
    
    def handle_run_analysis(self) -> None:
        if self.lp_optimization.isChecked():
            opt_result: tuple[str, dict[str, float]] = run_lp_optimization(
                cobrapy_model=self.appdata.project.cobra_py_model,
                scen_values=self.appdata.project.scen_values,
                solver_name=self.solver_buttons["group"].checkedButton().property("cobrak_name"),
                with_enzyme_constraints=self.with_enzyme_constraints.isChecked(),
                with_thermodynamic_constraints=self.with_thermodynamic_constraints.isChecked(),
                min_mdf=float(self.min_mdf.text()),
                min_default_conc=float(self.min_default_conc.text()),
                max_default_conc=float(self.max_default_conc.text()),
                objective_overwrite=linexpr2dict(self.set_objective.text(), self.model_reac_ids),
                direction_overwrite=-1 if self.opt_direction.currentIndex() == 0 else +1,
            )
            error_message, opt_solution = opt_result
            if error_message:
                QMessageBox(
                    "LP optimization error",
                    error_message,
                )
                return
            for reac_id in self.model_reac_ids:
                self.appdata.project.comp_values[reac_id] = (
                    opt_solution[reac_id], opt_solution[reac_id],
                )
            self.appdata.project.comp_values_type = 0
            self.central_widget.update()
        elif self.lp_variability.isChecked():
            var_result = run_lp_variability_analysis(
                cobrapy_model=self.appdata.project.cobra_py_model,
                scen_values=self.appdata.project.scen_values,
                solver_name=self.solver_buttons["group"].checkedButton().property("cobrak_name"),
                with_enzyme_constraints=self.with_enzyme_constraints.isChecked(),
                with_thermodynamic_constraints=self.with_thermodynamic_constraints.isChecked(),
                calculate_reacs=True,
                calculate_concs=False,
                min_mdf=float(self.min_mdf.text()),
                min_default_conc=float(self.min_default_conc.text()),
                max_default_conc=float(self.max_default_conc.text()),
            )
            print(var_result)
        elif self.lp_bottleneck_analysis.isChecked():
            bottleneck_result = run_lp_bottleneck_analysis(
                cobrapy_model=self.appdata.project.cobra_py_model,
                scen_values=self.appdata.project.scen_values,
                solver_name=self.solver_buttons["group"].checkedButton().property("cobrak_name"),
                with_enzyme_constraints=self.with_enzyme_constraints.isChecked(),
                min_mdf=float(self.min_mdf.text()),
                min_default_conc=float(self.min_default_conc.text()),
                max_default_conc=float(self.max_default_conc.text()),
            )
            print(bottleneck_result)
