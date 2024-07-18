"""The reactions list"""
from math import isclose
from enum import IntEnum
from typing_extensions import Annotated

import cobra
import copy
from qtpy.QtCore import QMimeData, Qt, Signal, Slot, QPoint, QSignalBlocker
from qtpy.QtGui import QColor, QDrag, QIcon, QGuiApplication, QKeyEvent
from qtpy.QtWidgets import (QHBoxLayout, QTreeWidget, QLabel, QLineEdit,
                            QMessageBox, QPushButton, QSizePolicy, QSplitter,
                            QTreeWidgetItem, QVBoxLayout, QWidget, QMenu,
                            QAbstractItemView)

from cnapy.appdata import AppData, ModelItemType
from cnapy.gui_elements.annotation_widget import AnnotationWidget
from cnapy.utils import SignalThrottler, turn_red, turn_white, update_selected
from cnapy.utils_for_cnapy_api import check_identifiers_org_entry, check_in_identifiers_org
from cnapy.gui_elements.map_view import validate_value
from cnapy.gui_elements.escher_map_view import EscherMapView

class ReactionListColumn(IntEnum):
    Id = 0
    Name = 1
    Scenario = 2
    Flux = 3
    LB = 4
    UB = 5
    DF = 6

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

    def keyPressEvent(self, event: QKeyEvent):
        # enable sequential editing of scenario values using up/down arrow keys
        super().keyPressEvent(event)
        if self.currentColumn() == ReactionListColumn.Scenario:
            if not self.isPersistentEditorOpen(self.currentItem(), self.currentColumn()):
                key = event.key()
                if key == Qt.Key_Up or key == Qt.Key_Down:
                    self.editItem(self.currentItem(), self.currentColumn())

class ReactionListItem(QTreeWidgetItem):
    """ For custom sorting of columns """

    def __init__(self, reaction: cobra.Reaction, parent: QTreeWidget):
        # although QTreeWidgetItem is constructed with the reaction_list as parent this
        # will not be its parent() which is None because it is a top-level item
        QTreeWidgetItem.__init__(self, parent)
        self.reaction: cobra.Reaction = reaction
        self.flux_sort_val = -float('inf')
        self.lb_val = -float('inf')
        self.ub_val = float('inf')
        self.df_val = -float("inf")
        self.pin_at_top = False

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
        if self.pin_at_top != other.pin_at_top:
            if self.treeWidget().header().sortIndicatorOrder() == Qt.DescendingOrder:
                return self.pin_at_top < other.pin_at_top
            else:
                return other.pin_at_top < self.pin_at_top
        column = self.treeWidget().sortColumn()
        if column == ReactionListColumn.Flux:
            return self.flux_sort_val < other.flux_sort_val
        elif column == ReactionListColumn.LB:
            return self.lb_val < other.lb_val
        elif column == ReactionListColumn.UB:
            return self.ub_val < other.ub_val
        elif column == ReactionListColumn.DF:
            return self.df_val < other.df_val
        else:  # use Qt default comparison for the other columns
