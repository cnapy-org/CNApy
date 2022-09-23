"""The metabolite list"""

import cobra
from qtpy.QtCore import Qt, Signal, Slot
from qtpy.QtGui import QColor, QIcon
from qtpy.QtWidgets import (QAction, QHBoxLayout, QHeaderView, QLabel,
                            QLineEdit, QMenu, QMessageBox, QPushButton, QSizePolicy,
                            QSplitter, QTableWidget, QTableWidgetItem,
                            QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from cnapy.appdata import AppData
from cnapy.utils import SignalThrottler, turn_red, turn_white
from cnapy.utils_for_cnapy_api import check_identifiers_org_entry
from cnapy.gui_elements.reaction_table_widget import ModelElementType, ReactionTableWidget


class MetaboliteList(QWidget):
    """A list of metabolites"""

    def __init__(self, appdata: AppData):
        QWidget.__init__(self)
        self.appdata = appdata
        self.last_selected = None

        self.metabolite_list = QTreeWidget()
        self.metabolite_list.setHeaderLabels(["Id", "Name"])
        self.metabolite_list.setSortingEnabled(True)

        for m in self.appdata.project.cobra_py_model.metabolites:
            self.add_metabolite(m)
        self.metabolite_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.metabolite_list.customContextMenuRequested.connect(
            self.on_context_menu)

        # create context menu
        self.pop_menu = QMenu(self.metabolite_list)
        in_out_fluxes_action = QAction(
            'compute in/out fluxes for this metabolite', self.metabolite_list)
        self.pop_menu.addAction(in_out_fluxes_action)
        in_out_fluxes_action.triggered.connect(self.emit_in_out_fluxes_action)

        self.metabolite_mask = MetabolitesMask(self, appdata)
        self.metabolite_mask.hide()

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Vertical)
        self.splitter.addWidget(self.metabolite_list)
        self.splitter.addWidget(self.metabolite_mask)
        self.layout.addWidget(self.splitter)
        self.setLayout(self.layout)

        self.metabolite_list.currentItemChanged.connect(
            self.metabolite_selected)
        self.metabolite_mask.metaboliteChanged.connect(
            self.handle_changed_metabolite)
        self.metabolite_mask.jumpToReaction.connect(
            self.emit_jump_to_reaction)

    def clear(self):
        self.metabolite_list.clear()
        self.metabolite_mask.hide()

    def add_metabolite(self, metabolite):
        item = QTreeWidgetItem(self.metabolite_list)
        item.setText(0, metabolite.id)
        item.setText(1, metabolite.name)
        item.setData(2, 0, metabolite)

    def on_context_menu(self, point):
        if len(self.appdata.project.cobra_py_model.metabolites) > 0:
            self.pop_menu.exec_(self.mapToGlobal(point))

    def update_annotations(self, annotation):

        self.metabolite_mask.annotation.itemChanged.disconnect(
            self.metabolite_mask.throttler.throttle)
        c = self.metabolite_mask.annotation.rowCount()
        for i in range(0, c):
            self.metabolite_mask.annotation.removeRow(0)
        i = 0
        for key in annotation:
            self.metabolite_mask.annotation.insertRow(i)
            keyl = QTableWidgetItem(key)
            iteml = QTableWidgetItem(str(annotation[key]))
            self.metabolite_mask.annotation.setItem(i, 0, keyl)
            self.metabolite_mask.annotation.setItem(i, 1, iteml)
            i += 1

        self.metabolite_mask.annotation.itemChanged.connect(
            self.metabolite_mask.throttler.throttle)

    def handle_changed_metabolite(self, metabolite: cobra.Metabolite, affected_reactions):
        # Update metabolite item in list
        root = self.metabolite_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            if item.data(2, 0) == metabolite:
                item.setText(0, metabolite.id)
                item.setText(1, metabolite.name)
                break

        self.last_selected = self.metabolite_mask.id.text()
        self.metaboliteChanged.emit(metabolite, affected_reactions)

    def update_selected(self, string):
        root = self.metabolite_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            item.setHidden(True)

        for item in self.metabolite_list.findItems(string, Qt.MatchContains, 0):
            item.setHidden(False)
        for item in self.metabolite_list.findItems(string, Qt.MatchContains, 1):
            item.setHidden(False)

    def metabolite_selected(self, item, _column):
        if item is None:
            self.metabolite_mask.hide()
        else:
            self.metabolite_mask.show()
            metabolite: cobra.Metabolite = item.data(2, 0)

            self.metabolite_mask.metabolite = metabolite

            self.metabolite_mask.id.setText(metabolite.id)
            self.metabolite_mask.name.setText(metabolite.name)
            self.metabolite_mask.formula.setText(metabolite.formula)
            if metabolite.charge is None:
                pass
            else:
                self.metabolite_mask.charge.setText(str(metabolite.charge))
            self.metabolite_mask.compartment.setText(metabolite.compartment)
            self.update_annotations(metabolite.annotation)
            self.metabolite_mask.changed = False

            turn_white(self.metabolite_mask.id)
            turn_white(self.metabolite_mask.name)
            turn_white(self.metabolite_mask.formula)
            turn_white(self.metabolite_mask.charge)
            turn_white(self.metabolite_mask.compartment)
            self.metabolite_mask.is_valid = True
            self.metabolite_mask.reactions.update_state(self.metabolite_mask.id.text(), self.metabolite_mask.metabolite_list)

    def update(self):
        self.metabolite_list.clear()
        for m in self.appdata.project.cobra_py_model.metabolites:
            self.add_metabolite(m)

        if self.last_selected is None:
            pass
        else:
            items = self.metabolite_list.findItems(
                self.last_selected, Qt.MatchExactly)

            for i in items:
                self.metabolite_list.setCurrentItem(i)
                break

    def set_current_item(self, key):
        self.last_selected = key
        self.update()

    def emit_jump_to_reaction(self, reaction):
        self.jumpToReaction.emit(reaction)

    def emit_in_out_fluxes_action(self):
        self.computeInOutFlux.emit(self.metabolite_list.currentItem().text(0))

    itemActivated = Signal(str)
    metaboliteChanged = Signal(cobra.Metabolite, object)
    jumpToReaction = Signal(str)
    computeInOutFlux = Signal(str)


