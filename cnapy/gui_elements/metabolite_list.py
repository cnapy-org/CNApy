"""The metabolite list"""

import cobra
from qtpy.QtCore import Qt, QPoint, Signal, Slot
from qtpy.QtGui import QColor, QGuiApplication, QIcon
from qtpy.QtWidgets import (QAction, QHBoxLayout, QHeaderView, QLabel,
                            QLineEdit, QMenu, QMessageBox, QPushButton, QSizePolicy,
                            QSplitter, QTableWidget, QTableWidgetItem,
                            QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from cnapy.appdata import AppData, ModelItemType
from cnapy.gui_elements.annotation_widget import AnnotationWidget
from cnapy.utils import SignalThrottler, turn_red, turn_white, update_selected
from cnapy.utils_for_cnapy_api import check_identifiers_org_entry
from cnapy.gui_elements.reaction_table_widget import ModelElementType, ReactionTableWidget
from enum import IntEnum

class MetaboliteListColumn(IntEnum):
    Id = 0
    Name = 1
    Concentration = 2


class MetaboliteListItem(QTreeWidgetItem):
    """ For custom sorting of columns """

    def __init__(self, parent: QTreeWidget):
        # although QTreeWidgetItem is constructed with the metabolite_list as parent this
        # will not be its parent() which is None because it is a top-level item
        QTreeWidgetItem.__init__(self, parent)

    def __lt__(self, other):
        """ overrides QTreeWidgetItem::operator< """
        column = self.treeWidget().sortColumn()
        if column == MetaboliteListColumn.Concentration:
            try:
                current_value = float(self.text(column))
            except ValueError:
                current_value = -float("inf")
            try:
                other_value = float(other.text(column))
            except ValueError:
                other_value = -float("inf")
            return current_value < other_value
        else:  # use Qt default comparison for the other columns
#            return super().__lt__(other) # infinite recursion with PySide2, __lt__ is a virtual function of QTreeWidgetItem
            return self.text(column) < other.text(column)


class MetaboliteList(QWidget):
    """A list of metabolites"""

    def __init__(self, central_widget):
        QWidget.__init__(self)
        self.appdata: AppData = central_widget.appdata
        self.central_widget = central_widget
        self.last_selected = None

        self.metabolite_list = QTreeWidget()

        self.header_labels = [MetaboliteListColumn(i).name for i in range(len(MetaboliteListColumn))]
        self.metabolite_list.setHeaderLabels(self.header_labels)
        self.visible_column = [True]*len(self.header_labels)
        self.metabolite_list.setSortingEnabled(True)
        self.metabolite_list.sortByColumn(MetaboliteListColumn.Id, Qt.AscendingOrder)

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

        self.metabolite_mask = MetabolitesMask(self, self.appdata)
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
        self.metabolite_list.header().setContextMenuPolicy(Qt.CustomContextMenu)
        self.metabolite_list.header().customContextMenuRequested.connect(self.header_context_menu)

    def clear(self):
        self.metabolite_list.clear()
        self.metabolite_mask.hide()

    def add_metabolite(self, metabolite):
        item = MetaboliteListItem(self.metabolite_list)
        item.setText(MetaboliteListColumn.Id, metabolite.id)
        item.setText(MetaboliteListColumn.Name, metabolite.name)
        if metabolite.id in self.appdata.project.conc_values.keys():
            item.setText(MetaboliteListColumn.Concentration, str(self.appdata.project.conc_values[metabolite.id]))
        item.setData(3, 0, metabolite)

    def on_context_menu(self, point):
        if len(self.appdata.project.cobra_py_model.metabolites) > 0:
            self.pop_menu.exec_(self.mapToGlobal(point))

    def update_annotations(self, annotation):
        self.metabolite_mask.annotation_widget.update_annotations(annotation)

    def handle_changed_metabolite(self, metabolite: cobra.Metabolite, affected_reactions, previous_id: str):
        # Update metabolite item in list
        root = self.metabolite_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            if item.data(3, 0) == metabolite:
                item.setText(MetaboliteListColumn.Id, metabolite.id)
                item.setText(MetaboliteListColumn.Name, metabolite.name)
                if metabolite.id in self.appdata.project.conc_values.keys():
                    item.setText(MetaboliteListColumn.Concentration, str(self.appdata.project.conc_values[metabolite.id]))
                break

        self.last_selected = self.metabolite_mask.id.text()
        self.metaboliteChanged.emit(metabolite, affected_reactions, previous_id)
        self.metabolite_list.resizeColumnToContents(MetaboliteListColumn.Id)
        self.metabolite_list.resizeColumnToContents(MetaboliteListColumn.Name)
        self.metabolite_list.resizeColumnToContents(MetaboliteListColumn.Concentration)

    def update_selected(self, string, with_annotations=True):
        return update_selected(
            string=string,
            with_annotations=with_annotations,
            model_elements=self.appdata.project.cobra_py_model.metabolites,
            element_list=self.metabolite_list,
        )

    def metabolite_selected(self, item, _column):
        if item is None:
            self.metabolite_mask.hide()
        else:
            self.metabolite_mask.show()
            metabolite: cobra.Metabolite = item.data(3, 0)

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
            self.central_widget.add_model_item_to_history(metabolite.id, metabolite.name, ModelItemType.Metabolite)

    def update(self):
        self.metabolite_list.clear()
        for m in self.appdata.project.cobra_py_model.metabolites:
            self.add_metabolite(m)

        if self.last_selected is None:
            self.metabolite_list.setCurrentItem(None)
        else:
            items = self.metabolite_list.findItems(
                self.last_selected, Qt.MatchExactly)

            for i in items:
                self.metabolite_list.setCurrentItem(i)
                self.metabolite_list.scrollToItem(i)
                break

    def set_current_item(self, key):
        self.last_selected = key
        self.update()

    def emit_jump_to_reaction(self, reaction):
        self.jumpToReaction.emit(reaction)

    def emit_in_out_fluxes_action(self):
        self.computeInOutFlux.emit(self.metabolite_list.currentItem().text(0))

    @Slot()
    def copy_to_clipboard(self):
        clipboard = QGuiApplication.clipboard()
        visible_columns = [j.value for j in MetaboliteListColumn if not self.metabolite_list.isColumnHidden(j)]
        table = ["\t".join([MetaboliteListColumn(j).name for j in visible_columns])]
        root = self.metabolite_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            line = []
            for j in visible_columns:
                line.append(item.text(j))
            table.append("\t".join(line))
        clipboard.setText("\r".join(table))

    @Slot(bool)
    def set_column_visibility_action(self, visible):
        col_idx = self.sender().data()
        self.metabolite_list.setColumnHidden(col_idx, not visible)
        self.visible_column[col_idx] = visible

    @Slot(QPoint)
    def header_context_menu(self, position):
        menu = QMenu(self.metabolite_list.header())
        for col_idx in range(1, len(self.header_labels)):
            action = menu.addAction(self.header_labels[col_idx])
            action.setCheckable(True)
            action.setChecked(self.visible_column[col_idx])
            action.setData(col_idx)
            action.triggered.connect(self.set_column_visibility_action)
        menu.addSeparator()
        action = menu.addAction("Copy table to system clipboard")
        action.triggered.connect(self.copy_to_clipboard)
        menu.exec_(self.metabolite_list.header().mapToGlobal(position))

    itemActivated = Signal(str)
    metaboliteChanged = Signal(cobra.Metabolite, object, str)
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

        self.throttler = SignalThrottler(500)
        self.throttler.triggered.connect(self.metabolites_data_changed)

        self.annotation_widget = AnnotationWidget(self)

        layout.addItem(self.annotation_widget)

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


        self.id.textEdited.connect(self.throttler.throttle)
        self.name.textEdited.connect(self.throttler.throttle)
        self.formula.textEdited.connect(self.throttler.throttle)
        self.charge.textEdited.connect(self.throttler.throttle)
        self.compartment.editingFinished.connect(self.metabolites_data_changed)
        self.annotation_widget.deleteAnnotation.connect(
            self.delete_selected_annotation
        )
        # self.validate_mask()

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
        self.metaboliteDeleted.emit(self.metabolite, affected_reactions, self.metabolite.id)

    def delete_selected_annotation(self, identifier_key):
        try:
            del(self.metabolite.annotation[identifier_key])
            self.appdata.window.unsaved_changes()
        except IndexError:
            pass

    def apply(self):
        previous_id = self.metabolite.id
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
            self.annotation_widget.apply_annotation(self.metabolite)

            self.changed = False
            self.metaboliteChanged.emit(self.metabolite, self.metabolite.reactions, previous_id)

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
    metaboliteChanged = Signal(cobra.Metabolite, object, str)
    metaboliteDeleted = Signal(cobra.Metabolite, object, str)
