"""The reactions list"""
from math import isclose

import cobra
from qtpy.QtCore import QMimeData, Qt, Signal, Slot
from qtpy.QtGui import QDrag, QIcon
from qtpy.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                            QMessageBox, QPushButton, QSizePolicy, QSplitter,
                            QTableWidget, QTableWidgetItem, QTreeWidget,
                            QTreeWidgetItem,
                            QVBoxLayout, QWidget)
from cnapy.cnadata import CnaData
from cnapy.utils import turn_red, turn_white
from cnapy.utils import SignalThrottler


class DragableTreeWidget(QTreeWidget):
    '''A list of dragable reaction items'''

    def mouseMoveEvent(self, _event):
        item = self.currentItem()
        if item is not None:
            reaction: cobra.Reaction = item.data(3, 0)
            mime_data = QMimeData()
            mime_data.setText(reaction.id)
            drag = QDrag(self)
            drag.setMimeData(mime_data)
            drag.exec_(Qt.CopyAction | Qt.MoveAction, Qt.CopyAction)


class ReactionList(QWidget):
    """A list of reaction"""

    def __init__(self, appdata: CnaData):
        QWidget.__init__(self)
        self.appdata = appdata
        self.last_selected = None
        self.reaction_counter = 1

        self.add_button = QPushButton("Add new reaction")
        self.add_button.setIcon(QIcon.fromTheme("list-add"))
        policy = QSizePolicy()
        policy.ShrinkFlag = True
        self.add_button.setSizePolicy(policy)

        self.reaction_list = DragableTreeWidget()
        self.reaction_list.setDragEnabled(True)
        self.reaction_list.setHeaderLabels(["Id", "Name", "Flux"])
        self.reaction_list.setSortingEnabled(True)

        for r in self.appdata.project.cobra_py_model.reactions:
            self.add_reaction(r)

        self.reaction_mask = ReactionMask(self)
        self.reaction_mask.hide()

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        l = QHBoxLayout()
        l.setAlignment(Qt.AlignRight)
        l.addWidget(self.add_button)
        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Vertical)
        self.splitter.addWidget(self.reaction_list)
        self.splitter.addWidget(self.reaction_mask)
        self.layout.addItem(l)
        self.layout.addWidget(self.splitter)
        self.setLayout(self.layout)

        self.reaction_list.currentItemChanged.connect(self.reaction_selected)
        self.reaction_mask.reactionChanged.connect(
            self.handle_changed_reaction)
        self.reaction_mask.reactionDeleted.connect(
            self.handle_deleted_reaction)
        self.reaction_mask.jumpToMap.connect(self.emit_jump_to_map)
        self.reaction_mask.jumpToMetabolite.connect(
            self.emit_jump_to_metabolite)

        self.add_button.clicked.connect(self.add_new_reaction)

    def clear(self):
        self.reaction_list.clear()
        self.reaction_mask.hide()

    def add_reaction(self, reaction: cobra.Reaction) -> QTreeWidgetItem:
        ''' create a new item in the reaction list'''
        self.reaction_list.clearSelection()
        item = QTreeWidgetItem(self.reaction_list)
        item.setText(0, reaction.id)
        item.setText(1, reaction.name)
        self.set_flux_value(item, reaction.id)

        text = "Id: " + reaction.id + "\nName: " + reaction.name \
            + "\nEquation: " + reaction.build_reaction_string()\
            + "\nLowerbound: " + str(reaction.lower_bound) \
            + "\nUpper bound: " + str(reaction.upper_bound) \
            + "\nObjective coefficient: " + str(reaction.objective_coefficient)

        item.setToolTip(1, text)
        item.setData(3, 0, reaction)

        return item

    def set_flux_value(self, item, key):
        if key in self.appdata.project.scen_values.keys():
            (vl, vu) = self.appdata.project.scen_values[key]
            if isclose(vl, vu, abs_tol=self.appdata.abs_tol):
                item.setData(2, 0, round(vl, self.appdata.rounding))
            else:
                item.setData(
                    2, 0, str((round(vl, self.appdata.rounding), round(vu, self.appdata.rounding))))
            item.setBackground(2, self.appdata.scen_color)
            item.setForeground(2, Qt.black)
        elif key in self.appdata.project.comp_values.keys():
            (vl, vu) = self.appdata.project.comp_values[key]

            # We differentiate special cases like (vl==vu)
            if isclose(vl, vu, abs_tol=self.appdata.abs_tol):
                if self.appdata.modes_coloring:
                    if vl == 0:
                        item.setBackground(2, Qt.red)
                    else:
                        item.setBackground(2, Qt.green)
                else:
                    item.setBackground(2, self.appdata.comp_color)

                item.setData(2, 0, round(vl, self.appdata.rounding))
            else:
                if isclose(vl, 0.0, abs_tol=self.appdata.abs_tol):
                    item.setBackground(2, self.appdata.special_color_1)
                elif isclose(vu, 0.0, abs_tol=self.appdata.abs_tol):
                    item.setBackground(2, self.appdata.special_color_1)
                elif vl <= 0 and vu >= 0:
                    item.setBackground(2, self.appdata.special_color_1)
                else:
                    item.setBackground(2, self.appdata.special_color_2)
                item.setData(
                    2, 0, str((round(vl, self.appdata.rounding), round(vu, self.appdata.rounding))))

            item.setForeground(2, Qt.black)

    def add_new_reaction(self):
        self.reaction_mask.show()
        while True:
            name = "rxn_"+str(self.reaction_counter)
            self.reaction_counter += 1
            if name not in self.appdata.project.cobra_py_model.reactions:
                break
        reaction = cobra.Reaction(name)
        self.appdata.project.cobra_py_model.add_reactions([reaction])
        item = self.add_reaction(reaction)
        self.reaction_selected(item, 1)
        self.appdata.window.unsaved_changes()

    def update_annotations(self, annotation):

        self.reaction_mask.annotation.itemChanged.disconnect(
            self.reaction_mask.throttler.throttle)
        c = self.reaction_mask.annotation.rowCount()
        for i in range(0, c):
            self.reaction_mask.annotation.removeRow(0)
        i = 0
        for key in annotation:
            self.reaction_mask.annotation.insertRow(i)
            keyl = QTableWidgetItem(key)
            iteml = QTableWidgetItem(str(annotation[key]))
            self.reaction_mask.annotation.setItem(i, 0, keyl)
            self.reaction_mask.annotation.setItem(i, 1, iteml)
            i += 1

        self.reaction_mask.annotation.itemChanged.connect(
            self.reaction_mask.throttler.throttle)

    def reaction_selected(self, item: QTreeWidgetItem, _column):
        if item is None:
            self.reaction_mask.hide()
        else:
            item.setSelected(True)
            self.reaction_mask.show()
            reaction: cobra.Reaction = item.data(3, 0)

            self.last_selected = reaction.id
            self.reaction_mask.reaction = reaction

            self.reaction_mask.id.setText(reaction.id)
            self.reaction_mask.name.setText(reaction.name)
            self.reaction_mask.equation.setText(
                reaction.build_reaction_string())
            self.reaction_mask.lower_bound.setText(str(reaction.lower_bound))
            self.reaction_mask.upper_bound.setText(str(reaction.upper_bound))
            self.reaction_mask.coefficent.setText(
                str(reaction.objective_coefficient))
            self.reaction_mask.gene_reaction_rule.setText(
                str(reaction.gene_reaction_rule))
            self.update_annotations(reaction.annotation)

            self.reaction_mask.changed = False

            turn_white(self.reaction_mask.id)
            turn_white(self.reaction_mask.name)
            turn_white(self.reaction_mask.name)
            turn_white(self.reaction_mask.equation)
            turn_white(self.reaction_mask.lower_bound)
            turn_white(self.reaction_mask.upper_bound)
            turn_white(self.reaction_mask.coefficent)
            turn_white(self.reaction_mask.gene_reaction_rule)
            self.reaction_mask.is_valid = True
        (_, r) = self.splitter.getRange(1)
        self.splitter.moveSplitter(r/2, 1)
        self.reaction_mask.update_state()

    def handle_changed_reaction(self, reaction: cobra.Reaction):
        # Update reaction item in list
        root = self.reaction_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            if item.data(3, 0) == reaction:
                old_id = item.text(0)
                item.setText(0, reaction.id)
                item.setText(1, reaction.name)
                break

        self.last_selected = self.reaction_mask.id.text()
        self.reactionChanged.emit(old_id, reaction)

    def handle_deleted_reaction(self, reaction: cobra.Reaction):
        '''Remove reaction item from reaction list'''
        root = self.reaction_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            if item.data(3, 0) == reaction:
                # remove item
                self.reaction_list.takeTopLevelItem(
                    self.reaction_list.indexOfTopLevelItem(item))
                break

        self.last_selected = self.reaction_mask.id.text()
        self.reactionDeleted.emit(reaction)

    def update_selected(self, string):
        root = self.reaction_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            item.setHidden(True)

        for item in self.reaction_list.findItems(string, Qt.MatchContains, 0):
            item.setHidden(False)
        for item in self.reaction_list.findItems(string, Qt.MatchContains, 1):
            item.setHidden(False)

    def update(self):
        self.reaction_list.clear()
        for r in self.appdata.project.cobra_py_model.reactions:
            self.add_reaction(r)

        if self.last_selected is None:
            pass
        else:
            items = self.reaction_list.findItems(
                self.last_selected, Qt.MatchExactly)

            for i in items:
                self.reaction_list.setCurrentItem(i)
                break

        self.reaction_mask.update_state()

    def set_current_item(self, key):
        self.last_selected = key
        self.update()

    def emit_jump_to_map(self, idx: str, reaction: str):
        self.jumpToMap.emit(idx, reaction)

    def emit_jump_to_metabolite(self, metabolite):
        self.jumpToMetabolite.emit(metabolite)

    itemActivated = Signal(str)
    reactionChanged = Signal(str, cobra.Reaction)
    reactionDeleted = Signal(cobra.Reaction)
    jumpToMap = Signal(str, str)
    jumpToMetabolite = Signal(str)