class MetabolitesMask(QWidget):
    """The input mask for a metabolites"""

    def __init__(self, metabolite_list: MetaboliteList, appdata):
        QWidget.__init__(self)
        self.metabolite_list: MetaboliteList = metabolite_list
        self.appdata = appdata
        self.metabolite = None
        self.is_valid = True
        self.changed = False
        self.setAcceptDrops(False)

        layout = QVBoxLayout()

        l = QHBoxLayout()
        label = QLabel("Id:")
        self.id = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.id)

        self.delete_button = QPushButton("Delete metabolite")
        self.delete_button.setIcon(QIcon.fromTheme("edit-delete"))
        self.delete_button.setToolTip(
            "Delete this metabolite and remove it from associated reactions.")
        policy = QSizePolicy()
        policy.ShrinkFlag = True
        self.delete_button.setSizePolicy(policy)
        l.addWidget(self.delete_button)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Name:")
        self.name = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.name)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Formula:")
        self.formula = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.formula)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Compartment:")
        self.compartment = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.compartment)

        label = QLabel(" Charge:")
        self.charge = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.charge)
        layout.addItem(l)

        l = QVBoxLayout()

        l3 = QHBoxLayout()
        label = QLabel("Annotations:")
        l3.addWidget(label)

        check_button = QPushButton("identifiers.org check")
        check_button.setIcon(QIcon.fromTheme("list-add"))
        policy = QSizePolicy()
        policy.ShrinkFlag = True
        check_button.setSizePolicy(policy)
        check_button.clicked.connect(self.check_in_identifiers_org)
        l3.addWidget(check_button)

        l.addItem(l3)

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
        label = QLabel("Reactions using this metabolite:")
        l.addWidget(label)
        l2 = QHBoxLayout()
        self.reactions = ReactionTableWidget (self.appdata, ModelElementType.METABOLITE)
        l2.addWidget(self.reactions)
        l.addItem(l2)
        self.reactions.itemDoubleClicked.connect(self.emit_jump_to_reaction)
        layout.addItem(l)

        self.setLayout(layout)

        self.delete_button.clicked.connect(self.delete_metabolite)

        self.throttler = SignalThrottler(500)
        self.throttler.triggered.connect(self.metabolites_data_changed)

        self.id.textEdited.connect(self.throttler.throttle)
        self.name.textEdited.connect(self.throttler.throttle)
        self.formula.textEdited.connect(self.throttler.throttle)
        self.charge.textEdited.connect(self.throttler.throttle)
        self.compartment.editingFinished.connect(self.metabolites_data_changed)
        self.annotation.itemChanged.connect(self.throttler.throttle)
        self.validate_mask()

    def delete_metabolite(self):
        self.hide()
        # in C++ the currentItem can just be destructed but in Python this is more convoluted
        current_row_index = self.metabolite_list.metabolite_list.currentIndex().row()
        self.metabolite_list.metabolite_list.setCurrentItem(None)
        affected_reactions = self.metabolite.reactions  # remember these before removal
        self.metabolite.remove_from_model()
        self.metabolite_list.last_selected = None
        self.metabolite_list.metabolite_list.takeTopLevelItem(
            current_row_index)
        self.appdata.window.unsaved_changes()
        self.appdata.window.setFocus()
        self.metaboliteDeleted.emit(self.metabolite, affected_reactions)

    def add_anno_row(self):
        i = self.annotation.rowCount()
        self.annotation.insertRow(i)
        self.changed = True

    def apply(self):
        try:
            self.metabolite.id = self.id.text()
        except ValueError:
            turn_red(self.id)
            QMessageBox.information(
                self, 'Invalid id', 'Could not apply changes identifier ' +
                self.id.text()+' already used.')
        else:
            self.metabolite.name = self.name.text()
            self.metabolite.formula = self.formula.text()
            if self.charge.text() == "":
                self.metabolite.charge = None
            else:
                self.metabolite.charge = int(self.charge.text())
            self.metabolite.compartment = self.compartment.text()
            self.metabolite.annotation = {}
            rows = self.annotation.rowCount()
            for i in range(0, rows):
                key = self.annotation.item(i, 0).text()
                if self.annotation.item(i, 1) is None:
                    value = ""
                else:
                    value = self.annotation.item(i, 1).text()

                self.metabolite.annotation[key] = value

            self.changed = False
            self.metaboliteChanged.emit(
                self.metabolite, self.metabolite.reactions)

    def validate_id(self):
        with self.appdata.project.cobra_py_model as model:
            text = self.id.text()
            if text == "":
                turn_red(self.id)
                return False
            if ' ' in text:
                turn_red(self.id)
                return False
            try:
                m = cobra.Metabolite(id=self.id.text())
                model.add_metabolites([m])
            except ValueError:
                turn_red(self.id)
                return False
            else:
                turn_white(self.id)
                return True

    def check_in_identifiers_org(self):
        self.setCursor(Qt.BusyCursor)
        rows = self.annotation.rowCount()
        invalid_red = QColor(255, 0, 0)
        for i in range(0, rows):
            if self.annotation.item(i, 0) is not None:
                key = self.annotation.item(i, 0).text()
            else:
                key = ""
            if self.annotation.item(i, 1) is not None:
                values = self.annotation.item(i, 1).text()
            else:
                values = ""
            if (key == "") or (values == ""):
                continue

            if values.startswith("["):
                values = values.replace("', ", "'\b,").replace('", ', '"\b,').replace("[", "")\
                               .replace("]", "").replace("'", "").replace('"', "")
                values = values.split("\b,")
            else:
                values = [values]

            for value in values:
                identifiers_org_result = check_identifiers_org_entry(
                    key, value)

                if identifiers_org_result.connection_error:
                    msgBox = QMessageBox()
                    msgBox.setWindowTitle("Connection error!")
                    msgBox.setTextFormat(Qt.RichText)
                    msgBox.setText(
                        "<p>identifiers.org could not be accessed. Either the internet connection isn't working or the server is currently down.</p>")
                    msgBox.setIcon(QMessageBox.Warning)
                    msgBox.exec()
                    break

                if (not identifiers_org_result.is_key_value_pair_valid) and (":" in value):
                    split_value = value.split(":")
                    identifiers_org_result = check_identifiers_org_entry(
                        split_value[0], split_value[1])

                if not identifiers_org_result.is_key_valid:
                    self.annotation.item(i, 0).setBackground(invalid_red)

                if not identifiers_org_result.is_key_value_pair_valid:
                    self.annotation.item(i, 1).setBackground(invalid_red)

                if not identifiers_org_result.is_key_value_pair_valid:
                    break
            self.setCursor(Qt.ArrowCursor)

    def validate_name(self):
        with self.appdata.project.cobra_py_model as model:
            try:
                m = cobra.Metabolite(id="test_id", name=self.name.text())
                model.add_metabolites([m])
            except ValueError:
                turn_red(self.name)
                return False
            else:
                turn_white(self.name)
                return True

    def validate_formula(self):
        return True

    def validate_charge(self):
        try:
            if self.charge.text() != "":
                _x = int(self.charge.text())
        except ValueError:
            turn_red(self.charge)
            return False
        else:
            turn_white(self.charge)
            return True

    def validate_compartment(self):
        try:
            if ' ' in self.compartment.text():
                turn_red(self.compartment)
                return False
            if '-' in self.compartment.text():
                turn_red(self.compartment)
                return False
            _m = cobra.Metabolite(id="test_id", name=self.compartment.text())
        except ValueError:
            turn_red(self.compartment)
            return False
        else:
            turn_white(self.compartment)
            if self.compartment.text() != "" and self.compartment.text() not in self.appdata.project.cobra_py_model.compartments:
                # block signals triggered by appearance of message_box
                self.compartment.blockSignals(True)
                message_box = QMessageBox()
                message_box.setText(
                    "The compartment "+self.compartment.text() + " does not yet exist.")
                message_box.setInformativeText(
                    "Do you want to create the compartment?")
                message_box.setStandardButtons(
                    QMessageBox.Ok | QMessageBox.Cancel)
                message_box.setDefaultButton(QMessageBox.Ok)
                ret = message_box.exec()
                self.compartment.blockSignals(False)

                if ret == QMessageBox.Cancel:
                    metabolite = self.appdata.project.cobra_py_model.metabolites.get_by_id(
                        self.id.text())
                    self.compartment.setText(metabolite.compartment)

            return True

    def validate_mask(self):
        valid_id = self.validate_id()
        valid_name = self.validate_name()
        valid_formula = self.validate_formula()
        valid_charge = self.validate_charge()
        valid_compartment = self.validate_compartment()
        if valid_id & valid_name & valid_formula & valid_charge & valid_compartment:
            self.is_valid = True
        else:
            self.is_valid = False

    def metabolites_data_changed(self):
        self.changed = True
        self.validate_mask()
        if self.is_valid:
            self.apply()
            self.reactions.update_state(self.id.text(), self.metabolite_list)

    @Slot(QTableWidgetItem)
    def emit_jump_to_reaction(self, item: QTableWidgetItem):
        self.jumpToReaction.emit(item.text())

    jumpToReaction = Signal(str)
    metaboliteChanged = Signal(cobra.Metabolite, object)
    metaboliteDeleted = Signal(cobra.Metabolite, object)
