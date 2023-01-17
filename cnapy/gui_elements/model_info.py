"""The model info view"""

from qtpy.QtCore import Signal, Slot, QSignalBlocker
from qtpy.QtWidgets import (QLabel, QTextEdit, QVBoxLayout, QWidget, QComboBox, QGroupBox)

from straindesign.parse_constr import linexpr2dict
from cnapy.appdata import AppData
from cnapy.gui_elements.scenario_tab import OptimizationDirection
from cnapy.utils import QComplReceivLineEdit

class ModelInfo(QWidget):
    """A widget that shows infos about the model"""

    def __init__(self, appdata: AppData):
        QWidget.__init__(self)
        self.appdata = appdata

        layout = QVBoxLayout()
        group = QGroupBox("Objective function (as defined in the model)")
        self.objective_group_layout: QVBoxLayout = QVBoxLayout()
        self.global_objective = QComplReceivLineEdit(self, [])
        self.objective_group_layout.addWidget(self.global_objective)
        label = QLabel("Optimization direction")
        self.objective_group_layout.addWidget(label)
        self.opt_direction = QComboBox()
        self.opt_direction.insertItems(0, ["minimize", "maximize"])
        self.objective_group_layout.addWidget(self.opt_direction)
        group.setLayout(self.objective_group_layout)
        layout.addWidget(group)

        label = QLabel("Description")
        layout.addWidget(label)
        self.description = QTextEdit()
        self.description.setPlaceholderText("Enter a project description")
        layout.addWidget(self.description)

        self.setLayout(layout)

        self.current_global_objective = {}
        self.global_objective.textCorrect.connect(self.change_global_objective)
        self.opt_direction.currentIndexChanged.connect(self.global_optimization_direction_changed)
        self.description.textChanged.connect(self.description_changed)

        self.update()

    def update(self):
        self.global_objective.set_wordlist(self.appdata.project.cobra_py_model.reactions.list_attr("id"))
        with QSignalBlocker(self.global_objective):
            self.global_objective.setText(self.format_objective_expression())
        self.current_global_objective = {}
        for r in self.appdata.project.cobra_py_model.reactions:
            if r.objective_coefficient != 0:
                self.current_global_objective[r.id] = r.objective_coefficient
        with QSignalBlocker(self.opt_direction):
            self.opt_direction.setCurrentIndex(OptimizationDirection[self.appdata.project.cobra_py_model.objective_direction].value)

        if "description" in self.appdata.project.meta_data:
            description = self.appdata.project.meta_data["description"]
        else:
            description = ""

        with QSignalBlocker(self.description):
            self.description.setText(description)

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
        self.globalObjectiveChanged.emit()

    def description_changed(self):
        self.appdata.project.meta_data["description"] = self.description.toPlainText()
        self.appdata.window.unsaved_changes()

    globalObjectiveChanged = Signal()
