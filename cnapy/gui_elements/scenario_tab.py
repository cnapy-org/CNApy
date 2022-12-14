from enum import IntEnum

from qtpy.QtCore import Signal, Slot, QSignalBlocker, Qt
from qtpy.QtWidgets import QLabel, QCheckBox, QComboBox, QVBoxLayout, QWidget, QTextEdit, QGroupBox

from straindesign.parse_constr import linexpr2dict, linexprdict2str
from cnapy.appdata import AppData
from cnapy.utils import QComplReceivLineEdit

class OptimizationDirection(IntEnum):
    min = 0
    max = 1

class ScenarioTab(QWidget):
    """A widget for display and modification of the global and scenario objective"""

    def __init__(self, appdata: AppData):
        QWidget.__init__(self)
        self.appdata = appdata

        layout = QVBoxLayout()

        group = QGroupBox("Scenario ojective")
        self.objective_group_layout: QVBoxLayout = QVBoxLayout()
        self.use_scenario_objective = QCheckBox("Use scenario objective (overrides the model objective)")
        self.use_scenario_objective.setEnabled(True)
        self.use_scenario_objective.stateChanged.connect(self.use_scenario_objective_changed)
        self.objective_group_layout.addWidget(self.use_scenario_objective)
        self.scenario_objective = QComplReceivLineEdit(self, [])
        self.objective_group_layout.addWidget(self.scenario_objective)
        label = QLabel("Optimization direction")
        self.objective_group_layout.addWidget(label)
        self.scenario_opt_direction = QComboBox()
        self.scenario_opt_direction.insertItems(0, ["minimize", "maximize"])
        self.objective_group_layout.addWidget(self.scenario_opt_direction)
        group.setLayout(self.objective_group_layout)
        layout.addWidget(group)

        label = QLabel("Scenario description")
        layout.addWidget(label)
        self.description = QTextEdit()
        self.description.setPlaceholderText("Enter a description for this scenario")
        layout.addWidget(self.description)
        self.setLayout(layout)

        self.scenario_objective.textCorrect.connect(self.change_scenario_objective_coefficients)
        self.scenario_opt_direction.currentIndexChanged.connect(self.scenario_optimization_direction_changed)
        self.description.textChanged.connect(self.description_changed)

        self.update()

    def update(self):
        self.scenario_objective.set_wordlist(self.appdata.project.cobra_py_model.reactions.list_attr("id"))
        with QSignalBlocker(self.scenario_objective):
            self.scenario_objective.setText(linexprdict2str(self.appdata.project.scen_values.objective_coefficients))
        with QSignalBlocker(self.use_scenario_objective):
            self.use_scenario_objective.setChecked(self.appdata.project.scen_values.use_scenario_objective)
        self.use_scenario_objective.setEnabled(True)

        with QSignalBlocker(self.scenario_opt_direction):
            self.scenario_opt_direction.setCurrentIndex(OptimizationDirection[self.appdata.project.scen_values.objective_direction])
        
        with QSignalBlocker(self.description):
            self.description.setText(self.appdata.project.scen_values.description)

    @Slot(bool)
    def change_scenario_objective_coefficients(self, yes: bool):
        if yes:
            new_objective = linexpr2dict(self.scenario_objective.text(),
                            self.appdata.project.cobra_py_model.reactions.list_attr("id"))
            if new_objective != self.appdata.project.scen_values.objective_coefficients:
                self.appdata.project.scen_values.objective_coefficients = new_objective
                if self.appdata.project.scen_values.use_scenario_objective:
                    self.objectiveSetupChanged.emit()
            self.use_scenario_objective.setEnabled(True)
        else:
            self.use_scenario_objective.setEnabled(False)

    @Slot(int)
    def use_scenario_objective_changed(self, state: int):
        if state == Qt.Checked:
            self.appdata.project.scen_values.use_scenario_objective = True
        elif state == Qt.Unchecked:
            self.appdata.project.scen_values.use_scenario_objective = False
        self.objectiveSetupChanged.emit()

    @Slot(int)
    def scenario_optimization_direction_changed(self, index: int):
        self.appdata.project.scen_values.objective_direction = OptimizationDirection(index).name
        if self.appdata.project.scen_values.use_scenario_objective:
            self.objectiveSetupChanged.emit()

    def description_changed(self):
        self.appdata.project.scen_values.description = self.description.toPlainText()

    objectiveSetupChanged = Signal()
