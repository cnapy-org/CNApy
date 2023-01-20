from enum import IntEnum
from math import isnan

from qtpy.QtCore import Signal, Slot, QSignalBlocker, Qt, QStringListModel
from qtpy.QtGui import QBrush, QColor
from qtpy.QtWidgets import (QLabel, QCheckBox, QComboBox, QVBoxLayout, QWidget, QTextEdit, QGroupBox,
                            QTableWidget, QTableWidgetItem, QHBoxLayout, QPushButton, QLineEdit,
                            QAbstractItemView, QMessageBox)

import cobra
from cnapy.appdata import AppData, Scenario
from cnapy.utils import QComplReceivLineEdit, format_scenario_constraint, turn_red, turn_white, BACKGROUND_COLOR
from straindesign.parse_constr import linexpr2dict, linexprdict2str, lineq2list

class OptimizationDirection(IntEnum):
    min = 0
    max = 1

class ScenarioReactionColumn(IntEnum):
    Id = 0
    Flux = 1
    LB = 2
    UB = 3

red_brush = QBrush(QColor.fromRgb(0xff, 0x99, 0x99))
white_brush = QBrush(QColor.fromRgb(0xff, 0xff, 0xff))

class ScenarioTab(QWidget):
    """A widget for display and modification of scenario objective, reactions and constraints"""

    def __init__(self, central_widget):
        QWidget.__init__(self)
        self.appdata: AppData = central_widget.appdata
        self.central_widget = central_widget
        self.reaction_ids = []
        self.reaction_ids_model: QStringListModel = QStringListModel()

        layout = QVBoxLayout()
        group = QGroupBox("Scenario ojective")
        self.objective_group_layout = QVBoxLayout()
        self.use_scenario_objective = QCheckBox("Use scenario objective (overrides the model objective)")
        self.use_scenario_objective.setEnabled(True)
        self.use_scenario_objective.stateChanged.connect(self.use_scenario_objective_changed)
        self.objective_group_layout.addWidget(self.use_scenario_objective)
        self.scenario_objective = QComplReceivLineEdit(self, [])
        self.scenario_objective.set_wordlist(self.reaction_ids, replace_completer_model=False)
        self.scenario_objective.set_completer_model(self.reaction_ids_model)
        self.objective_group_layout.addWidget(self.scenario_objective)
        label = QLabel("Optimization direction")
        self.objective_group_layout.addWidget(label)
        self.scenario_opt_direction = QComboBox()
        self.scenario_opt_direction.insertItems(0, ["minimize", "maximize"])
        self.objective_group_layout.addWidget(self.scenario_opt_direction)
        group.setLayout(self.objective_group_layout)
        layout.addWidget(group)

        label = QLabel("Scenario reactions")
        hbox = QHBoxLayout()
        hbox.addWidget(label)
        self.add_reaction = QPushButton("+")
        self.add_reaction.clicked.connect(self.add_scenario_reaction)
        hbox.addWidget(self.add_reaction)
        self.delete_reaction = QPushButton("-")
        self.delete_reaction.clicked.connect(self.delete_scenario_reaction)
        hbox.addWidget(self.delete_reaction)
        hbox.addStretch()
        layout.addLayout(hbox)
        self.reactions = QTableWidget(0, len(ScenarioReactionColumn))
        self.reactions.setHorizontalHeaderLabels([ScenarioReactionColumn(i).name for i in range(len(ScenarioReactionColumn))])
        self.reactions.setEditTriggers(QAbstractItemView.CurrentChanged | QAbstractItemView.SelectedClicked)
        layout.addWidget(self.reactions)

        layout.addWidget(QLabel("Reaction equation"))
        self.equation = QLineEdit()
        self.equation.setPlaceholderText("Enter a reaction equation")
        layout.addWidget(self.equation)

        label = QLabel("Scenario constraints")
        hbox = QHBoxLayout()
        hbox.addWidget(label)
        self.add_constraint_button = QPushButton("+")
        self.add_constraint_button.clicked.connect(self.add_constraint)
        hbox.addWidget(self.add_constraint_button)
        self.delete_constraint_button = QPushButton("-")
        self.delete_constraint_button.clicked.connect(self.delete_constraint)
        hbox.addWidget(self.delete_constraint_button)
        hbox.addStretch()
        layout.addLayout(hbox)
        self.constraints = QTableWidget(0, 1) # table with fixed row order
        self.constraints.horizontalHeader().setHidden(True)
        self.constraints.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.constraints)

        label = QLabel("Scenario description")
        layout.addWidget(label)
        self.description = QTextEdit()
        self.description.setPlaceholderText("Enter a description for this scenario")
        layout.addWidget(self.description)
        self.setLayout(layout)

        self.reactions.currentCellChanged.connect(self.handle_current_cell_changed)
        self.reactions.cellChanged.connect(self.cell_content_changed)
        self.equation.editingFinished.connect(self.equation_edited)
        self.scenario_objective.textCorrect.connect(self.change_scenario_objective_coefficients)
        self.scenario_objective.editingFinished.connect(self.validate_objective)
        self.scenario_opt_direction.currentIndexChanged.connect(self.scenario_optimization_direction_changed)
        self.description.textChanged.connect(self.description_changed)

        self.update()

    def update(self):
        self.update_reation_id_lists()

        with QSignalBlocker(self.scenario_opt_direction):
            self.scenario_opt_direction.setCurrentIndex(OptimizationDirection[self.appdata.project.scen_values.objective_direction])

        for row in range(self.reactions.rowCount()):
            reac_id: str = self.reactions.item(row, ScenarioReactionColumn.Id).data(Qt.UserRole)
            if reac_id in self.appdata.project.comp_values:
                (vl, vu) = self.appdata.project.comp_values[reac_id]
                flux_text, background_color, _ = self.appdata.flux_value_display(vl, vu)
            else:
                flux_text = ''
                background_color = Qt.white
            item = self.reactions.item(row, ScenarioReactionColumn.Flux)
            item.setText(flux_text)
            item.setBackground(QBrush(background_color))

    def update_reation_id_lists(self):
        # update the reaction ids within the same list (such a list should be kept on a project level)
        num_reac = len(self.appdata.project.cobra_py_model.reactions)
        num_scenario_reac = len(self.appdata.project.scen_values.reactions)
        diff = num_reac + num_scenario_reac - len(self.reaction_ids)
        if diff > 0:
            self.reaction_ids += [None]*diff
        elif diff < 0:
            del self.reaction_ids[diff:]
        for i in range(num_reac):
            self.reaction_ids[i] = self.appdata.project.cobra_py_model.reactions[i].id
        for i, reac_id in enumerate(self.appdata.project.scen_values.reactions.keys()):
            self.reaction_ids[num_reac+i] = reac_id
        self.reaction_ids_model.setStringList(self.reaction_ids)
            
    def recreate_scenario_items(self):
        # assumes that the objective, reactions and constraints are all valid
        with QSignalBlocker(self.scenario_objective):
            self.scenario_objective.setText(linexprdict2str(self.appdata.project.scen_values.objective_coefficients))
        with QSignalBlocker(self.use_scenario_objective):
            self.use_scenario_objective.setChecked(self.appdata.project.scen_values.use_scenario_objective)
        self.use_scenario_objective.setEnabled(True)

        num_scenario_reactions = len(self.appdata.project.scen_values.reactions)
        with QSignalBlocker(self.reactions):
            self.reactions.clearContents()
            self.reactions.setRowCount(num_scenario_reactions)
            for row,reac_id in enumerate(self.appdata.project.scen_values.reactions):
                self.new_reaction_row(row)
                self.update_reaction_row(row, reac_id)
        if num_scenario_reactions > 0:
            self.reactions.setCurrentCell(0, ScenarioReactionColumn.Id)
            self.equation.setEnabled(True)
        else:
            self.equation.clear()
            self.equation.setEnabled(False)
        turn_white(self.equation)

        self.constraints.clearContents()
        self.constraints.setRowCount(0)
        for constr in self.appdata.project.scen_values.constraints:
            _, constraint_edit = self.add_constraint_row()
            with QSignalBlocker(constraint_edit):
                constraint_edit.setText(format_scenario_constraint(constr))

        with QSignalBlocker(self.description):
            self.description.setText(self.appdata.project.scen_values.description)

    @Slot(int, int)
    def cell_content_changed(self, row: int, column: int):
        reac_id: str = self.reactions.item(row, ScenarioReactionColumn.Id).data(Qt.UserRole)
        if column == ScenarioReactionColumn.Id:
            new_reac_id = self.reactions.currentItem().text().strip()
            with QSignalBlocker(self.reactions):
                if len(new_reac_id) == 0:
                    self.reactions.item(row, ScenarioReactionColumn.Id).setText(reac_id)
                elif self.verify_scenario_reaction_id(new_reac_id):
                        self.reactions.item(row, ScenarioReactionColumn.Id).setData(Qt.UserRole, new_reac_id)
                        self.appdata.project.scen_values.reactions[new_reac_id] = self.appdata.project.scen_values.reactions[reac_id]
                        del self.appdata.project.scen_values.reactions[reac_id]
                else:
                    self.reactions.item(row, ScenarioReactionColumn.Id).setText(reac_id)
                    QMessageBox.information(self, 'Reaction ID already in use',
                                            'Choose a different reaction identifier.')
            self.update_reation_id_lists()
            self.check_constraints_and_objective()
            if self.appdata.auto_fba:
                self.central_widget.parent.fba()
        elif column == ScenarioReactionColumn.LB or column == ScenarioReactionColumn.UB:
            lb, lb_brush = self.verify_bound(self.reactions.item(row, ScenarioReactionColumn.LB))
            ub, ub_brush = self.verify_bound(self.reactions.item(row, ScenarioReactionColumn.UB))
            if not (isnan(lb) or isnan(ub)):
                if lb <= ub:
                    self.appdata.project.scen_values.reactions[reac_id][1] = lb
                    self.appdata.project.scen_values.reactions[reac_id][2] = ub
                    if self.appdata.auto_fba:
                        self.central_widget.parent.fba()
                else:
                    lb_brush = red_brush
                    ub_brush = red_brush
            self.reactions.item(row, ScenarioReactionColumn.LB).setBackground(lb_brush)
            self.reactions.item(row, ScenarioReactionColumn.UB).setBackground(ub_brush)

    def verify_bound(self, item: QTableWidgetItem):
        try:
            val = float(item.text())
            brush = white_brush
        except:
            val = float('NaN')
            brush = red_brush
        return val, brush

    @Slot()
    def equation_edited(self):
        if self.equation.isModified():
            self.equation.setModified(False)
            row: int = self.reactions.currentRow()
            reac_id: str = self.reactions.item(row, ScenarioReactionColumn.Id).data(Qt.UserRole)
            existing_metabolites = set(self.appdata.project.cobra_py_model.metabolites.list_attr('id'))
            if reac_id in self.appdata.project.cobra_py_model.reactions: # overwrite existing reaction
                reaction = self.appdata.project.cobra_py_model.reactions.get_by_id(reac_id)
                original_metabolites = reaction.metabolites.copy()
            else:
                reaction = cobra.Reaction(reac_id)
                self.appdata.project.cobra_py_model.add_reaction(reaction)
                original_metabolites = None
            try:
                eqtxt = self.equation.text().rstrip()
                if len(eqtxt) > 0 and eqtxt[-1] == '+':
                    raise ValueError
                reaction.build_reaction_from_string(eqtxt)
                self.appdata.project.scen_values.reactions[reac_id][0] = {m.id: c for m,c in reaction.metabolites.items()}
                self.appdata.project.scen_values.reactions[reac_id][1] = reaction.lower_bound
                self.appdata.project.scen_values.reactions[reac_id][2] = reaction.upper_bound
                turn_white(self.equation)
                with QSignalBlocker(self.reactions):
                    self.update_reaction_row(row, reac_id)
                equation_valid = True
            except:
                turn_red(self.equation)
                with QSignalBlocker(self.equation):
                    QMessageBox.information(self, 'Cannot parse equation',
                                            'Check the reaction equation for mistakes.')
                equation_valid = False
            added_metabolites = [m for m in reaction.metabolites if m.id not in existing_metabolites]
            if original_metabolites is None:
                self.appdata.project.cobra_py_model.remove_reactions([reaction])
            else:
                reaction.subtract_metabolites(reaction.metabolites)
                reaction.add_metabolites(original_metabolites)
            self.appdata.project.cobra_py_model.remove_metabolites(added_metabolites)

            if equation_valid and self.appdata.auto_fba:
                self.central_widget.parent.fba()

    @Slot(int, int, int, int)
    def handle_current_cell_changed(self, row: int, column: int, previous_row: int, previous_column: int):
        if row < 0:
            self.equation.clear()
            self.equation.setEnabled(False)
        else:
            self.equation.setEnabled(True)
            if row != previous_row:
                self.update_reaction_equation(self.reactions.item(row, ScenarioReactionColumn.Id).data(Qt.UserRole))

    def update_reaction_equation(self, reac_id: str):
        metabolites, lb, ub = self.appdata.project.scen_values.reactions[reac_id]
        with self.appdata.project.cobra_py_model as model:
            model.add_metabolites([cobra.Metabolite(m) for m in metabolites])
            if reac_id in self.appdata.project.cobra_py_model.reactions: # overwrite existing reaction
                reaction = self.appdata.project.cobra_py_model.reactions.get_by_id(reac_id)
                reaction.subtract_metabolites(reaction.metabolites, combine=True) # remove current metabolites
            else:
                reaction = cobra.Reaction(reac_id)
                model.add_reaction(reaction)
            reaction.add_metabolites(metabolites)
            reaction.lower_bound = lb
            reaction.upper_bound = ub
            turn_white(self.equation)
            self.equation.setText(reaction.build_reaction_string())

    def verify_scenario_reaction_id(self, reac_id: str) -> bool:
        return reac_id not in self.appdata.project.scen_values.reactions \
                and reac_id not in self.appdata.project.cobra_py_model.reactions

    @Slot()
    def add_scenario_reaction(self):
        row: int = self.reactions.rowCount()
        # self.reactions.setSortingEnabled(False)
        self.reactions.setRowCount(row + 1)
        reac_id: str = "S"+str(row)
        while not self.verify_scenario_reaction_id(reac_id):
            reac_id += "_"
        self.appdata.project.scen_values.reactions[reac_id] = [{}, cobra.Configuration().lower_bound, cobra.Configuration().upper_bound]
        self.update_reation_id_lists()
        self.check_constraints_and_objective()
        with QSignalBlocker(self.reactions):
            self.new_reaction_row(row)
            self.update_reaction_row(row, reac_id)
        self.reactions.setCurrentCell(row, ScenarioReactionColumn.Id)
        # self.reactions.setSortingEnabled(True)

    @Slot()
    def delete_scenario_reaction(self):
        row: int = self.reactions.currentRow()
        if row >= 0:
            reac_id: str = self.reactions.item(row, ScenarioReactionColumn.Id).data(Qt.UserRole)
            self.reactions.removeRow(row)
            del self.appdata.project.scen_values.reactions[reac_id]
            self.update_reation_id_lists()
            self.check_constraints_and_objective()
            self.reactions.setCurrentCell(self.reactions.currentRow(), 0) # to make the cell appear selected in the GUI
            if self.appdata.auto_fba:
                self.central_widget.parent.fba()

    def new_reaction_row(self, row: int):
        item = QTableWidgetItem()
        self.reactions.setItem(row, ScenarioReactionColumn.Id, item)
        flux_item = QTableWidgetItem()
        flux_item.setFlags(Qt.ItemIsSelectable) # not editable
        flux_item.setForeground(item.foreground()) # to keep text color black
        self.reactions.setItem(row, ScenarioReactionColumn.Flux, flux_item)
        self.reactions.setItem(row, ScenarioReactionColumn.LB, QTableWidgetItem())
        self.reactions.setItem(row, ScenarioReactionColumn.UB, QTableWidgetItem())

    def update_reaction_row(self, row: int, reac_id: str):
        reac_id_item = self.reactions.item(row, ScenarioReactionColumn.Id)
        reac_id_item.setText(reac_id)
        reac_id_item.setData(Qt.UserRole, reac_id)
        _, lb, ub = self.appdata.project.scen_values.reactions[reac_id]
        self.reactions.item(row, ScenarioReactionColumn.LB).setText(str(lb))
        self.reactions.item(row, ScenarioReactionColumn.UB).setText(str(ub))

    @Slot()
    def add_constraint(self):
        row, _ = self.add_constraint_row()
        self.appdata.project.scen_values.constraints.append(Scenario.empty_constraint)
        self.constraints.setCurrentCell(row, 0)
        
    def add_constraint_row(self):
        row: int = self.constraints.rowCount()
        self.constraints.setRowCount(row + 1)
        constraint_edit = QComplReceivLineEdit(self.constraints, [], is_constr=True)
        constraint_edit.set_wordlist(self.reaction_ids, replace_completer_model=False)
        constraint_edit.set_completer_model(self.reaction_ids_model)
        constraint_edit.textCorrect.connect(self.constraint_edited)
        constraint_edit.editingFinished.connect(self.constraint_editing_finished)
        self.constraints.setCellWidget(row, 0, constraint_edit)
        return row, constraint_edit

    @Slot()
    def constraint_editing_finished(self):
        constraint_edit: QComplReceivLineEdit = self.sender()
        if constraint_edit.is_valid is True:
            if self.appdata.auto_fba:
                self.central_widget.parent.fba()
        else:
            constraint_edit.setStyleSheet(BACKGROUND_COLOR("#ffb0b0", constraint_edit.objectName()))

    @Slot()
    def delete_constraint(self):
        row: int = self.constraints.currentRow()
        if row >= 0:
            with QSignalBlocker(self.constraints): # does not appear to suppress the focus out event
                self.constraints.removeRow(row)
            del self.appdata.project.scen_values.constraints[row]
            if self.appdata.auto_fba:
                self.central_widget.parent.fba()

    @Slot(bool)
    def constraint_edited(self, text_correct: bool):
        row: int = self.constraints.currentRow()
        if row >= 0: # in case this is triggered when nothing is selected
            constraint_edit: QComplReceivLineEdit = self.constraints.cellWidget(row, 0)
            if text_correct:
                self.appdata.project.scen_values.constraints[row] = lineq2list([constraint_edit.text()],
                    self.reaction_ids)[0]
            else:
                self.appdata.project.scen_values.constraints[row] = Scenario.empty_constraint

    def check_constraints_and_objective(self):
        for row in range(self.constraints.rowCount()):
            constraint_edit: QComplReceivLineEdit = self.constraints.cellWidget(row, 0)
            constraint_edit.check_text(True)
        self.scenario_objective.check_text(True)
        self.validate_objective()

    @Slot(bool)
    def change_scenario_objective_coefficients(self, text_correct: bool):
        if text_correct:
            new_objective = linexpr2dict(self.scenario_objective.text(), self.reaction_ids)
            if new_objective != self.appdata.project.scen_values.objective_coefficients:
                self.appdata.project.scen_values.objective_coefficients = new_objective
                if self.appdata.project.scen_values.use_scenario_objective:
                    self.objectiveSetupChanged.emit()
            self.use_scenario_objective.setEnabled(True)
        else:
            self.appdata.project.scen_values.objective_coefficients.clear()
            self.use_scenario_objective.setEnabled(False)

    @Slot()
    def validate_objective(self):
        if not self.scenario_objective.is_valid and self.appdata.project.scen_values.use_scenario_objective:
            self.use_scenario_objective.setChecked(False)

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
