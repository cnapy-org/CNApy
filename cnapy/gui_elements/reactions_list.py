"""The reactions list"""
from math import isclose
import io
import traceback
from enum import IntEnum

import cobra
from qtpy.QtCore import QMimeData, Qt, Signal, Slot, QPoint
from qtpy.QtGui import QColor, QDrag, QIcon
from qtpy.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                            QMessageBox, QPushButton, QSizePolicy, QSplitter,
                            QTableWidget, QTableWidgetItem, QTreeWidget,
                            QTreeWidgetItem, QVBoxLayout, QWidget, QMenu,
                            QAbstractItemView)

from cnapy.appdata import AppData
from cnapy.utils import SignalThrottler, turn_red, turn_white
from cnapy.utils_for_cnapy_api import check_identifiers_org_entry
from cnapy.gui_elements.map_view import validate_value

class ReactionListColumn(IntEnum):
    Id = 0
    Name = 1
    Scenario = 2
    Flux = 3
    LB = 4
    UB = 5

class DragableTreeWidget(QTreeWidget):
    '''A list of dragable reaction items'''

    def mouseMoveEvent(self, _event):
        item = self.currentItem()
        if item is not None:
            mime_data = QMimeData()
            mime_data.setText(item.reaction.id)
            drag = QDrag(self)
            drag.setMimeData(mime_data)
            drag.exec_(Qt.CopyAction | Qt.MoveAction, Qt.CopyAction)


class ReactionListItem(QTreeWidgetItem):
    """ For custom sorting of columns """

    def __init__(self, reaction: cobra.Reaction, parent: QTreeWidget):
        # although QTreeWidgetItem is constructed with the reaction_list as parent this
        # will not be its parent() which is None because it is a top-level item
        QTreeWidgetItem.__init__(self, parent)
        self.reaction = reaction
        self.flux_sort_val = -float('inf')
        self.lb_val = -float('inf')
        self.ub_val = float('inf')

    def set_flux_data(self, text, value):
        self.setText(ReactionListColumn.Flux, text)
        if isinstance(value, (int, float)):
            self.flux_sort_val = abs(value)
        else:  # assumes value is a pair of numbers
            self.flux_sort_val = value[1] - value[0]

    def reset_flux_data(self):
        self.setText(ReactionListColumn.Flux, "")
        self.flux_sort_val = -float('inf')
        self.lb_val = -float('inf')
        self.ub_val = float('inf')

    def __lt__(self, other):
        """ overrides QTreeWidgetItem::operator< """
        column = self.treeWidget().sortColumn()
        if column == ReactionListColumn.Flux:
            return self.flux_sort_val < other.flux_sort_val
        elif column == ReactionListColumn.LB:
            return self.lb_val < other.lb_val
        elif column == ReactionListColumn.UB:
            return self.ub_val < other.ub_val
        else:  # use Qt default comparison for the other columns
#            return super().__lt__(other) # infinite recursion with PySide2, __lt__ is a virtual function of QTreeWidgetItem
            return self.text(column) < other.text(column)