#            return super().__lt__(other) # infinite recursion with PySide2, __lt__ is a virtual function of QTreeWidgetItem
            return self.text(column) < other.text(column)

    def update_tooltips(self):
        text = "Id: " + self.reaction.id + "\nName: " + self.reaction.name \
            + "\nEquation: " + self.reaction.build_reaction_string()\
            + "\nLowerbound: " + str(self.reaction.lower_bound) \
            + "\nUpper bound: " + str(self.reaction.upper_bound) \
            + "\nObjective coefficient: " + str(self.reaction.objective_coefficient)
        self.setToolTip(ReactionListColumn.Id, text)
        self.setToolTip(ReactionListColumn.Name, text)

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

        self.reaction_list: DragableTreeWidget = DragableTreeWidget()
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
        self.reaction_list.sortByColumn(ReactionListColumn.Id, Qt.AscendingOrder)
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
        self.reaction_list.setColumnHidden(ReactionListColumn.DF, True)
        self.visible_column[ReactionListColumn.DF] = False

    def clear(self):
        self.reaction_list.clear()
        self.reaction_mask.hide()

    def add_reaction(self, reaction: cobra.Reaction) -> ReactionListItem:
        ''' create a new item in the reaction list'''
        self.reaction_list.clearSelection()
        item = ReactionListItem(reaction, self.reaction_list)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        item.setText(ReactionListColumn.Id, reaction.id)
        item.setText(ReactionListColumn.Name, reaction.name)
        item.update_tooltips()
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
        if item.reaction.id in self.appdata.project.df_values.keys():
            item.setText(ReactionListColumn.DF, str(self.appdata.project.df_values[item.reaction.id]))
            item.df_val = self.appdata.project.df_values[item.reaction.id]

    def set_flux_value(self, item: ReactionListItem):
        key = item.reaction.id
        if key in self.appdata.project.comp_values.keys():
            (vl, vu) = self.appdata.project.comp_values[key]
            flux_text, background_color, as_one = self.appdata.flux_value_display(vl, vu)
            item.set_flux_data(flux_text, vl if as_one else (vl, vu))
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
        self.appdata.project.update_reaction_id_lists()
        reaction.set_hash_value()
        self.appdata.project.cobra_py_model.set_stoichiometry_hash_object()
        self.reaction_list.blockSignals(True)
        item = self.add_reaction(reaction)
        self.reaction_list.blockSignals(False)
        self.reaction_selected(item)
        self.appdata.window.unsaved_changes()

    def update_annotations(self, annotation):
        self.reaction_mask.annotation_widget.update_annotations(annotation)

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
            self.splitter.moveSplitter(int(r/2), 1)
            self.reaction_list.scrollToItem(item)
            self.reaction_mask.update_state()

            self.central_widget.add_model_item_to_history(reaction.id, reaction.name, ModelItemType.Reaction)
            self.central_widget.reaction_selected(reaction.id)

    def handle_changed_reaction(self, reaction: cobra.Reaction):
        # Update reaction item in list
        root = self.reaction_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            if item.reaction == reaction:
                old_id = item.text(ReactionListColumn.Id)
                item.setText(ReactionListColumn.Id, reaction.id)
                item.setText(ReactionListColumn.Name, reaction.name)
                item.update_tooltips()
                break

        self.last_selected = self.reaction_mask.id.text()
        self.reactionChanged.emit(old_id, reaction)

    def handle_deleted_reaction(self, reaction: cobra.Reaction):
        '''Remove reaction item from reaction list'''
        root = self.reaction_list.invisibleRootItem()
        child_count = root.childCount()
        with QSignalBlocker(self.reaction_list):
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

    def update_selected(self, string, with_annotations):
        return update_selected(
            string=string,
            with_annotations=with_annotations,
            model_elements=self.appdata.project.cobra_py_model.reactions,
            element_list=self.reaction_list,
        )

    def update(self, rebuild=False):
        if len(self.appdata.project.df_values.keys()) > 0:
            self.reaction_list.setColumnHidden(ReactionListColumn.DF, False)
            self.visible_column[ReactionListColumn.DF] = True

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
        self.reaction_list.itemChanged.connect(self.handle_item_changed)

        if self.last_selected is None:
            self.reaction_list.setCurrentItem(None)
        else:
            items = self.reaction_list.findItems(
                self.last_selected, Qt.MatchExactly)
            for i in items:
                # triggers self.reaction_selected which also does a self.reaction_mask.update_state()
                self.reaction_list.setCurrentItem(i)
                self.reaction_list.scrollToItem(i)
                break

        self.reaction_list.setSortingEnabled(True)
        self.reaction_list.resizeColumnToContents(ReactionListColumn.Flux)
        self.reaction_list.resizeColumnToContents(ReactionListColumn.LB)
        self.reaction_list.resizeColumnToContents(ReactionListColumn.UB)
        self.reaction_list.resizeColumnToContents(ReactionListColumn.DF)

    def set_current_item(self, key: str):
        self.last_selected = key
        self.update()

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
            pin_action = menu.addAction("pin at top of list")
            pin_action.setCheckable(True)
            pin_action.setChecked(item.pin_at_top)
            pin_action.triggered.connect(self.change_pinned)
            maximize_action = menu.addAction("maximize flux for this reaction")
            maximize_action.triggered.connect(self.maximize_reaction)
            minimize_action = menu.addAction("minimize flux for this reaction")
            minimize_action.triggered.connect(self.minimize_reaction)
            set_scen_value_action = menu.addAction("add computed value to scenario")
            set_scen_value_action.triggered.connect(self.set_scen_value_action)
            menu.exec_(self.reaction_list.mapToGlobal(position))

    @Slot(bool)
    def change_pinned(self, checked: bool):
        self.reaction_list.currentItem().pin_at_top = checked
        if checked:
            self.reaction_list.sortItems(self.reaction_list.sortColumn(), self.reaction_list.header().sortIndicatorOrder())
            self.appdata.project.scen_values.pinned_reactions.add(self.reaction_list.currentItem().reaction.id)
        else:
            self.appdata.project.scen_values.pinned_reactions.discard(self.reaction_list.currentItem().reaction.id)

    def pin_multiple(self, reac_ids):
        root = self.reaction_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item: ReactionListItem = root.child(i)
            if item.reaction.id in reac_ids:
                item.pin_at_top = True
        self.reaction_list.sortItems(self.reaction_list.sortColumn(), self.reaction_list.header().sortIndicatorOrder())
        self.appdata.project.scen_values.pinned_reactions.update(reac_ids)

    @Slot()
    def unpin_all(self):
        root = self.reaction_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item: ReactionListItem = root.child(i)
            if item.reaction.id in self.appdata.project.scen_values.pinned_reactions:
                item.pin_at_top = False
        self.appdata.project.scen_values.pinned_reactions = set()

    @Slot()
    def maximize_reaction(self):
        self.central_widget.maximize_reaction(self.reaction_list.currentItem().reaction.id)

    @Slot()
    def minimize_reaction(self):
        self.central_widget.minimize_reaction(self.reaction_list.currentItem().reaction.id)

    @Slot()
    def set_scen_value_action(self):
        self.central_widget.set_scen_value(self.reaction_list.currentItem().reaction.id)

    @Slot()
    def delete_reaction_action(self):
        self.central_widget.map_tabs.currentWidget().delete_reaction(self.reaction_list.currentItem().reaction.id)
        self.reaction_mask.update_state()
        self.appdata.window.unsaved_changes()

    @Slot(QPoint)
    def header_context_menu(self, position):
        menu = QMenu(self.reaction_list.header())
        for col_idx in range(1, len(self.header_labels)):
            action = menu.addAction(self.header_labels[col_idx])
            action.setCheckable(True)
            action.setChecked(self.visible_column[col_idx])
            action.setData(col_idx)
            action.triggered.connect(self.set_column_visibility_action)
        menu.addSeparator()
        action = menu.addAction("Copy table to system clipboard")
        action.triggered.connect(self.copy_to_clipboard)
        menu.exec_(self.reaction_list.header().mapToGlobal(position))

    def get_as_table(self) -> str:
        visible_columns = [j.value for j in ReactionListColumn if not self.reaction_list.isColumnHidden(j)]
        table = ["\t".join([ReactionListColumn(j).name for j in visible_columns])]
        root = self.reaction_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            line = []
            for j in visible_columns:
                line.append(item.text(j))
            table.append("\t".join(line))
        return "\r".join(table)

    @Slot()
    def copy_to_clipboard(self):
        clipboard = QGuiApplication.clipboard()
        table = self.get_as_table()
        clipboard.setText(table)

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
        self.fba_relevant_change = False
        self.setAcceptDrops(False)

        layout = QVBoxLayout()

        l = QHBoxLayout()
        label = QLabel("Id:")
        self.id = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.id)

        self.delete_button = QPushButton("Delete reaction")
        self.delete_button.setIcon(QIcon.fromTheme("edit-delete"))
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

        label = QLabel(" Rate max:")
        self.upper_bound = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.upper_bound)

        label = QLabel(" Objective coefficient:")
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

        self.throttler = SignalThrottler(500)
        self.throttler.triggered.connect(self.reaction_data_changed)

        self.annotation_widget = AnnotationWidget(self)
        layout.addItem(self.annotation_widget)

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


        self.id.textEdited.connect(self.throttler.throttle)
        self.name.textEdited.connect(self.throttler.throttle)
        self.equation.editingFinished.connect(self.reaction_data_changed)
        self.equation.editingFinished.connect(self.auto_fba)
        self.lower_bound.textEdited.connect(self.throttler.throttle)
        self.lower_bound.editingFinished.connect(self.throttler.finish)
        self.lower_bound.editingFinished.connect(self.auto_fba)
        self.upper_bound.textEdited.connect(self.throttler.throttle)
        self.upper_bound.editingFinished.connect(self.throttler.finish)
        self.upper_bound.editingFinished.connect(self.auto_fba)
        self.coefficent.textEdited.connect(self.throttler.throttle)
        self.coefficent.editingFinished.connect(self.throttler.finish)
        self.coefficent.editingFinished.connect(self.auto_fba)
        self.gene_reaction_rule.editingFinished.connect(self.throttler.throttle)

        self.grp_test_model = cobra.Model(id_or_model="GPR test")
        reaction = cobra.Reaction('GPR_TEST')
        metabolite = cobra.Metabolite('X')
        reaction.add_metabolites({metabolite: -1})
        self.grp_test_model.add_reactions([reaction])

        self.annotation_widget.deleteAnnotation.connect(
            self.delete_selected_annotation
        )

    def apply(self):
        bounds = self.reaction.bounds
        try:
            self.reaction.bounds = (float(self.lower_bound.text()), float(self.upper_bound.text()))
        except ValueError as exception:
            self.is_valid = False
            turn_red(self.lower_bound)
            turn_red(self.upper_bound)
            QMessageBox.warning(self, 'ValueError', str(exception))
            return

        id_ = self.reaction.id
        if self.reaction.id != self.id.text():
            if (" " in self.id.text()):
                turn_red(self.id)
                QMessageBox.warning(
                    self,
                    "Reaction ID error",
                    "A reaction ID must not contain a whitespace."
                )
                return
            self.reaction.id = self.id.text()
        name = self.reaction.name
        self.reaction.name = self.name.text()
        metabolites = self.reaction.metabolites
        if self.equation.isModified():
            self.reaction.build_reaction_from_string(self.equation.text()) # creates a new metabolites dict
            self.equation.setModified(False)
        objective_coefficient = self.reaction.objective_coefficient
        self.reaction.objective_coefficient = float(self.coefficent.text())
        gene_reaction_rule = self.reaction.gene_reaction_rule
        if self.gene_reaction_rule.isModified():
            self.handle_changed_gpr()
            self.gene_reaction_rule.setModified(False)
        self.reaction.bounds = (float(self.lower_bound.text()), float(self.upper_bound.text()))
        annotation = self.reaction.annotation
        self.annotation_widget.apply_annotation(self.reaction)

        if bounds != self.reaction.bounds or metabolites != self.reaction.metabolites or \
            objective_coefficient != self.reaction.objective_coefficient:
            self.fba_relevant_change = True
            self.reaction.set_hash_value()
            self.parent.appdata.project.cobra_py_model.set_stoichiometry_hash_object()
        if self.fba_relevant_change or name != self.reaction.name or \
            gene_reaction_rule != self.reaction.gene_reaction_rule or id_ != self.reaction.id or \
            annotation != self.reaction.annotation:
            self.reactionChanged.emit(self.reaction)
            current_item = self.parent.reaction_list.currentItem()
            if current_item is not None:
                self.parent.update_item(current_item)
                self.parent.central_widget.update()

    def auto_fba(self):
        if self.fba_relevant_change and self.parent.appdata.auto_fba:
            self.parent.central_widget.parent.fba()
        self.fba_relevant_change = False

    def check_in_identifiers_org(self):
        check_in_identifiers_org(self)

    def delete_reaction(self):
        self.hide()
        self.reactionDeleted.emit(self.reaction)

    def delete_selected_annotation(self, identifier_key):
        try:
            del(self.reaction.annotation[identifier_key])
            self.parent.appdata.window.unsaved_changes()
        except IndexError:
            pass

    def handle_changed_gpr(self):
        # "Except" cobra.core.gene:Malformed gene_reaction_rule
        # which results in an emptied GPR rule string.
        self.grp_test_model.reactions.get_by_id("GPR_TEST").gene_reaction_rule = self.gene_reaction_rule.text()
        if self.grp_test_model.reactions.get_by_id("GPR_TEST").gene_reaction_rule == "":
            self.gene_reaction_rule.blockSignals(True)
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("Malformed GPR rule")
            msg_box.setText("It appears that your changed GPR rule is not valid. Do you want to edit or revert your changes?")
            edit_but = msg_box.addButton("Edit GPR rule", QMessageBox.RejectRole)
            revert_but = msg_box.addButton("Revert GPR rule", QMessageBox.ResetRole)
            msg_box.setDefaultButton(revert_but)
            msg_box.exec_()
            self.gene_reaction_rule.blockSignals(False)

            if msg_box.clickedButton() == edit_but:
                self.gene_reaction_rule.setFocus()
                return
            elif msg_box.clickedButton() == revert_but:
                self.gene_reaction_rule.setText(self.reaction.gene_reaction_rule)
                self.gene_reaction_rule.setModified(False)
                return

        genes = copy.deepcopy(self.gene_reaction_rule.text())\
            .replace("AND", "").replace("and", "")\
            .replace("OR", "").replace("or", "")\
            .replace("(", "").replace(")", "")\
            .replace("  ", " ").replace("\t", " ")\
            .split(" ")

        model_gene_ids = [x.id for x in self.parent.appdata.project.cobra_py_model.genes]
        genes_to_add = []
        for gene in genes:
            if (gene not in model_gene_ids) and (gene != ""):
                genes_to_add.append(gene)

        old_gene_reaction_rule = copy.deepcopy(self.reaction.gene_reaction_rule)

        if len(genes_to_add) > 0:
            self.gene_reaction_rule.blockSignals(True)
            msg_box = QMessageBox(self)
            msg_box.setIcon(QMessageBox.Question)
            msg_box.setWindowTitle("Create new genes?")
            msg_box.setText("The following genes do not exist and will be added to the model:\n" +
                            ', '.join(genes_to_add))
            msg_box.setDefaultButton(msg_box.addButton(QMessageBox.Ok))
            edit_but = msg_box.addButton("Edit GPR rule", QMessageBox.RejectRole)
            revert_but = msg_box.addButton("Revert GPR rule", QMessageBox.ResetRole)
            msg_box.exec_()
            self.gene_reaction_rule.blockSignals(False)
            if msg_box.clickedButton() == edit_but:
                self.gene_reaction_rule.setFocus()
                return
            elif msg_box.clickedButton() == revert_but:
                self.gene_reaction_rule.setText(self.reaction.gene_reaction_rule)
                self.reaction.gene_reaction_rule = old_gene_reaction_rule
                self.gene_reaction_rule.setModified(False)
                return

        self.reaction.gene_reaction_rule = self.gene_reaction_rule.text()
        self.gene_reaction_rule.setText(self.reaction.gene_reaction_rule)
        self.parent.appdata.window.unsaved_changes()

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
                model.add_reactions([r])
            except ValueError:
                turn_red(self.name)
                return False
            else:
                turn_white(self.name)
                return True

    def validate_equation(self):
        if not self.equation.isModified():
            return True
        ok = False
        existing_metabolites = set(self.parent.appdata.project.cobra_py_model.metabolites.list_attr('id'))
        test_reaction = cobra.Reaction(
            "xxxx_cnapy_test_reaction", name="cnapy test reaction")
        with self.parent.appdata.project.cobra_py_model as model:
            model.add_reactions([test_reaction])

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

            if ok:
                new_metabolites = {m.id for m in test_reaction.metabolites} - existing_metabolites
                if len(new_metabolites) > 0:
                    self.equation.blockSignals(True)
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Question)
                    msg_box.setWindowTitle("Create new metabolites?")
                    msg_box.setText("The following metabolites do not exist and will be added to the model:\n" +
                                    ', '.join(new_metabolites))
                    msg_box.setDefaultButton(msg_box.addButton(QMessageBox.Ok)) #"Ok", QMessageBox.AcceptRole))
                    edit_but = msg_box.addButton("Edit equation", QMessageBox.RejectRole)
                    revert_but = msg_box.addButton("Revert equation", QMessageBox.ResetRole)
                    msg_box.exec_()
                    if msg_box.clickedButton() == edit_but:
                        self.equation.setFocus()
                        ok = False
                    elif msg_box.clickedButton() == revert_but:
                        self.equation.setText(model.reactions.get_by_id(self.id.text()).build_reaction_string())
                        self.equation.setModified(False)
                    self.equation.blockSignals(False)

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
        self.validate_mask()
        if self.is_valid:
            self.apply()
            self.update_state()

    def update_state(self):
        self.jump_list.clear()
        for name, mmap in self.parent.appdata.project.maps.items():
            if EscherMapView in mmap:
                # creates one button even if the reaction occurs multiple times on the map
                mmap[EscherMapView].cnapy_bridge.addMapToJumpListIfReactionPresent.emit(self.id.text(), name)
            else: # CNApy map
                if self.id.text() in mmap["boxes"]:
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

    @Slot()
    def update_reaction_string(self):
        if self.reaction is not None:
            self.equation.setText(self.reaction.build_reaction_string())

    jumpToMap = Signal(str, str)
    jumpToMetabolite = Signal(str)
    reactionChanged = Signal(cobra.Reaction)
    reactionDeleted = Signal(cobra.Reaction)
