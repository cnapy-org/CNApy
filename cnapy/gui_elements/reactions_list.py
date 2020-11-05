"""The CellNetAnalyzer reactions list"""
import cobra
from math import isclose
from qtpy.QtCore import Qt, Signal, Slot
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (QComboBox, QHBoxLayout, QHeaderView, QLabel,
                            QLineEdit, QMessageBox, QPushButton,
                            QSizePolicy, QSplitter, QTableWidget,
                            QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
                            QVBoxLayout, QWidget)

from cnapy.cnadata import CnaData


class ReactionList(QWidget):
    """A list of reaction"""

    def __init__(self, appdata: CnaData):
        QWidget.__init__(self)
        self.appdata = appdata
        self.last_selected = None
        self.new = True

        self.add_button = QPushButton("Add new reaction")
        self.add_button.setIcon(QIcon.fromTheme("list-add"))
        policy = QSizePolicy()
        policy.ShrinkFlag = True
        self.add_button.setSizePolicy(policy)

        self.reaction_list = QTreeWidget()
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
        self.splitter.addWidget(self.reaction_list)
        self.splitter.addWidget(self.reaction_mask)
        self.layout.addItem(l)
        self.layout.addWidget(self.splitter)
        self.setLayout(self.layout)

        self.reaction_list.currentItemChanged.connect(self.reaction_selected)
        self.reaction_mask.changedReactionList.connect(self.emit_changedModel)
        self.reaction_mask.jumpToMap.connect(self.emit_jump_to_map)

        self.add_button.clicked.connect(self.add_new_reaction)

    def clear(self):
        self.reaction_list.clear()
        self.reaction_mask.hide()

    def add_reaction(self, reaction):
        item = QTreeWidgetItem(self.reaction_list)
        item.setText(0, reaction.id)
        item.setText(1, reaction.name)
        self.set_flux_value(item, reaction.id)
        item.setData(3, 0, reaction)

    def set_flux_value(self, item, key):
        if key in self.appdata.project.scen_values.keys():
            (vl, vu) = self.appdata.project.scen_values[key]
            if isclose(vl, vu, abs_tol=self.appdata.abs_tol):
                item.setData(2, 0, round(vl, self.appdata.rounding))
            else:
                item.setData(
                    2, 0, str((round(vl, self.appdata.rounding), round(vu, self.appdata.rounding))))
            item.setBackground(2, self.appdata.Scencolor)
            item.setForeground(2, Qt.black)
        elif key in self.appdata.project.comp_values.keys():
            (vl, vu) = self.appdata.project.comp_values[key]

            # We differentiate special cases like (vl==vu)
            if isclose(vl, vu, abs_tol=self.appdata.abs_tol):
                if len(self.appdata.project.modes) == 0:
                    item.setBackground(2, self.appdata.Compcolor)
                else:
                    if vl == 0:
                        item.setBackground(2, Qt.red)
                    else:
                        item.setBackground(2, Qt.green)

                item.setData(2, 0, round(vl, self.appdata.rounding))
            else:
                if isclose(vl, 0.0, abs_tol=self.appdata.abs_tol):
                    item.setBackground(2, self.appdata.SpecialColor1)
                elif isclose(vu, 0.0, abs_tol=self.appdata.abs_tol):
                    item.setBackground(2, self.appdata.SpecialColor1)
                elif vl <= 0 and vu >= 0:
                    item.setBackground(2, self.appdata.SpecialColor1)
                else:
                    item.setBackground(2, self.appdata.SpecialColor2)
                item.setData(
                    2, 0, str((round(vl, self.appdata.rounding), round(vu, self.appdata.rounding))))

            item.setForeground(2, Qt.black)

    def add_new_reaction(self):
        self.new = True
        self.reaction_mask.show()
        reaction = cobra.Reaction()

        self.reaction_mask.id.setText(reaction.id)
        self.reaction_mask.name.setText(reaction.name)
        self.reaction_mask.equation.setText(reaction.build_reaction_string())
        self.reaction_mask.rate_min.setText(str(reaction.lower_bound))
        self.reaction_mask.rate_max.setText(str(reaction.upper_bound))
        self.reaction_mask.coefficent.setText(
            str(reaction.objective_coefficient))
        # self.reaction_mask.variance.setText()
        self.update_annotations({})
        self.reaction_mask.old = None
        self.reaction_mask.changed = False
        self.reaction_mask.update_state()

    def update_annotations(self, annotation):

        self.reaction_mask.annotation.itemChanged.disconnect(
            self.reaction_mask.reaction_data_changed)
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
            self.reaction_mask.reaction_data_changed)

    def reaction_selected(self, item, _column):
        self.new = False
        if item is None:
            self.reaction_mask.hide()
        else:
            # print("last selected", self.last_selected)
            self.reaction_mask.show()
            reaction: cobra.Reaction = item.data(3, 0)
            self.reaction_mask.id.setText(reaction.id)
            self.reaction_mask.name.setText(reaction.name)
            self.reaction_mask.equation.setText(
                reaction.build_reaction_string())
            self.reaction_mask.rate_min.setText(str(reaction.lower_bound))
            self.reaction_mask.rate_max.setText(str(reaction.upper_bound))
            self.reaction_mask.coefficent.setText(
                str(reaction.objective_coefficient))
            # self.reaction_mask.variance.setText()
            self.update_annotations(reaction.annotation)

            self.reaction_mask.old = reaction
            self.reaction_mask.changed = False
            self.reaction_mask.update_state()

    def emit_changedModel(self):
        self.last_selected = self.reaction_mask.id.text()
        # print("last selected", self.last_selected)
        self.changedModel.emit()

    def update_selected(self, string):
        print("reaction_list:update_selected", string)
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
            # print("something was previosly selected")
            items = self.reaction_list.findItems(
                self.last_selected, Qt.MatchExactly)

            for i in items:
                self.reaction_list.setCurrentItem(i)
                print(i.text(0))
                break

        self.reaction_mask.update_state()

    def setCurrentItem(self, key):
        self.last_selected = key
        self.update()

    def emit_jump_to_map(self, idx: int, reaction):
        # print("ReactionList::emit jump to map", idx, reaction)
        self.jumpToMap.emit(idx, reaction)

    itemActivated = Signal(str)
    changedModel = Signal()
    jumpToMap = Signal(int, str)


