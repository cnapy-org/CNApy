"""The CellNetAnalyzer reactions list"""
from PySide2.QtGui import QIcon, QColor, QPalette
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QLineEdit, QTextEdit, QLabel,
                               QHBoxLayout, QVBoxLayout,
                               QTreeWidget, QSizePolicy,
                               QTreeWidgetItem, QWidget, QPushButton, QMessageBox, QComboBox)
from PySide2.QtCore import Signal
import cobra


class ReactionList(QWidget):
    """A list of reaction"""

    def __init__(self, appdata):
        QWidget.__init__(self)
        self.appdata = appdata
        self.last_selected = None

        self.add_button = QPushButton("Add new reaction")
        self.add_button.setIcon(QIcon.fromTheme("list-add"))
        policy = QSizePolicy()
        policy.ShrinkFlag = True
        self.add_button.setSizePolicy(policy)

        self.reaction_list = QTreeWidget()
        self.reaction_list.setHeaderLabels(["Id", "Name", "Flux"])
        self.reaction_list.setSortingEnabled(True)

        for r in self.appdata.cobra_py_model.reactions:
            self.add_reaction(r)

        self.reaction_mask = ReactionMask(appdata)
        self.reaction_mask.hide()

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        l = QHBoxLayout()
        l.setAlignment(Qt.AlignRight)
        l.addWidget(self.add_button)
        self.layout.addItem(l)
        self.layout.addWidget(self.reaction_list)
        self.layout.addWidget(self.reaction_mask)
        self.setLayout(self.layout)

        self.reaction_list.currentItemChanged.connect(self.reaction_selected)
        self.reaction_mask.changedReactionList.connect(self.emit_changedModel)
        self.reaction_mask.changedMap.connect(self.emit_changedMap)

        self.add_button.clicked.connect(self.add_new_reaction)

    def clear(self):
        self.reaction_list.clear()
        self.reaction_mask.hide()

    def add_reaction(self, reaction):
        item = QTreeWidgetItem(self.reaction_list)
        item.setText(0, reaction.id)
        item.setText(1, reaction.name)
        if reaction.id in self.appdata.scen_values:
            self.set_flux_value(item, reaction.id, self.appdata.scen_values)
        elif reaction.id in self.appdata.comp_values:
            self.set_flux_value(item, reaction.id, self.appdata.comp_values)

        item.setData(3, 0, reaction)

    def set_flux_value(self, item, key, values):
        item.setText(2, str(values[key]))
        color = self.appdata.compute_color(values[key])
        item.setData(2, Qt.BackgroundRole, color)
        item.setForeground(2, Qt.black)

    def add_new_reaction(self):
        # print("ReactionList::add_new_reaction")
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
        # self.reaction_mask.comments.setText()

        self.reaction_mask.old = None
        self.reaction_mask.changed = False
        self.reaction_mask.update_state()

    def reaction_selected(self, item, _column):
        # print("reaction_selected")
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
            # self.reaction_mask.comments.setText()

            self.reaction_mask.old = reaction
            self.reaction_mask.changed = False
            self.reaction_mask.update_state()

    def emit_changedModel(self):
        self.last_selected = self.reaction_mask.id.text()
        # print("last selected", self.last_selected)
        self.changedModel.emit()

    def update(self):
        self.reaction_list.clear()
        for r in self.appdata.cobra_py_model.reactions:
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

    def emit_changedMap(self, idx: int):
        self.changedMap.emit(idx)

    itemActivated = Signal(str)
    changedModel = Signal()
    changedMap = Signal(int)


class ReactionMask(QWidget):
    """The input mask for a reaction"""

    def __init__(self, appdata):
        QWidget.__init__(self)
        self.appdata = appdata
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

        # l = QVBoxLayout()
        # label = QLabel("Notes and Comments:")
        # self.comments = QTextEdit()
        # self.comments.setFixedHeight(200)
        # l.addWidget(label)
        # l.addWidget(self.comments)
        # layout.addItem(l)

        l = QHBoxLayout()
        self.apply_button = QPushButton("apply changes")
        self.add_map_button = QPushButton("add reaction to map")
        self.map_combo = QComboBox()
        self.map_combo.setMaximumWidth(40)

        l.addWidget(self.apply_button)
        l.addWidget(self.add_map_button)
        l.addWidget(self.map_combo)
        layout.addItem(l)

        self.setLayout(layout)

        self.delete_button.clicked.connect(self.delete_reaction)
        self.id.textEdited.connect(self.reaction_data_changed)
        self.name.textEdited.connect(self.reaction_data_changed)
        self.equation.textEdited.connect(self.reaction_data_changed)
        self.rate_min.textEdited.connect(self.reaction_data_changed)
        self.rate_max.textEdited.connect(self.reaction_data_changed)
        self.coefficent.textEdited.connect(self.reaction_data_changed)
        # self.variance.textEdited.connect(self.reaction_data_changed)
        # self.comments.textEdited.connect(self.reaction_data_changed)
        self.apply_button.clicked.connect(self.apply)
        self.add_map_button.clicked.connect(self.add_to_map)

        self.update_state()

    def apply(self):
        if self.old is None:
            self.old = cobra.Reaction(
                id=self.id.text(), name=self.name.text())
            self.appdata.cobra_py_model.add_reaction(self.old)

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
            print("TODO save coefficient")
            # self.old.objective_coefficient = float(self.coefficent.text())

            self.changed = False
            self.changedReactionList.emit()

    def delete_reaction(self):
        self.appdata.cobra_py_model.remove_reactions([self.old])
        self.hide()
        self.changedReactionList.emit()

    def add_to_map(self):
        idx = self.map_combo.currentText()
        print("ReactionMask::add_to_map", idx)
        self.appdata.maps[int(idx)-1]["boxes"][self.id.text()] = (
            100, 100, self.name.text())
        self.changedMap.emit(int(idx)-1)
        self.update_state()

    def verify_id(self):

        palette = self.id.palette()
        role = self.id.foregroundRole()
        palette.setColor(role, Qt.black)
        self.id.setPalette(palette)

        with self.appdata.cobra_py_model as model:
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

        with self.appdata.cobra_py_model as model:
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

        with self.appdata.cobra_py_model as model:
            r = cobra.Reaction("test_id")
            model.add_reaction(r)
            try:
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
        if self.old is None:
            self.apply_button.setText("add reaction")
            self.delete_button.hide()
        else:
            self.apply_button.setText("apply changes")
            self.delete_button.show()

            self.add_map_button.setEnabled(False)
            self.map_combo.clear()
            count = 1
            idx = 0
            for m in self.appdata.maps:
                if self.id.text() not in m["boxes"]:
                    self.add_map_button.setEnabled(True)
                    self.map_combo.insertItem(idx, str(count))
                    idx += 1
                count += 1

        if self.is_valid & self.changed:
            self.apply_button.setEnabled(True)
        else:
            self.apply_button.setEnabled(False)

    changedReactionList = Signal()
    changedMap = Signal(int)