class JumpButton(QPushButton):
    """button to jump to reactions on map"""

    def __init__(self, parent, r_id: str):
        QPushButton.__init__(self, r_id)
        self.parent = parent
        self.id: str = r_id
        self.clicked.connect(self.emit_jump_to_map)

    def emit_jump_to_map(self):
        self.jumpToMap.emit(self.id)

    jumpToMap = Signal(str)


class JumpList(QWidget):
    """List of buttons to jump to reactions on map"""

    def __init__(self, parent):
        QWidget.__init__(self)
        self.parent = parent
        self.layout = QHBoxLayout()
        self.layout.setAlignment(Qt.AlignLeft)

    def clear(self):
        for i in reversed(range(self.layout.count())):
            self.layout.itemAt(i).widget().setParent(None)

    def add(self, name: str):
        if self.layout.count() == 0:
            label = QLabel("Jump to reaction on map:")
            self.layout.addWidget(label)

        jb = JumpButton(self, name)
        policy = QSizePolicy()
        policy.ShrinkFlag = True
        jb.setSizePolicy(policy)
        self.layout.addWidget(jb)
        self.setLayout(self.layout)

        jb.jumpToMap.connect(self.parent.emit_jump_to_map)

    @ Slot(str)
    def emit_jump_to_map(self: JumpButton, name: str):
        self.parent.emit_jump_to_map(name)

    jumpToMap = Signal(str)