class JumpButton(QPushButton):
    """button to jump to reactions on map"""

    def __init__(self, parent, id: int):
        QPushButton.__init__(self, str(id))
        self.parent = parent
        self.id: int = id
        self.clicked.connect(self.emit_jump_to_map)

    def emit_jump_to_map(self):
        # print("JumpButton::emit jump to map", self.id)
        self.jumpToMap.emit(self.id)

    jumpToMap = Signal(int)


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

    def add(self, map_id: int):
        # print("JumpList::add")
        if self.layout.count() == 0:
            label = QLabel("Jump to reaction on map:")
            self.layout.addWidget(label)

        jb = JumpButton(self, map_id)
        policy = QSizePolicy()
        policy.ShrinkFlag = True
        jb.setSizePolicy(policy)
        self.layout.addWidget(jb)
        self.setLayout(self.layout)

        jb.jumpToMap.connect(self.emit_jump_to_map)

    @ Slot(int)
    def emit_jump_to_map(self: JumpButton, id: int):
        print("JumpList::emit_jump_to_map", id)
        self.parent.emit_jump_to_map(id)

    jumpToMap = Signal(int)


class ReactionMask(QWidget):
    """The input mask for a reaction"""

    def __init__(self, parent):
        QWidget.__init__(self)

        self.parent = parent
        self.old = None
        self.is_valid = True
        self.changed = False

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
        self.rate_min = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.rate_min)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Rate max:")
        self.rate_max = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.rate_max)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Coefficient in obj. function:")
        self.coefficent = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.coefficent)
        layout.addItem(l)

        # l = QHBoxLayout()
        # label = QLabel("Variance of meassures:")
        # self.variance = QLineEdit()
        # l.addWidget(label)
        # l.addWidget(self.variance)
        # layout.addItem(l)

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

        l = QHBoxLayout()
        self.apply_button = QPushButton("apply changes")
        self.add_map_button = QPushButton("add reaction to map")
        self.map_combo = QComboBox()
        self.map_combo.setMaximumWidth(40)

        l.addWidget(self.apply_button)
        l.addWidget(self.add_map_button)
        l.addWidget(self.map_combo)
        layout.addItem(l)

        self.jump_list = JumpList(self)
        layout.addWidget(self.jump_list)

        self.setLayout(layout)

        self.delete_button.clicked.connect(self.delete_reaction)
        self.id.textEdited.connect(self.reaction_data_changed)
        self.name.textEdited.connect(self.reaction_data_changed)
        self.equation.textEdited.connect(self.reaction_data_changed)
        self.rate_min.textEdited.connect(self.reaction_data_changed)
        self.rate_max.textEdited.connect(self.reaction_data_changed)
        self.coefficent.textEdited.connect(self.reaction_data_changed)
        # self.variance.textEdited.connect(self.reaction_data_changed)
        self.annotation.itemChanged.connect(self.reaction_data_changed)
        self.apply_button.clicked.connect(self.apply)
        self.add_map_button.clicked.connect(self.add_to_map)

        self.update_state()

    def add_anno_row(self):
        i = self.annotation.rowCount()
        self.annotation.insertRow(i)
        self.changed = True

    def apply(self):
        if self.old is None:
            self.old = cobra.Reaction(
                id=self.id.text(), name=self.name.text())
            self.parent.appdata.project.cobra_py_model.add_reaction(self.old)

        try:
            self.old.id = self.id.text()
        except:
            msgBox = QMessageBox()
            msgBox.setText("Could not apply changes identifier already used.")
            msgBox.exec()
            pass
        else:
            self.old.name = self.name.text()
            self.old.build_reaction_from_string(self.equation.text())
            self.old.lower_bound = float(self.rate_min.text())
            self.old.upper_bound = float(self.rate_max.text())
            self.old.objective_coefficient = float(self.coefficent.text())
            self.old.annotation = {}
            rows = self.annotation.rowCount()
            for i in range(0, rows):
                key = self.annotation.item(i, 0).text()
                value = self.annotation.item(i, 1).text()
                print(key, value)
                self.old.annotation[key] = value

            self.changed = False
            self.changedReactionList.emit()

    def delete_reaction(self):
        self.parent.appdata.project.cobra_py_model.remove_reactions(
            [self.old], remove_orphans=True)
        self.hide()
        self.changedReactionList.emit()

    def add_to_map(self):
        # print("add to map")
        idx = self.map_combo.currentText()
        print("ReactionMask::add_to_map", idx)
        self.parent.appdata.project.maps[int(idx)-1]["boxes"][self.id.text()] = (
            100, 100, self.name.text())
        self.emit_jump_to_map(int(idx))
        self.update_state()

    def verify_id(self):

        palette = self.id.palette()
        role = self.id.foregroundRole()
        palette.setColor(role, Qt.black)
        self.id.setPalette(palette)

        with self.parent.appdata.project.cobra_py_model as model:
            try:
                r = cobra.Reaction(id=self.id.text())
                model.add_reaction(r)
            except:
                self.id.setStyleSheet("background: #ff9999")
                return False
            else:
                self.id.setStyleSheet("background: white")
                return True

    def verify_name(self):
        palette = self.name.palette()
        role = self.name.foregroundRole()
        palette.setColor(role, Qt.black)
        self.name.setPalette(palette)

        with self.parent.appdata.project.cobra_py_model as model:
            try:
                r = cobra.Reaction(id="testid", name=self.name.text())
                model.add_reaction(r)
            except:
                self.name.setStyleSheet("background: #ff9999")
                return False
            else:
                self.name.setStyleSheet("background: white")
                return True

    def verify_equation(self):

        palette = self.equation.palette()
        role = self.equation.foregroundRole()
        palette.setColor(role, Qt.black)
        self.equation.setPalette(palette)

        with self.parent.appdata.project.cobra_py_model as model:
            try:
                r = cobra.Reaction("test_id")
                model.add_reaction(r)
                r.build_reaction_from_string(self.equation.text())
            except:
                self.equation.setStyleSheet("background: #ff9999")
                return False
            else:
                self.equation.setStyleSheet("background: white")
                return True

    def verify_lowerbound(self):

        palette = self.rate_min.palette()
        role = self.rate_min.foregroundRole()
        palette.setColor(role, Qt.black)
        self.rate_min.setPalette(palette)
        try:
            x = float(self.rate_min.text())
        except:
            self.rate_min.setStyleSheet("background: #ff9999")
            return False
        else:
            self.rate_min.setStyleSheet("background: white")
            return True

    def verify_upperbound(self):

        palette = self.rate_max.palette()
        role = self.rate_max.foregroundRole()
        palette.setColor(role, Qt.black)
        self.rate_max.setPalette(palette)

        try:
            x = float(self.rate_max.text())
        except:
            self.rate_max.setStyleSheet("background: #ff9999")
            return False
        else:
            self.rate_max.setStyleSheet("background: white")
            return True

    def verify_coefficient(self):

        palette = self.coefficent.palette()
        role = self.coefficent.foregroundRole()
        palette.setColor(role, Qt.black)
        self.coefficent.setPalette(palette)

        try:
            x = float(self.coefficent.text())
        except:
            self.coefficent.setStyleSheet("background: #ff9999")
            return False
        else:
            self.coefficent.setStyleSheet("background: white")
            return True

    def verify_mask(self):
        if self.verify_id() & self.verify_name() & self.verify_equation() & self.verify_lowerbound() & self.verify_upperbound() & self.verify_coefficient():
            self.is_valid = True
        else:
            self.is_valid = False

    def reaction_data_changed(self):
        self.changed = True
        self.verify_mask()
        self.update_state()

    def update_state(self):
        # print("reaction_mask::update_state")
        self.jump_list.clear()
        c = 1
        for m in self.parent.appdata.project.maps:
            if self.id.text() in m["boxes"]:
                self.jump_list.add(c)
            c += 1

        if self.parent.new:
            self.apply_button.setText("add reaction")
            self.delete_button.hide()
        else:
            self.apply_button.setText("apply changes")
            self.delete_button.show()

            self.add_map_button.setEnabled(False)
            self.map_combo.clear()
            count = 1
            idx = 0
            for m in self.parent.appdata.project.maps:
                if self.id.text() not in m["boxes"]:
                    self.add_map_button.setEnabled(True)
                    self.map_combo.insertItem(idx, str(count))
                    idx += 1
                count += 1

        if self.is_valid & self.changed:
            self.apply_button.setEnabled(True)
        else:
            self.apply_button.setEnabled(False)

    def emit_jump_to_map(self, idx):
        # print("ReactionMask::emit_jump_to_map", idx, self.id.text())
        self.jumpToMap.emit(idx, self.id.text())

    jumpToMap = Signal(int, str)
    changedReactionList = Signal()