class ReactionList(QWidget):
    """A list of reaction"""

    def __init__(self, central_widget):
        QWidget.__init__(self)
        self.appdata: AppData = central_widget.appdata
        self.central_widget = central_widget
        self.last_selected = None
        self.reaction_counter = 1

        self.add_button = QPushButton("Add new reaction")
        self.add_button.setIcon(QIcon.fromTheme("list-add"))
        policy = QSizePolicy()
        policy.ShrinkFlag = True
        self.add_button.setSizePolicy(policy)

        self.reaction_list = DragableTreeWidget()
        self.reaction_list.setDragEnabled(True)
        self.reaction_list.setColumnCount(len(ReactionListColumn))
        self.reaction_list.setRootIsDecorated(False)
        self.reaction_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.reaction_list.customContextMenuRequested.connect(self.context_menu)
        self.header_labels = [ReactionListColumn(i).name for i in range(len(ReactionListColumn))]
        self.reaction_list.setHeaderLabels(self.header_labels)
        # heuristic initial column widths
        self.reaction_list.resizeColumnToContents(ReactionListColumn.Scenario)
        self.reaction_list.resizeColumnToContents(ReactionListColumn.LB)
        width = self.reaction_list.header().sectionSize(ReactionListColumn.Scenario) + \
                self.reaction_list.header().sectionSize(ReactionListColumn.LB)
        self.reaction_list.header().resizeSection(ReactionListColumn.Id, width)
        self.reaction_list.header().resizeSection(ReactionListColumn.Name, width)
        self.visible_column = [True]*len(self.header_labels)
        self.reaction_list.setSortingEnabled(True)
        self.reaction_list.header().setContextMenuPolicy(Qt.CustomContextMenu)
        self.reaction_list.header().customContextMenuRequested.connect(self.header_context_menu)

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
        self.reaction_list.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.reaction_list.itemClicked.connect(self.handle_item_clicked)
        self.reaction_list.itemChanged.connect(self.handle_item_changed)

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

    def add_reaction(self, reaction: cobra.Reaction) -> ReactionListItem:
        ''' create a new item in the reaction list'''
        self.reaction_list.clearSelection()
        item = ReactionListItem(reaction, self.reaction_list)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        item.setText(0, reaction.id)
        item.setText(1, reaction.name)
        text = "Id: " + reaction.id + "\nName: " + reaction.name \
            + "\nEquation: " + reaction.build_reaction_string()\
            + "\nLowerbound: " + str(reaction.lower_bound) \
            + "\nUpper bound: " + str(reaction.upper_bound) \
            + "\nObjective coefficient: " + str(reaction.objective_coefficient)
        item.setToolTip(ReactionListColumn.Id, text)
        item.setToolTip(ReactionListColumn.Name, text)
        self.update_item(item)
        return item

    def update_item(self, item: ReactionListItem):
        ''' update Scenario, Flux, LB, UB columns '''
        if self.appdata.project.comp_values_type == 0:
            self.set_flux_value(item)
        self.set_bounds_values(item)
        if item.reaction.id in self.appdata.project.scen_values:
            scen_background_color = self.appdata.scen_color
            (vl, vu) = self.appdata.project.scen_values[item.reaction.id]
            scen_text = self.appdata.format_flux_value(vl)
            if vl != vu:
                scen_text = scen_text+", "+self.appdata.format_flux_value(vu)
        else:
            scen_background_color = Qt.white
            scen_text = ""
        item.setBackground(ReactionListColumn.Scenario, scen_background_color)
        item.setText(ReactionListColumn.Scenario, scen_text)

    def set_flux_value(self, item: ReactionListItem):
        key = item.reaction.id
        if key in self.appdata.project.comp_values.keys():
            (vl, vu) = self.appdata.project.comp_values[key]

            # We differentiate special cases like (vl==vu)
            if isclose(vl, vu, abs_tol=self.appdata.abs_tol):
                if self.appdata.modes_coloring:
                    if vl == 0:
                        background_color = Qt.red
                    else:
                        background_color = Qt.green
                else:
                    background_color = self.appdata.comp_color

                item.set_flux_data(self.appdata.format_flux_value(vl), vl)
            else:
                if isclose(vl, 0.0, abs_tol=self.appdata.abs_tol):
                    background_color = self.appdata.special_color_1
                elif isclose(vu, 0.0, abs_tol=self.appdata.abs_tol):
                    background_color = self.appdata.special_color_1
                elif vl <= 0 and vu >= 0:
                    background_color = self.appdata.special_color_1
                else:
                    background_color = self.appdata.special_color_2
                item.set_flux_data(self.appdata.format_flux_value(vl) + ", " +
                                 self.appdata.format_flux_value(vu), (vl, vu))
        else:
            item.reset_flux_data()
            background_color = Qt.white
        item.setBackground(ReactionListColumn.Flux, background_color)
        item.setForeground(ReactionListColumn.Flux, Qt.black)

    def set_bounds_values(self, item):
        key = item.reaction.id
        if key in self.appdata.project.fva_values.keys():
            (vl, vu) = self.appdata.project.fva_values[key]
            if isclose(vl, vu, abs_tol=self.appdata.abs_tol):
                if self.appdata.modes_coloring:
                    if vl == 0:
                        background_color = Qt.red
                    else:
                        background_color = Qt.green
                else:
                        background_color = self.appdata.comp_color
            else:
                if isclose(vl, 0.0, abs_tol=self.appdata.abs_tol):
                    background_color = self.appdata.special_color_1
                elif isclose(vu, 0.0, abs_tol=self.appdata.abs_tol):
                    background_color = self.appdata.special_color_1
                elif vl <= 0 and vu >= 0:
                    background_color = self.appdata.special_color_1
                else:
                    background_color = self.appdata.special_color_2
        else:
            vl = item.reaction.lower_bound
            vu = item.reaction.upper_bound
            background_color = Qt.white
        item.setBackground(ReactionListColumn.LB, background_color)
        item.lb_val = vl
        item.setText(ReactionListColumn.LB, self.appdata.format_flux_value(vl))
        item.setBackground(ReactionListColumn.UB, background_color)
        item.ub_val = vu
        item.setText(ReactionListColumn.UB, self.appdata.format_flux_value(vu))

    def add_new_reaction(self):
        self.reaction_mask.show()
        while True:
            name = "rxn_"+str(self.reaction_counter)
            self.reaction_counter += 1
            if name not in self.appdata.project.cobra_py_model.reactions:
                break
        reaction = cobra.Reaction(name)
        self.appdata.project.cobra_py_model.add_reactions([reaction])
        self.reaction_list.blockSignals(True)
        item = self.add_reaction(reaction)
        self.reaction_list.blockSignals(False)
        self.reaction_selected(item)
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

    def reaction_selected(self, item: ReactionListItem):
        if item is None:
            self.reaction_mask.hide()
        elif self.reaction_list.currentColumn() != ReactionListColumn.Scenario or self.splitter.sizes()[1] > 0:
            item.setSelected(True)
            self.reaction_mask.show()
            reaction: cobra.Reaction = item.reaction

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
            self.reaction_list.scrollToItem(item)
            self.reaction_mask.update_state()

    def handle_changed_reaction(self, reaction: cobra.Reaction):
        # Update reaction item in list
        root = self.reaction_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            if item.reaction == reaction:
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
            if item.reaction == reaction:
                # remove item
                self.reaction_list.takeTopLevelItem(
                    self.reaction_list.indexOfTopLevelItem(item))
                break

        self.last_selected = self.reaction_mask.id.text()
        self.reactionDeleted.emit(reaction)

    @Slot(QTreeWidgetItem, int)
    def handle_item_clicked(self, item: ReactionListItem, column):
        self.last_selected = item.reaction.id
        if column == ReactionListColumn.Scenario:
            self.reaction_list.editItem(item, column)

    @Slot(QTreeWidgetItem, int)
    def handle_item_changed(self, item: ReactionListItem, column: int):
        if column == ReactionListColumn.Scenario:
            scen_text = item.text(column).strip()
            if len(scen_text) == 0 or validate_value(scen_text):
                self.central_widget.update_reaction_value(item.reaction.id, scen_text,
                    update_reaction_list=False) # not necessary to update the whole reaction list
                if self.appdata.auto_fba:
                    self.central_widget.parent.fba() # makes an update
                else:
                    self.update_item(item)
                    self.central_widget.update_maps()
            else:
                item.setBackground(column, Qt.red)

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

    def update(self, rebuild=False):
        # should only need to rebuild the whole list if the model changes
        self.reaction_list.itemChanged.disconnect(self.handle_item_changed)
        self.reaction_list.setSortingEnabled(False) # keep row order stable so that each item is updated
        if rebuild:
            self.reaction_list.clear()
            for r in self.appdata.project.cobra_py_model.reactions:
                self.add_reaction(r)
        else:
            for i in range(self.reaction_list.topLevelItemCount()):
                self.update_item(self.reaction_list.topLevelItem(i))

        if self.last_selected is None:
            pass
        else:
            items = self.reaction_list.findItems(
                self.last_selected, Qt.MatchExactly)
            for i in items:
                self.reaction_list.setCurrentItem(i)
                break

        self.reaction_list.setSortingEnabled(True)
        self.reaction_list.itemChanged.connect(self.handle_item_changed)
        self.reaction_list.resizeColumnToContents(ReactionListColumn.Flux)
        self.reaction_list.resizeColumnToContents(ReactionListColumn.LB)
        self.reaction_list.resizeColumnToContents(ReactionListColumn.UB)
        self.reaction_mask.update_state()

    def set_current_item(self, key):
        self.last_selected = key
        self.update()
        self.reaction_selected(self.reaction_list.currentItem())

    def emit_jump_to_map(self, idx: str, reaction: str):
        self.jumpToMap.emit(idx, reaction)

    def emit_jump_to_metabolite(self, metabolite):
        self.jumpToMetabolite.emit(metabolite)

    @Slot(bool)
    def set_column_visibility_action(self, visible):
        col_idx = self.sender().data()
        self.reaction_list.setColumnHidden(col_idx, not visible)
        self.visible_column[col_idx] = visible

    @Slot(QPoint)
    def context_menu(self, position):
        item: ReactionListItem = self.reaction_list.currentItem()
        if item:
            menu = QMenu(self.reaction_list)
            maximize_action = menu.addAction("maximize flux for this reaction")
            maximize_action.triggered.connect(self.maximize_reaction)
            minimize_action = menu.addAction("minimize flux for this reaction")
            minimize_action.triggered.connect(self.minimize_reaction)
            set_scen_value_action = menu.addAction("add computed value to scenario")
            set_scen_value_action.triggered.connect(self.set_scen_value_action)
            menu.exec_(self.reaction_list.mapToGlobal(position))

    @Slot()
    def maximize_reaction(self):
        self.central_widget.maximize_reaction(self.reaction_list.currentItem().reaction.id)

    @Slot()
    def minimize_reaction(self):
        self.central_widget.minimize_reaction(self.reaction_list.currentItem().reaction.id)

    @Slot()
    def set_scen_value_action(self):
        self.central_widget.set_scen_value(self.reaction_list.currentItem().reaction.id)

    @Slot(QPoint)
    def header_context_menu(self, position):
        menu = QMenu(self.reaction_list.header())
        for col_idx in range(1, len(self.header_labels)):
            action = menu.addAction(self.header_labels[col_idx])
            action.setCheckable(True)
            action.setChecked(self.visible_column[col_idx])
            action.setData(col_idx)
            action.triggered.connect(self.set_column_visibility_action)
        menu.exec_(self.reaction_list.header().mapToGlobal(position))

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

        self.parent: ReactionList = parent
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
        self.equation.editingFinished.connect(self.reaction_data_changed)
        self.lower_bound.textEdited.connect(self.throttler.throttle)
        self.upper_bound.textEdited.connect(self.throttler.throttle)
        self.coefficent.textEdited.connect(self.throttler.throttle)
        self.gene_reaction_rule.textEdited.connect(self.throttler.throttle)
        self.annotation.itemChanged.connect(self.throttler.throttle)


    def add_anno_row(self):
        i = self.annotation.rowCount()
        self.annotation.insertRow(i)
        self.changed = True

    def apply(self):
        try:
            self.reaction.lower_bound = float(self.lower_bound.text())
            self.reaction.upper_bound = float(self.upper_bound.text())
        except ValueError as exception:
            turn_red(self.lower_bound)
            turn_red(self.upper_bound)
            QMessageBox.warning(self, 'ValueError', str(exception))
        else:
            if self.reaction.id != self.id.text():
                self.reaction.id = self.id.text()
            self.reaction.name = self.name.text()
            self.reaction.build_reaction_from_string(self.equation.text())
            self.reaction.lower_bound = float(self.lower_bound.text())
            self.reaction.upper_bound = float(self.upper_bound.text())
            self.reaction.objective_coefficient = float(self.coefficent.text())
            self.reaction.gene_reaction_rule = self.gene_reaction_rule.text()
            self.reaction.lower_bound = float(self.lower_bound.text())
            self.reaction.upper_bound = float(self.upper_bound.text())
            self.reaction.annotation = {}
            rows = self.annotation.rowCount()
            for i in range(0, rows):
                if self.annotation.item(i, 0) is not None:
                    key = self.annotation.item(i, 0).text()
                else:
                    key = ""
                if self.annotation.item(i, 1) is not None:
                    value = self.annotation.item(i, 1).text()
                else:
                    value = ""

                self.reaction.annotation[key] = value

            self.changed = False
            self.reactionChanged.emit(self.reaction)
            self.parent.update_item(self.parent.reaction_list.currentItem())

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
                identifiers_org_result = check_identifiers_org_entry(key, value)

                if identifiers_org_result.connection_error:
                    msgBox = QMessageBox()
                    msgBox.setWindowTitle("Connection error!")
                    msgBox.setTextFormat(Qt.RichText)
                    msgBox.setText("<p>identifiers.org could not be accessed. Either the internet connection isn't working or the server is currently down.</p>")
                    msgBox.setIcon(QMessageBox.Warning)
                    msgBox.exec()
                    break

                if (not identifiers_org_result.is_key_value_pair_valid) and (":" in value):
                    split_value = value.split(":")
                    identifiers_org_result = check_identifiers_org_entry(split_value[0], split_value[1])


                if not identifiers_org_result.is_key_valid:
                    self.annotation.item(i, 0).setBackground(invalid_red)

                if not identifiers_org_result.is_key_value_pair_valid:
                    self.annotation.item(i, 1).setBackground(invalid_red)

                if not identifiers_org_result.is_key_value_pair_valid:
                    break
        self.setCursor(Qt.ArrowCursor)

    def delete_reaction(self):
        self.hide()
        self.reactionDeleted.emit(self.reaction)

    def validate_id(self):
        if self.reaction.id != self.id.text():
            if len(self.id.text().strip()) == 0:
                turn_red(self.id)
                return False
            elif self.id.text() in self.parent.appdata.project.cobra_py_model.reactions:
                turn_red(self.id)
                QMessageBox.information(
                    self, 'Invalid id', 'Please change identifier ' +
                    self.id.text() + ' because it is already in use.')
                return False
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
