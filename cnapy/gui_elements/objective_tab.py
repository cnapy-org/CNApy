from enum import IntEnum

from qtpy.QtCore import Signal, Slot, QSignalBlocker, Qt
from qtpy.QtWidgets import QLabel, QCheckBox, QComboBox, QVBoxLayout, QWidget, QFrame, QTextEdit

from straindesign.parse_constr import linexpr2dict, linexprdict2str
from cnapy.appdata import AppData
from cnapy.utils import QComplReceivLineEdit

class OptimizationDirection(IntEnum):
    min = 0
    max = 1

class ObjectiveTab(QWidget):
    """A widget for display and modification of the global and scenario objective"""

    def __init__(self, appdata: AppData):
        QWidget.__init__(self)
        self.appdata = appdata

        layout = QVBoxLayout()
        label = QLabel("Objective function (as defined in the model)")
        layout.addWidget(label)
        self.global_objective = QWidget() # placeholder
        layout.addWidget(self.global_objective)
        label = QLabel("Optimization direction")
        layout.addWidget(label)
        self.opt_direction = QComboBox()
        self.opt_direction.insertItems(0, ["minimize", "maximize"])
        layout.addWidget(self.opt_direction)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)
        label = QLabel("Scenario ojective")
        layout.addWidget(label)
        self.use_scenario_objective = QCheckBox("Use scenario objective (overrides the model objective)")
        self.use_scenario_objective.setEnabled(True)
        self.use_scenario_objective.stateChanged.connect(self.use_scenario_objective_changed)
        layout.addWidget(self.use_scenario_objective)
        self.scenario_objective = QWidget() # placeholder
        layout.addWidget(self.scenario_objective)
        label = QLabel("Optimization direction")
        layout.addWidget(label)
        self.scenario_opt_direction = QComboBox()
        self.scenario_opt_direction.insertItems(0, ["minimize", "maximize"])
        layout.addWidget(self.scenario_opt_direction)

        label = QLabel("Scenario description")
        layout.addWidget(label)
        self.description = QTextEdit()
        self.description.setPlaceholderText("Enter a description for this scenario")
        layout.addWidget(self.description)
        self.setLayout(layout)

        self.current_global_objective = {}

        self.opt_direction.currentIndexChanged.connect(self.global_optimization_direction_changed)
        self.scenario_opt_direction.currentIndexChanged.connect(self.scenario_optimization_direction_changed)
        self.description.textChanged.connect(self.description_changed)

        self.update()

    def update(self):
        # always recreate the QComplReceivLineEdit to make sure completion list is up to date
        reac_ids = self.appdata.project.cobra_py_model.reactions.list_attr("id")
        global_objective = QComplReceivLineEdit(self, reac_ids)
        self.layout().replaceWidget(self.global_objective, global_objective)
        self.global_objective.deleteLater()
        self.global_objective = global_objective
        scenario_objective = QComplReceivLineEdit(self, reac_ids)
        self.layout().replaceWidget(self.scenario_objective, scenario_objective)
        self.scenario_objective.deleteLater()
        self.scenario_objective = scenario_objective

        with QSignalBlocker(self.global_objective):
            # without the blocker a second line edit becomes visible?!?
            self.global_objective.setText(self.format_objective_expression())
        self.global_objective.textCorrect.connect(self.change_global_objective)
        with QSignalBlocker(self.scenario_objective):
            self.scenario_objective.setText(linexprdict2str(self.appdata.project.scen_values.objective_coefficients))
        self.scenario_objective.textCorrect.connect(self.change_scenario_objective_coefficients)
        with QSignalBlocker(self.use_scenario_objective):
            self.use_scenario_objective.setChecked(self.appdata.project.scen_values.use_scenario_objective)
        self.use_scenario_objective.setEnabled(True)

        self.current_global_objective = {}
        for r in self.appdata.project.cobra_py_model.reactions:
            if r.objective_coefficient != 0:
                self.current_global_objective[r.id] = r.objective_coefficient

        with QSignalBlocker(self.opt_direction):
            self.opt_direction.setCurrentIndex(OptimizationDirection[self.appdata.project.cobra_py_model.objective_direction].value)

        with QSignalBlocker(self.scenario_opt_direction):
            self.scenario_opt_direction.setCurrentIndex(OptimizationDirection[self.appdata.project.scen_values.objective_direction])
        
        with QSignalBlocker(self.description):
            self.description.setText(self.appdata.project.scen_values.description)

    @Slot(bool)
    def change_global_objective(self, yes: bool):
        if yes:
            new_objective = linexpr2dict(self.global_objective.text(),
                            self.appdata.project.cobra_py_model.reactions.list_attr("id"))
            if new_objective != self.current_global_objective:
                for reac_id in self.current_global_objective.keys():
                    self.appdata.project.cobra_py_model.reactions.get_by_id(reac_id).objective_coefficient = 0
                for reac_id, coeff in new_objective.items():
                    self.appdata.project.cobra_py_model.reactions.get_by_id(reac_id).objective_coefficient = coeff
                self.current_global_objective = new_objective
                self.globalObjectiveChanged.emit()

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

    def format_objective_expression(self) -> str:
        first = True
        res = ""
        model = self.appdata.project.cobra_py_model
        for r in model.reactions:
            if r.objective_coefficient != 0:
                if first:
                    res += str(r.objective_coefficient) + " " + str(r.id)
                    first = False
                else:
                    if r.objective_coefficient > 0:
                        res += " +" + \
                            str(r.objective_coefficient) + " " + str(r.id)
                    else:
                        res += " "+str(r.objective_coefficient) + \
                            " " + str(r.id)

        return res

    @Slot(int)
    def global_optimization_direction_changed(self, index: int):
        self.appdata.project.cobra_py_model.objective_direction = OptimizationDirection(index).name
        if self.appdata.project.scen_values.use_scenario_objective:
            self.globalObjectiveChanged.emit()

    @Slot(int)
    def scenario_optimization_direction_changed(self, index: int):
        self.appdata.project.scen_values.objective_direction = OptimizationDirection(index).name
        if self.appdata.project.scen_values.use_scenario_objective:
            self.objectiveSetupChanged.emit()

    def description_changed(self):
        self.appdata.project.scen_values.description = self.description.toPlainText()


    globalObjectiveChanged = Signal()
    objectiveSetupChanged = Signal()