class ReactionMask(QWidget):
    """The input mask for a reaction"""

    def __init__(self, parent: ReactionList):
        QWidget.__init__(self)

        self.parent = parent
        self.reaction = None
        self.is_valid = True
        self.changed = False
        self.setAcceptDrops(False)

        layout = QVBoxLayout()
        l = QHBoxLayout()
        self.delete_button = QPushButton("Delete reaction")
        self.delete_button.setIcon(QIcon.fromTheme("edit-delete"))
        policy = QSizePolicy()
        policy.ShrinkFlag = True
        self.delete_button.setSizePolicy(policy)
        l.addWidget(self.delete_button)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Id:")
        self.id = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.id)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Name:")
        self.name = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.name)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Equation:")
        self.equation = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.equation)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Rate min:")
        self.lower_bound = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.lower_bound)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Rate max:")
        self.upper_bound = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.upper_bound)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Coefficient in obj. function:")
        self.coefficent = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.coefficent)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Gene reaction rule:")
        self.gene_reaction_rule = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.gene_reaction_rule)
        layout.addItem(l)

        l = QVBoxLayout()
        label = QLabel("Annotations:")
        l.addWidget(label)
        l2 = QHBoxLayout()
        self.annotation = QTableWidget(0, 2)
        self.annotation.setHorizontalHeaderLabels(
            ["key", "value"])
        self.annotation.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        l2.addWidget(self.annotation)

        self.add_anno = QPushButton("+")
        self.add_anno.clicked.connect(self.add_anno_row)
        l2.addWidget(self.add_anno)
        l.addItem(l2)
        layout.addItem(l)

        l = QVBoxLayout()
        label = QLabel("Metabolites involved in this reaction:")
        l.addWidget(label)
        l2 = QHBoxLayout()
        self.metabolites = QTreeWidget()
        self.metabolites.setHeaderLabels(["Id"])
        self.metabolites.setSortingEnabled(True)
        l2.addWidget(self.metabolites)
        l.addItem(l2)
        self.metabolites.itemDoubleClicked.connect(
            self.emit_jump_to_metabolite)
        layout.addItem(l)

        self.jump_list = JumpList(self)
        layout.addWidget(self.jump_list)

        self.setLayout(layout)

        self.delete_button.clicked.connect(self.delete_reaction)

        self.throttler = SignalThrottler(500)
        self.throttler.triggered.connect(self.reaction_data_changed)

        self.id.textEdited.connect(self.throttler.throttle)
        self.name.textEdited.connect(self.throttler.throttle)
        self.equation.textEdited.connect(self.throttler.throttle)
        self.lower_bound.textEdited.connect(self.throttler.throttle)
        self.upper_bound.textEdited.connect(self.throttler.throttle)
        self.coefficent.textEdited.connect(self.throttler.throttle)
        self.gene_reaction_rule.textEdited.connect(self.throttler.throttle)
        self.annotation.itemChanged.connect(self.throttler.throttle)

        self.validate_mask()

    def add_anno_row(self):
        i = self.annotation.rowCount()
        self.annotation.insertRow(i)
        self.changed = True

    def apply(self):
        try:
            self.reaction.id = self.id.text()
        except ValueError:
            turn_red(self.id)
            QMessageBox.information(
                self, 'Invalid id', 'Could not apply changes identifier ' +
                self.id.text() + ' already used.')
        else:
            self.reaction.name = self.name.text()
            self.reaction.build_reaction_from_string(self.equation.text())
            self.reaction.lower_bound = float(self.lower_bound.text())
            self.reaction.upper_bound = float(self.upper_bound.text())
            self.reaction.objective_coefficient = float(self.coefficent.text())
            self.reaction.gene_reaction_rule = self.gene_reaction_rule.text()
            self.reaction.annotation = {}
            rows = self.annotation.rowCount()
            for i in range(0, rows):
                key = self.annotation.item(i, 0).text()
                if self.annotation.item(i, 1) is None:
                    value = ""
                else:
                    value = self.annotation.item(i, 1).text()

                self.reaction.annotation[key] = value

            self.changed = False
            self.reactionChanged.emit(self.reaction)

    def delete_reaction(self):
        self.hide()
        self.reactionDeleted.emit(self.reaction)

    def validate_id(self):

        with self.parent.appdata.project.cobra_py_model as model:
            try:
                r = cobra.Reaction(id=self.id.text())
                model.add_reaction(r)
            except ValueError:
                turn_red(self.id)
                return False
            else:
                turn_white(self.id)
                return True

    def validate_name(self):
        with self.parent.appdata.project.cobra_py_model as model:
            try:
                r = cobra.Reaction(id="testid", name=self.name.text())
                model.add_reaction(r)
            except ValueError:
                turn_red(self.name)
                return False
            else:
                turn_white(self.name)
                return True

    def validate_equation(self):
        ok = False
        test_reaction = cobra.Reaction(
            "xxxx_cnapy_test_reaction", name="cnapy test reaction")
        with self.parent.appdata.project.cobra_py_model as model:
            model.add_reaction(test_reaction)

            try:
                eqtxt = self.equation.text().rstrip()
                if len(eqtxt) > 0 and eqtxt[-1] == '+':
                    turn_red(self.equation)
                else:
                    test_reaction.build_reaction_from_string(eqtxt)
                    turn_white(self.equation)
                    ok = True
            except ValueError:
                turn_red(self.equation)

        try:
            test_reaction = self.parent.appdata.project.cobra_py_model.reactions.get_by_id(
                "xxxx_cnapy_test_reaction")
            self.parent.appdata.project.cobra_py_model.remove_reactions(
                [test_reaction], remove_orphans=True)
        except KeyError:
            pass

        return ok

    def validate_lowerbound(self):
        try:
            _x = float(self.lower_bound.text())
        except ValueError:
            turn_red(self.lower_bound)
            return False
        else:
            turn_white(self.lower_bound)
            return True

    def validate_upperbound(self):
        try:
            _x = float(self.upper_bound.text())
        except ValueError:
            turn_red(self.upper_bound)
            return False
        else:
            turn_white(self.upper_bound)
            return True

    def validate_coefficient(self):
        try:
            _x = float(self.coefficent.text())
        except ValueError:
            turn_red(self.coefficent)
            return False
        else:
            turn_white(self.coefficent)
            return True

    def validate_gene_reaction_rule(self):
        try:
            _x = float(self.gene_reaction_rule.text())
        except ValueError:
            turn_red(self.gene_reaction_rule)
            return False
        else:
            turn_white(self.gene_reaction_rule)
            return True

    def validate_mask(self):

        valid_id = self.validate_id()
        valid_name = self.validate_name()
        valid_equation = self.validate_equation()
        valid_lb = self.validate_lowerbound()
        valid_ub = self.validate_upperbound()
        valid_coefficient = self.validate_coefficient()
        if valid_id & valid_name & valid_equation & valid_lb & valid_ub & valid_coefficient:
            self.is_valid = True
        else:
            self.is_valid = False

    def reaction_data_changed(self):
        self.changed = True
        self.validate_mask()
        if self.is_valid:
            self.apply()
            self.update_state()

    def update_state(self):
        self.jump_list.clear()
        for name, m in self.parent.appdata.project.maps.items():
            if self.id.text() in m["boxes"]:
                self.jump_list.add(name)

        self.metabolites.clear()
        if self.parent.appdata.project.cobra_py_model.reactions.has_id(self.id.text()):
            reaction = self.parent.appdata.project.cobra_py_model.reactions.get_by_id(
                self.id.text())
            for m in reaction.metabolites:
                item = QTreeWidgetItem(self.metabolites)
                item.setText(0, m.id)
                item.setText(1, m.name)
                item.setData(2, 0, m)
                text = "Id: " + m.id + "\nName: " + m.name
                item.setToolTip(1, text)

    def emit_jump_to_map(self, name):
        self.jumpToMap.emit(name, self.id.text())

    def emit_jump_to_metabolite(self, metabolite):
        self.jumpToMetabolite.emit(str(metabolite.data(2, 0)))

    jumpToMap = Signal(str, str)
    jumpToMetabolite = Signal(str)
    reactionChanged = Signal(cobra.Reaction)
    reactionDeleted = Signal(cobra.Reaction)
