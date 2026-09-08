"""The reactions list"""
from math import isclose
from enum import IntEnum
from typing_extensions import Annotated

import cobra
import copy
import re
from qtpy.QtCore import (QAbstractTableModel, QModelIndex, QMimeData, Qt, Signal, Slot, QPoint,
                         QSignalBlocker, QEvent, QTimer)
from qtpy.QtGui import QColor, QDrag, QIcon, QGuiApplication
from qtpy.QtWidgets import (QHBoxLayout, QTableView, QTableWidget, QTableWidgetItem, QLabel, QLineEdit,
                            QMessageBox, QPushButton, QSizePolicy, QSplitter, QStyledItemDelegate,
                            QVBoxLayout, QWidget, QMenu, QAbstractItemView, QHeaderView, QStackedWidget,
                            QToolButton, QFrame, QPlainTextEdit)

from cnapy.appdata import AppData, ModelItemType
from cnapy.gui_elements.annotation_widget import AnnotationWidget
from cnapy.utils import SignalThrottler, turn_red, turn_white
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

class ReactionListItem:
    """Row data for reactions in the table model."""

    def __init__(self, reaction: cobra.Reaction, model=None):
        self.reaction: cobra.Reaction = reaction
        self.model = model
        self.texts = [""] * len(ReactionListColumn)
        self.backgrounds = [None] * len(ReactionListColumn)
        self.foregrounds = [None] * len(ReactionListColumn)
        self.tooltips = [""] * len(ReactionListColumn)
        self.pin_at_top = False
        self.hidden = False

    def flags(self):
        # Vestigial QTreeWidgetItem-compatibility shim: ReactionListModel.flags()
        # hardcodes which column is editable and never consults this, so this
        # value is not authoritative and setFlags() below does not store anything.
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def setFlags(self, _flags):
        return None

    def text(self, column):
        return self.texts[int(column)]

    def setText(self, column, text):
        self.texts[int(column)] = text
        self._emit_changed(column)

    def setBackground(self, column, color):
        self.backgrounds[int(column)] = color
        self._emit_changed(column)

    def setForeground(self, column, color):
        self.foregrounds[int(column)] = color
        self._emit_changed(column)

    def setToolTip(self, column, text):
        self.tooltips[int(column)] = text
        self._emit_changed(column)

    def setSelected(self, selected):
        if self.model is not None and selected:
            self.model.view.setCurrentItem(self)

    def setHidden(self, hidden):
        self.hidden = hidden
        if self.model is not None:
            row = self.model.indexOfTopLevelItem(self)
            if row >= 0:
                self.model.view.setRowHidden(row, hidden)

    def isHidden(self):
        return self.hidden

    def update_tooltips(self):
        text = "Id: " + self.reaction.id + "\nName: " + self.reaction.name \
            + "\nEquation: " + self.reaction.build_reaction_string()\
            + "\nLowerbound: " + str(self.reaction.lower_bound) \
            + "\nUpper bound: " + str(self.reaction.upper_bound) \
            + "\nObjective coefficient: " + str(self.reaction.objective_coefficient)
        self.setToolTip(ReactionListColumn.Id, text)
        self.setToolTip(ReactionListColumn.Name, text)

    def _emit_changed(self, column):
        if self.model is not None:
            self.model.emit_item_changed(self, int(column))


class ReactionListModel(QAbstractTableModel):
    """Custom table model backing the reaction list view."""

    itemChanged = Signal(object, int)

    def __init__(self, header_labels, appdata, parent=None):
        super().__init__(parent)
        self.header_labels = header_labels
        self.appdata = appdata
        self.items = []
        self.sort_column = ReactionListColumn.Id
        self.sort_order = Qt.SortOrder.AscendingOrder
        self.sorting_enabled = False
        self.view = None
        # Snapshot of appdata.project.comp_values for display in the Flux
        # column, decoupled from that dict itself: appdata.project.comp_values
        # is shared between FBA (comp_values_type == 0, real flux values) and
        # FVA (comp_values_type == 1, used only for the map's coloring), but
        # the Flux column should only ever reflect the last real FBA solution.
        self.flux_values = {}
        self.refresh_flux_values()

    def refresh_flux_values(self):
        """Pick up appdata.project.comp_values for the Flux column, but only
        when it currently holds real flux values rather than FVA results."""
        if self.appdata.project.comp_values_type == 0:
            self.flux_values = dict(self.appdata.project.comp_values)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.header_labels)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        column = index.column()
        text, background, foreground, tooltip = self.cell_data(item, column)
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return text
        if role == Qt.ItemDataRole.BackgroundRole:
            return background
        if role == Qt.ItemDataRole.ForegroundRole:
            return foreground
        if role == Qt.ItemDataRole.ToolTipRole:
            return tooltip
        return None

    def cell_data(self, item, column):
        column = ReactionListColumn(column)
        text = item.text(column)
        background = item.backgrounds[column]
        foreground = item.foregrounds[column]
        tooltip = item.tooltips[column]
        default_background = QColor(75, 75, 75) if self.appdata.is_in_dark_mode else Qt.GlobalColor.white
        default_foreground = QColor(255, 255, 255) if self.appdata.is_in_dark_mode else QColor(0, 0, 0)
        key = item.reaction.id

        if column == ReactionListColumn.Scenario:
            if key in self.appdata.project.scen_values:
                vl, vu = self.appdata.project.scen_values[key]
                text = self.appdata.format_flux_value(vl)
                if vl != vu:
                    text = text + ", " + self.appdata.format_flux_value(vu)
                background = self.appdata.scen_color
            else:
                text = ""
                background = default_background
                foreground = default_foreground
        elif column == ReactionListColumn.Flux:
            if key in self.flux_values:
                vl, vu = self.flux_values[key]
                text, background, as_one = self.appdata.flux_value_display(vl, vu)
            else:
                text = ""
                background = default_background
                foreground = default_foreground
        elif column in (ReactionListColumn.LB, ReactionListColumn.UB):
            vl, vu, background = self.bounds_data(item)
            text = self.appdata.format_flux_value(vl if column == ReactionListColumn.LB else vu)
            if key not in self.appdata.project.fva_values:
                foreground = default_foreground
        elif column == ReactionListColumn.DF and key in self.appdata.project.df_values:
            text = str(self.appdata.project.df_values[key])
        if item.backgrounds[column] is not None:
            background = item.backgrounds[column]
        if item.foregrounds[column] is not None:
            foreground = item.foregrounds[column]
        return text, background, foreground, tooltip

    def bounds_data(self, item):
        key = item.reaction.id
        if key in self.appdata.project.fva_values.keys():
            vl, vu = self.appdata.project.fva_values[key]
            if isclose(vl, vu, abs_tol=self.appdata.abs_tol):
                if self.appdata.modes_coloring:
                    background = Qt.GlobalColor.red if vl == 0 else Qt.GlobalColor.green
                else:
                    background = self.appdata.comp_color
            elif isclose(vl, 0.0, abs_tol=self.appdata.abs_tol) or isclose(vu, 0.0, abs_tol=self.appdata.abs_tol) or vl <= 0 and vu >= 0:
                background = self.appdata.special_color_1
            else:
                background = self.appdata.special_color_2
        else:
            vl = item.reaction.lower_bound
            vu = item.reaction.upper_bound
            background = QColor(75, 75, 75) if self.appdata.is_in_dark_mode else Qt.GlobalColor.white
        return vl, vu, background

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        item = self.items[index.row()]
        column = index.column()
        if column == ReactionListColumn.Scenario:
            current_text, *_ = self.cell_data(item, column)
            if value == current_text:
                # Nothing actually changed -- e.g. the editor was opened (by a
                # click, or by ScenarioValueDelegate moving between rows while
                # editing) and closed again without being typed into. Treating
                # this as a real edit would make handle_item_changed invalidate
                # the previously computed flux values on every such no-op commit,
                # including every arrow-key step while just browsing the column.
                return True
        item.texts[column] = value
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole])
        self.itemChanged.emit(item, column)
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        flags = Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsDragEnabled
        if index.column() == ReactionListColumn.Scenario:
            flags |= Qt.ItemFlag.ItemIsEditable
        return flags

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return self.header_labels[section]
        return None

    def add_item(self, item):
        item.model = self
        self.beginInsertRows(QModelIndex(), len(self.items), len(self.items))
        self.items.append(item)
        self.endInsertRows()
        if self.sorting_enabled:
            self.sort(self.sort_column, self.sort_order)

    def clear(self):
        self.beginResetModel()
        self.items.clear()
        self.endResetModel()

    def emit_item_changed(self, item, column):
        row = self.indexOfTopLevelItem(item)
        if row >= 0:
            index = self.index(row, int(column))
            self.dataChanged.emit(index, index)

    def indexOfTopLevelItem(self, item):
        try:
            return self.items.index(item)
        except ValueError:
            return -1

    def takeTopLevelItem(self, row):
        if row < 0 or row >= len(self.items):
            return None
        self.beginRemoveRows(QModelIndex(), row, row)
        item = self.items.pop(row)
        item.model = None
        self.endRemoveRows()
        return item

    def sort_value(self, item, column):
        key = item.reaction.id
        if column == ReactionListColumn.Scenario:
            if key in self.appdata.project.scen_values:
                vl, vu = self.appdata.project.scen_values[key]
                return abs(vl) if vl == vu else vu - vl
            return -float('inf')
        if column == ReactionListColumn.Flux:
            if key in self.flux_values:
                vl, vu = self.flux_values[key]
                return abs(vl) if vl == vu else vu - vl
            return -float('inf')
        if column == ReactionListColumn.LB:
            vl, _vu, _background = self.bounds_data(item)
            return vl
        if column == ReactionListColumn.UB:
            _vl, vu, _background = self.bounds_data(item)
            return vu
        if column == ReactionListColumn.DF:
            return self.appdata.project.df_values.get(key, -float('inf'))
        return item.text(column)

    def sort(self, column, order=Qt.SortOrder.AscendingOrder):
        self.sort_column = column
        self.sort_order = order
        if not self.sorting_enabled:
            return
        self.layoutAboutToBeChanged.emit()
        reverse = order == Qt.SortOrder.DescendingOrder
        pinned = [item for item in self.items if item.pin_at_top]
        unpinned = [item for item in self.items if not item.pin_at_top]
        pinned.sort(key=lambda item: self.sort_value(item, column), reverse=reverse)
        unpinned.sort(key=lambda item: self.sort_value(item, column), reverse=reverse)
        new_items = pinned + unpinned

        new_row_of_item = {id(item): row for row, item in enumerate(new_items)}
        for old_index in self.persistentIndexList():
            old_item = self.items[old_index.row()]
            new_row = new_row_of_item.get(id(old_item))
            new_index = (self.index(new_row, old_index.column())
                         if new_row is not None else QModelIndex())
            self.changePersistentIndex(old_index, new_index)

        self.items[:] = new_items
        self.layoutChanged.emit()


class ScenarioValueDelegate(QStyledItemDelegate):
    """Editor delegate for the Scenario column.

    Qt installs the delegate itself as an event filter on the editor widget
    it creates (this is how Tab/Backtab/Enter/Escape are normally handled,
    see QAbstractItemDelegate.eventFilter). We hook the same mechanism for
    Up/Down so they commit the current row and move the *editor* to the
    row above/below instead of just moving the cursor inside the QLineEdit
    (which ignores Up/Down anyway).

    This intentionally does not rely on the key event bubbling up from the
    editor to the view: that bubbling does happen in plain Qt, but the
    editor's parent view here also reacts to currentIndex changes (to keep
    the reaction detail mask in sync), and that reaction can itself change
    the current index again before a view-level keyPressEvent handler gets
    a chance to reopen the editor. Handling it here, before the event ever
    leaves the editor, sidesteps that reentrancy entirely.
    """

    @staticmethod
    def _next_visible_row(view, row, step):
        """Row index one step away in the given direction, skipping rows
        hidden by the search filter (see ReactionList.update_selected).
        Returns -1 if there is no visible row in that direction."""
        row_count = view.model().rowCount()
        row += step
        while 0 <= row < row_count and view.isRowHidden(row):
            row += step
        return row if 0 <= row < row_count else -1

    def eventFilter(self, editor, event):
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            view = self.parent()
            index = view.currentIndex()
            step = 1 if event.key() == Qt.Key.Key_Down else -1
            new_row = self._next_visible_row(view, index.row(), step)
            # Commit unconditionally, even at the boundary (no row to move to):
            # otherwise a value typed into the first/last row is silently lost
            # instead of saved, since there's nowhere left to arrow away to.
            self.commitData.emit(editor)
            if new_row >= 0:
                self.closeEditor.emit(editor, QStyledItemDelegate.NoHint)
                new_index = view.model().index(new_row, index.column())
                view.setCurrentIndex(new_index)
                view.scrollTo(new_index)
                view.edit(new_index)
            return True
        return super().eventFilter(editor, event)


class DragableTableView(QTableView):
    """A table of dragable reaction items."""

    currentItemChanged = Signal(object)
    itemClicked = Signal(object, int)

    def __init__(self):
        super().__init__()
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setWordWrap(False)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.verticalHeader().setMinimumSectionSize(self.fontMetrics().lineSpacing())
        self.verticalHeader().setDefaultSectionSize(self.fontMetrics().lineSpacing())
        self.setItemDelegateForColumn(ReactionListColumn.Scenario, ScenarioValueDelegate(self))

    def setModel(self, model):
        super().setModel(model)
        model.view = self
        self.selectionModel().currentChanged.connect(self._current_changed)
        self.clicked.connect(self._clicked)

    def mouseMoveEvent(self, _event):
        item = self.currentItem()
        if item is not None:
            mime_data = QMimeData()
            mime_data.setText(item.reaction.id)
            drag = QDrag(self)
            drag.setMimeData(mime_data)
            drag.exec(Qt.DropAction.CopyAction | Qt.DropAction.MoveAction, Qt.DropAction.CopyAction)

    def _current_changed(self, current, _previous):
        self.currentItemChanged.emit(self.itemFromIndex(current))

    def _clicked(self, index):
        self.itemClicked.emit(self.itemFromIndex(index), index.column())

    def itemFromIndex(self, index):
        if index.isValid():
            return self.model().items[index.row()]
        return None

    def currentItem(self):
        return self.itemFromIndex(self.currentIndex())

    def currentColumn(self):
        return self.currentIndex().column()

    def clear(self):
        self.model().clear()

    def clearSelection(self):
        super().clearSelection()
        self.setCurrentIndex(QModelIndex())

    def setCurrentItem(self, item):
        if item is None:
            self.clearSelection()
            return
        row = self.model().indexOfTopLevelItem(item)
        if row >= 0:
            self.setCurrentIndex(self.model().index(row, 0))

    def scrollToItem(self, item):
        row = self.model().indexOfTopLevelItem(item)
        if row >= 0:
            self.scrollTo(self.model().index(row, 0))

    def editItem(self, item, column):
        row = self.model().indexOfTopLevelItem(item)
        if row >= 0:
            self.edit(self.model().index(row, int(column)))

    def topLevelItemCount(self):
        return len(self.model().items)

    def topLevelItem(self, row):
        return self.model().items[row]

    def findItems(self, text, _flags, column=ReactionListColumn.Id):
        model = self.model()
        return [item for item in model.items if model.cell_data(item, column)[0] == text]

    def sortItems(self, column, order):
        self.model().sort(column, order)

    def sortColumn(self):
        return self.model().sort_column

    def setSortingEnabled(self, enable):
        self.model().sorting_enabled = enable
        super().setSortingEnabled(enable)

    def indexOfTopLevelItem(self, item):
        return self.model().indexOfTopLevelItem(item)

    def takeTopLevelItem(self, row):
        return self.model().takeTopLevelItem(row)


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
        policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
        self.add_button.setSizePolicy(policy)

        self.reaction_list: DragableTableView = DragableTableView()
        self.reaction_list.setDragEnabled(True)
        self.header_labels = [ReactionListColumn(i).name for i in range(len(ReactionListColumn))]
        self.reaction_model = ReactionListModel(self.header_labels, self.appdata, self.reaction_list)
        self.reaction_list.setModel(self.reaction_model)
        self.reaction_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.reaction_list.customContextMenuRequested.connect(self.context_menu)
        # heuristic initial column widths
        self.reaction_list.resizeColumnToContents(ReactionListColumn.Scenario)
        self.reaction_list.resizeColumnToContents(ReactionListColumn.LB)
        self.reaction_list.resizeColumnToContents(ReactionListColumn.UB)
        width = self.reaction_list.horizontalHeader().sectionSize(ReactionListColumn.Scenario)
        self.reaction_list.horizontalHeader().resizeSection(ReactionListColumn.Flux, width)
        width +=  self.reaction_list.horizontalHeader().sectionSize(ReactionListColumn.LB)
        self.reaction_list.horizontalHeader().resizeSection(ReactionListColumn.Id, width)
        self.reaction_list.horizontalHeader().resizeSection(ReactionListColumn.Name, width)
        self.visible_column = [True]*len(self.header_labels)
        self.reaction_list.setSortingEnabled(True)
        self.reaction_list.sortByColumn(ReactionListColumn.Id, Qt.SortOrder.AscendingOrder)
        self.reaction_list.horizontalHeader().setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.reaction_list.horizontalHeader().customContextMenuRequested.connect(self.header_context_menu)

        for r in self.appdata.project.cobra_py_model.reactions:
            self.add_reaction(r)

        self.reaction_mask = ReactionMask(self)
        self.reaction_mask.hide()

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        l = QHBoxLayout()
        l.setAlignment(Qt.AlignmentFlag.AlignRight)
        l.addWidget(self.add_button)
        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.reaction_list)
        self.splitter.addWidget(self.reaction_mask)
        self.layout.addItem(l)
        self.layout.addWidget(self.splitter)
        self.setLayout(self.layout)

        self.reaction_list.currentItemChanged.connect(self.reaction_selected)
        self.reaction_list.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.reaction_list.itemClicked.connect(self.handle_item_clicked)
        self.reaction_model.itemChanged.connect(self.handle_item_changed)

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
        item = ReactionListItem(reaction)
        self.reaction_model.add_item(item)
        item.setText(ReactionListColumn.Id, reaction.id)
        item.setText(ReactionListColumn.Name, reaction.name)
        item.update_tooltips()
        return item

    def update_item(self, item: ReactionListItem):
        ''' notify the view that lazily computed columns changed '''
        row = self.reaction_model.indexOfTopLevelItem(item)
        if row >= 0:
            self.reaction_model.dataChanged.emit(
                self.reaction_model.index(row, ReactionListColumn.Scenario),
                self.reaction_model.index(row, ReactionListColumn.DF),
            )

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
            if self.reaction_list.currentItem() is not item:
                # Only needed to make `item` current in the first place (e.g. a
                # newly added reaction, called outside the currentChanged signal).
                # Calling it when `item` is already current would reset the
                # current column back to 0, fighting with in-row column
                # navigation (see ScenarioValueDelegate).
                item.setSelected(True)
            self.reaction_mask.show()
            reaction: cobra.Reaction = item.reaction

            self.last_selected = reaction.id
            self.reaction_mask.reaction = reaction

            self.reaction_mask.id.setText(reaction.id)
            self.reaction_mask.name.setText(reaction.name)
            self.reaction_mask.set_equation_from_reaction(reaction)
            self.reaction_mask.lower_bound.setText(str(reaction.lower_bound))
            self.reaction_mask.upper_bound.setText(str(reaction.upper_bound))
            self.reaction_mask.coefficent.setText(
                str(reaction.objective_coefficient))
            self.reaction_mask.gene_reaction_rule.setText(
                str(reaction.gene_reaction_rule))
            self.update_annotations(reaction.annotation)

            turn_white(self.reaction_mask.id, self.appdata.is_in_dark_mode)
            turn_white(self.reaction_mask.name, self.appdata.is_in_dark_mode)
            turn_white(self.reaction_mask.name, self.appdata.is_in_dark_mode)
            turn_white(self.reaction_mask.equation, self.appdata.is_in_dark_mode)
            turn_white(self.reaction_mask.lower_bound, self.appdata.is_in_dark_mode)
            turn_white(self.reaction_mask.upper_bound, self.appdata.is_in_dark_mode)
            turn_white(self.reaction_mask.coefficent, self.appdata.is_in_dark_mode)
            turn_white(self.reaction_mask.gene_reaction_rule, self.appdata.is_in_dark_mode)
            self.reaction_mask.is_valid = True

            if self.splitter.sizes()[1] == 0:
                (_, r) = self.splitter.getRange(1)
                self.splitter.moveSplitter(int(r/2), 1)
            self.reaction_list.scrollToItem(item)
            self.reaction_mask.update_state()

            self.central_widget.add_model_item_to_history(reaction.id, reaction.name, ModelItemType.Reaction)
            self.central_widget.reaction_selected(reaction.id)

    def handle_changed_reaction(self, reaction: cobra.Reaction):
        # Update reaction item in list
        for item in self.reaction_model.items:
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
        with QSignalBlocker(self.reaction_list):
            for item in list(self.reaction_model.items):
                if item.reaction == reaction:
                    # remove item
                    self.reaction_list.takeTopLevelItem(
                        self.reaction_list.indexOfTopLevelItem(item))
                    break

        self.last_selected = self.reaction_mask.id.text()
        self.reactionDeleted.emit(reaction)

    @Slot(object, int)
    def handle_item_clicked(self, item: ReactionListItem, column):
        self.last_selected = item.reaction.id
        if column == ReactionListColumn.Scenario:
            self.reaction_list.editItem(item, column)

    @Slot(object, int)
    def handle_item_changed(self, item: ReactionListItem, column: int):
        if column == ReactionListColumn.Scenario:
            scen_text = item.text(column).strip()
            if len(scen_text) == 0 or validate_value(scen_text):
                item.backgrounds[ReactionListColumn.Scenario] = None
                self.central_widget.update_reaction_value(item.reaction.id, scen_text,
                    update_reaction_list=False) # not necessary to update the whole reaction list
                if self.appdata.auto_fba:
                    self.central_widget.parent.fba() # makes an update
                else:
                    self.update_item(item)
                    self.central_widget.update_maps()
            else:
                item.setBackground(column, Qt.GlobalColor.red)

    def update_selected(self, string, with_annotations):
        if len(string) >= 2:
            regex = re.compile(".*".join(map(re.escape, string.split("*"))), re.IGNORECASE)
            found_ids = [
                reaction.id
                for reaction in self.appdata.project.cobra_py_model.reactions
                if regex.search(reaction.id)
                or regex.search(reaction.name)
                or (
                    with_annotations
                    and (
                        any(regex.search(key) for key in reaction.annotation.keys())
                        or any(regex.search(str(value)) for value in reaction.annotation.values())
                    )
                )
            ]
        else:
            found_ids = [reaction.id for reaction in self.appdata.project.cobra_py_model.reactions]

        found_id_set = set(found_ids)
        for item in self.reaction_model.items:
            item.setHidden(item.reaction.id not in found_id_set)

        current_item = self.reaction_list.currentItem()
        if current_item is not None and not current_item.isHidden():
            self.reaction_list.scrollToItem(current_item)

        return found_ids

    def update(self, rebuild=False):
        if len(self.appdata.project.df_values.keys()) > 0:
            self.reaction_list.setColumnHidden(ReactionListColumn.DF, False)
            self.visible_column[ReactionListColumn.DF] = True

        # should only need to rebuild the whole list if the model changes; computed
        # columns are evaluated lazily by ReactionListModel.data() for visible rows.
        if rebuild:
            self.reaction_model.itemChanged.disconnect(self.handle_item_changed)
            self.reaction_list.setSortingEnabled(False)
            self.reaction_list.clear()
            for r in self.appdata.project.cobra_py_model.reactions:
                self.add_reaction(r)
            self.reaction_model.itemChanged.connect(self.handle_item_changed)
        elif self.reaction_model.rowCount() > 0:
            self.reaction_model.refresh_flux_values()
            for item in self.reaction_model.items:
                item.backgrounds[ReactionListColumn.Flux] = None
            self.reaction_model.dataChanged.emit(
                self.reaction_model.index(0, ReactionListColumn.Scenario),
                self.reaction_model.index(self.reaction_model.rowCount() - 1, ReactionListColumn.DF),
            )

        if self.last_selected is None:
            self.reaction_list.setCurrentItem(None)
        else:
            items = self.reaction_list.findItems(
                self.last_selected, Qt.MatchFlag.MatchExactly)
            for i in items:
                # triggers self.reaction_selected which also does a self.reaction_mask.update_state()
                self.reaction_list.setCurrentItem(i)
                self.reaction_list.scrollToItem(i)
                break

        self.reaction_list.setSortingEnabled(True)
        self.reaction_list.sortItems(
            self.reaction_list.sortColumn(),
            self.reaction_list.horizontalHeader().sortIndicatorOrder(),
        )

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
            menu.exec(self.reaction_list.mapToGlobal(position))

    @Slot(bool)
    def change_pinned(self, checked: bool):
        self.reaction_list.currentItem().pin_at_top = checked
        if checked:
            self.reaction_list.sortItems(self.reaction_list.sortColumn(), self.reaction_list.horizontalHeader().sortIndicatorOrder())
            self.appdata.project.scen_values.pinned_reactions.add(self.reaction_list.currentItem().reaction.id)
        else:
            self.appdata.project.scen_values.pinned_reactions.discard(self.reaction_list.currentItem().reaction.id)

    def pin_multiple(self, reac_ids):
        for item in self.reaction_model.items:
            if item.reaction.id in reac_ids:
                item.pin_at_top = True
        self.reaction_list.sortItems(self.reaction_list.sortColumn(), self.reaction_list.horizontalHeader().sortIndicatorOrder())
        self.appdata.project.scen_values.pinned_reactions.update(reac_ids)

    @Slot()
    def unpin_all(self):
        for item in self.reaction_model.items:
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
        menu = QMenu(self.reaction_list.horizontalHeader())
        for col_idx in range(1, len(self.header_labels)):
            action = menu.addAction(self.header_labels[col_idx])
            action.setCheckable(True)
            action.setChecked(self.visible_column[col_idx])
            action.setData(col_idx)
            action.triggered.connect(self.set_column_visibility_action)
        menu.addSeparator()
        action = menu.addAction("Copy table to system clipboard")
        action.triggered.connect(self.copy_to_clipboard)
        menu.exec(self.reaction_list.horizontalHeader().mapToGlobal(position))

    def get_as_table(self) -> str:
        visible_columns = [j.value for j in ReactionListColumn if not self.reaction_list.isColumnHidden(j)]
        table = ["\t".join([ReactionListColumn(j).name for j in visible_columns])]
        for item in self.reaction_model.items:
            line = []
            for j in visible_columns:
                line.append(self.reaction_model.cell_data(item, j)[0])
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
        self.layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

    def clear(self):
        for i in reversed(range(self.layout.count())):
            self.layout.itemAt(i).widget().setParent(None)

    def add(self, name: str):
        if self.layout.count() == 0:
            label = QLabel("Jump to reaction on map:")
            self.layout.addWidget(label)

        jb = JumpButton(self, name)
        policy = QSizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
        jb.setSizePolicy(policy)
        self.layout.addWidget(jb)
        self.setLayout(self.layout)

        jb.jumpToMap.connect(self.parent.emit_jump_to_map)

    @ Slot(str)
    def emit_jump_to_map(self: JumpButton, name: str):
        self.parent.emit_jump_to_map(name)

    jumpToMap = Signal(str)


class ClickableEquationLabel(QLabel):
    """A read-only label used to display a reaction equation with clickable
    metabolite links (see ReactionMask.build_equation_html).

    Clicking a link is handled through the inherited linkActivated signal.
    Clicking anywhere else on the label emits `clicked`, which
    ReactionMask uses to switch back to the editable QLineEdit.
    """

    clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hovering_link = False
        self._metabolite_names = {}
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.setWordWrap(False)
        self.setMouseTracking(True)
        # Ignored so the layout can shrink this label below its content's
        # sizeHint instead of growing the whole mask to fit a long equation;
        # Qt still clips the painted rich text to the label's actual
        # geometry, so an over-long equation is simply cut off here (the
        # expand button/overlay is how the full text stays reachable).
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        self.linkHovered.connect(self._on_link_hovered)

    def set_metabolite_names(self, reaction: cobra.Reaction):
        self._metabolite_names = {metabolite.id: metabolite.name for metabolite in reaction.metabolites}

    def _on_link_hovered(self, link: str):
        self._hovering_link = bool(link)
        self.setCursor(Qt.CursorShape.PointingHandCursor if link else Qt.CursorShape.IBeamCursor)
        self.setToolTip(self._metabolite_names.get(link, ""))

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if not self._hovering_link:
            self.clicked.emit()


class EquationTextEdit(QPlainTextEdit):
    """A word-wrapping text editor used to edit the *whole* reaction
    equation inside the overlay, filling its entire area rather than a
    single cramped line.

    The underlying reaction string is logically single-line, so Enter
    commits (emits editingFinished) instead of inserting a newline;
    losing focus also commits, mirroring QLineEdit's editingFinished so
    ReactionMask can run the exact same commit pipeline
    (reaction_data_changed) it already uses for self.equation. Escape
    discards the edit instead (emits cancelled).
    """

    editingFinished = Signal()
    cancelled = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setTabChangesFocus(True)
        self.setFrameShape(QFrame.Shape.NoFrame)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            # Commit via the same path as a normal focus-out, rather than
            # inserting a newline: the reaction string this editor stands
            # in for has no line breaks of its own.
            self.clearFocus()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.cancelled.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.editingFinished.emit()


class EquationOverlay(QFrame):
    """Popup used by ReactionMask.show_equation_overlay() to display (and,
    via EquationTextEdit, edit) the full reaction equation.

    A Qt::Popup can be dismissed in more than one way (a click outside it,
    Escape, the toggle button, or a metabolite link), so both closeEvent
    and hideEvent are used to make sure any edit still in progress in the
    overlay's (throwaway) EquationTextEdit gets committed before the
    overlay is destroyed (WA_DeleteOnClose), no matter which path
    triggered the dismissal.
    """

    def __init__(self, mask: "ReactionMask"):
        super().__init__(mask, Qt.WindowType.Popup)
        self._mask = mask
        self._closing_handled = False

    def _handle_closing_once(self):
        if not self._closing_handled:
            self._closing_handled = True
            self._mask.handle_overlay_closing()

    def closeEvent(self, event):
        self._handle_closing_once()
        super().closeEvent(event)

    def hideEvent(self, event):
        self._handle_closing_once()
        super().hideEvent(event)


class ReactionMask(QWidget):
    """The input mask for a reaction"""

    def __init__(self, parent: ReactionList):
        QWidget.__init__(self)

        self.parent: ReactionList = parent
        self.reaction = None
        self.is_valid = True
        self.equation_valid = True
        self.fba_relevant_change = False
        self.setAcceptDrops(False)
        # State for the equation overlay opened by equation_expand_button
        # (see show_equation_overlay/handle_overlay_closing): the overlay
        # itself while open (None otherwise); its current content, which is
        # either a read-only ClickableEquationLabel or -- while the user is
        # editing -- a throwaway EquationTextEdit (self.equation itself is
        # never moved into the overlay, so there is nothing shared to keep
        # track of or reclaim).
        self._equation_overlay = None
        self._overlay_label = None
        self._overlay_editor = None

        layout = QVBoxLayout()

        l = QHBoxLayout()
        label = QLabel("Id:")
        self.id = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.id)

        self.delete_button = QPushButton("Delete reaction")
        self.delete_button.setIcon(QIcon.fromTheme("edit-delete"))
        policy = QSizePolicy()
        policy.setHorizontalPolicy(QSizePolicy.Policy.Preferred)
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
        label = QLabel("Equation: ")
        self.equation = QLineEdit()
        # Read-only view of the equation with clickable metabolite links,
        # shown in place of the plain QLineEdit whenever it is not being
        # edited (see set_equation_from_reaction/enter_equation_edit_mode).
        self.equation_link_label = ClickableEquationLabel()
        self.equation_link_label.linkActivated.connect(self.jump_to_metabolite_by_id)
        self.equation_link_label.clicked.connect(self.enter_equation_edit_mode)
        # Match font and height to self.equation exactly, so that switching
        # between the two stack pages never changes the row's geometry and
        # both widgets vertically center their text within the identical
        # box (this is also why build_equation_html renders cobra's own
        # ASCII arrows rather than Unicode ones: a Unicode arrow glyph the
        # active font lacks would fall back to a different font just for
        # that character and can shift the whole line's vertical centering).
        self.equation_link_label.setFont(self.equation.font())
        self.equation_link_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.equation_link_label.setFixedHeight(self.equation.sizeHint().height())
        self.equation_stack = QStackedWidget()
        self.equation_stack.addWidget(self.equation)
        self.equation_stack.addWidget(self.equation_link_label)
        self.equation_stack.setCurrentWidget(self.equation_link_label)
        # Only shown once the equation no longer fits in the field; opens an
        # overlay with the full, multi-line, link-ified equation, and acts
        # as a close button for as long as that overlay is open.
        self.equation_expand_button = QToolButton()
        self.equation_expand_button.setText("\u25be")
        self.equation_expand_button.setToolTip("Show full reaction equation")
        self.equation_expand_button.setVisible(False)
        self.equation_expand_button.clicked.connect(self.show_equation_overlay)
        # Explicit AlignVCenter on every item in this row: QBoxLayout's
        # default behavior for an item that can't grow to fill the row
        # (like equation_link_label's fixed height, or a QLabel/QToolButton
        # at their natural size) is to pin it to the *top* of the row, not
        # center it. That's invisible as long as every item is roughly the
        # same height, but equation_expand_button is only shown for long
        # equations, and a QToolButton's natural height varies a lot by
        # style -- notably taller under Linux's Fusion/GTK-based styles
        # than under Windows' native one. Once it's the tallest item and
        # sets the row's height, the shorter equation text would otherwise
        # get shoved to the top of that taller row instead of staying
        # vertically centered in it.
        l.addWidget(label, 0, Qt.AlignmentFlag.AlignVCenter)
        l.addWidget(self.equation_stack, 0, Qt.AlignmentFlag.AlignVCenter)
        l.addWidget(self.equation_expand_button, 0, Qt.AlignmentFlag.AlignVCenter)
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

        # l = QVBoxLayout()
        # label = QLabel("Metabolites involved in this reaction:")
        # l.addWidget(label)
        # l2 = QHBoxLayout()
        # self.metabolites = QTableWidget()
        # self.metabolites.setColumnCount(2)
        # self.metabolites.setHorizontalHeaderLabels(["Id", "Name"])
        # self.metabolites.setWordWrap(False)
        # self.metabolites.verticalHeader().setVisible(False)
        # self.metabolites.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        # self.metabolites.verticalHeader().setMinimumSectionSize(self.metabolites.fontMetrics().lineSpacing())
        # self.metabolites.verticalHeader().setDefaultSectionSize(self.metabolites.fontMetrics().lineSpacing())
        # self.metabolites.setSortingEnabled(True)
        # l2.addWidget(self.metabolites)
        # l.addItem(l2)
        # self.metabolites.itemDoubleClicked.connect(
        #     self.emit_jump_to_metabolite)
        # layout.addItem(l)

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
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle("Malformed GPR rule")
            msg_box.setText("It appears that your changed GPR rule is not valid. Do you want to edit or revert your changes?")
            edit_but = msg_box.addButton("Edit GPR rule", QMessageBox.ButtonRole.RejectRole)
            revert_but = msg_box.addButton("Revert GPR rule", QMessageBox.ButtonRole.ResetRole)
            msg_box.setDefaultButton(revert_but)
            msg_box.exec()
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
            msg_box.setIcon(QMessageBox.Icon.Question)
            msg_box.setWindowTitle("Create new genes?")
            msg_box.setText("The following genes do not exist and will be added to the model:\n" +
                            ', '.join(genes_to_add))
            msg_box.setDefaultButton(msg_box.addButton(QMessageBox.StandardButton.Ok))
            edit_but = msg_box.addButton("Edit GPR rule", QMessageBox.ButtonRole.RejectRole)
            revert_but = msg_box.addButton("Revert GPR rule", QMessageBox.ButtonRole.ResetRole)
            msg_box.exec()
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
        turn_white(self.id, self.parent.appdata.is_in_dark_mode)
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
                turn_white(self.name, self.parent.appdata.is_in_dark_mode)
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
                    turn_white(self.equation, self.parent.appdata.is_in_dark_mode)
                    ok = True
            except ValueError:
                turn_red(self.equation)

            if ok:
                new_metabolites = {m.id for m in test_reaction.metabolites} - existing_metabolites
                if len(new_metabolites) > 0:
                    self.equation.blockSignals(True)
                    msg_box = QMessageBox(self)
                    msg_box.setIcon(QMessageBox.Icon.Question)
                    msg_box.setWindowTitle("Create new metabolites?")
                    msg_box.setText("The following metabolites do not exist and will be added to the model:\n" +
                                    ', '.join(new_metabolites))
                    msg_box.setDefaultButton(msg_box.addButton(QMessageBox.StandardButton.Ok)) #"Ok", QMessageBox.AcceptRole))
                    edit_but = msg_box.addButton("Edit equation", QMessageBox.ButtonRole.RejectRole)
                    revert_but = msg_box.addButton("Revert equation", QMessageBox.ButtonRole.ResetRole)
                    msg_box.exec()
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
            turn_white(self.lower_bound, self.parent.appdata.is_in_dark_mode)
            return True

    def validate_upperbound(self):
        try:
            _x = float(self.upper_bound.text())
        except ValueError:
            turn_red(self.upper_bound)
            return False
        else:
            turn_white(self.upper_bound, self.parent.appdata.is_in_dark_mode)
            return True

    def validate_coefficient(self):
        try:
            _x = float(self.coefficent.text())
        except ValueError:
            turn_red(self.coefficent)
            return False
        else:
            turn_white(self.coefficent, self.parent.appdata.is_in_dark_mode)
            return True

    def validate_mask(self):
        valid_id = self.validate_id()
        valid_name = self.validate_name()
        valid_equation = self.validate_equation()
        valid_lb = self.validate_lowerbound()
        valid_ub = self.validate_upperbound()
        valid_coefficient = self.validate_coefficient()
        # Tracked separately so refresh_equation_view() can decide whether to
        # collapse the equation field back to the link view -- that's only
        # sensible once the equation itself parses correctly, independent of
        # whether some other field (id, name, bounds, ...) is invalid.
        self.equation_valid = valid_equation
        if valid_id & valid_name & valid_equation & valid_lb & valid_ub & valid_coefficient:
            self.is_valid = True
        else:
            self.is_valid = False

    def reaction_data_changed(self):
        self.validate_mask()
        if self.is_valid:
            self.apply()
            self.update_state()
        self.refresh_equation_view()

    def update_state(self):
        self.jump_list.clear()
        for name, mmap in self.parent.appdata.project.maps.items():
            if EscherMapView in mmap:
                # creates one button even if the reaction occurs multiple times on the map
                mmap[EscherMapView].cnapy_bridge.addMapToJumpListIfReactionPresent.emit(self.id.text(), name)
            else: # CNApy map
                if self.id.text() in mmap["boxes"]:
                    self.jump_list.add(name)

        # self.metabolites.setSortingEnabled(False)
        # self.metabolites.setRowCount(0)
        # if self.parent.appdata.project.cobra_py_model.reactions.has_id(self.id.text()):
        #     reaction = self.parent.appdata.project.cobra_py_model.reactions.get_by_id(
        #         self.id.text())
        #     for row, m in enumerate(reaction.metabolites):
        #         self.metabolites.insertRow(row)
        #         id_item = QTableWidgetItem(m.id)
        #         name_item = QTableWidgetItem(m.name)
        #         id_item.setData(Qt.ItemDataRole.UserRole, m)
        #         text = "Id: " + m.id + "\nName: " + m.name
        #         id_item.setToolTip(text)
        #         name_item.setToolTip(text)
        #         self.metabolites.setItem(row, 0, id_item)
        #         self.metabolites.setItem(row, 1, name_item)
        # self.metabolites.setSortingEnabled(True)

    def emit_jump_to_map(self, name):
        self.jumpToMap.emit(name, self.id.text())

    def emit_jump_to_metabolite(self, metabolite):
        item = self.metabolites.item(metabolite.row(), 0)
        self.jumpToMetabolite.emit(str(item.data(Qt.ItemDataRole.UserRole)))

    @Slot()
    def update_reaction_string(self):
        if self.reaction is not None:
            self.set_equation_from_reaction(self.reaction)

    def build_equation_html(self, reaction: cobra.Reaction, multiline: bool = False) -> str:
        """Build a rich-text version of the reaction equation in which every
        metabolite id is a clickable link (href = metabolite id).

        Reactants/products are always ' + '-separated (breakable spaces),
        matching reaction.build_reaction_string() and letting word-wrap lay
        out several metabolites per line when there's room, rather than
        forcing one per line. With multiline=True (used for the expanded
        overlay) the arrow additionally gets its own line, visually
        separating the reactant and product sides.

        The arrow itself is rendered using cobra's own ASCII notation
        ('-->' / '<=>', HTML-escaped) rather than a Unicode arrow glyph:
        besides matching what the plain QLineEdit shows, this avoids a
        Unicode glyph missing from the active font falling back to a
        different font just for that character, which can shift the
        vertical centering of the whole line.
        """
        def format_side(metabolites, sign):
            parts = []
            for m, coeff in metabolites.items():
                coeff = coeff * sign
                factor = "" if isclose(abs(coeff), 1.0) else f"{abs(coeff):g} "
                parts.append(f'{factor}<a href="{m.id}">{m.id}</a>')
            return " + ".join(parts)

        reactants = {m: c for m, c in reaction.metabolites.items() if c < 0}
        products = {m: c for m, c in reaction.metabolites.items() if c > 0}
        lhs = format_side(reactants, -1)
        rhs = format_side(products, 1)
        arrow = "&lt;=&gt;" if reaction.reversibility else "--&gt;"
        arrow_html = f"<br>{arrow}<br>" if multiline else f" {arrow} "
        return f"{lhs}{arrow_html}{rhs}"

    def set_equation_from_reaction(self, reaction: cobra.Reaction):
        """Populate both the editable equation field and its link-ified
        display counterpart from `reaction`, and show the display view."""
        self.equation.setText(reaction.build_reaction_string())
        self.equation.setModified(False)
        self.equation_link_label.setText(self.build_equation_html(reaction))
        self.equation_link_label.set_metabolite_names(reaction)
        self.equation_stack.setCurrentWidget(self.equation_link_label)
        self.equation_valid = True
        self.update_equation_expand_button()

    def refresh_equation_view(self):
        """Called after every edit attempt on the mask (successful or not).

        Collapses the equation field back to the read-only link view once it
        holds a valid equation; otherwise leaves it in edit mode so the red
        highlight from validate_equation() stays visible to the user. Never
        interrupts an edit that is currently in progress.
        """
        if self.equation_stack.currentWidget() is self.equation and self.equation.hasFocus():
            return
        if self.equation_valid and self.reaction is not None:
            self.set_equation_from_reaction(self.reaction)
        else:
            self.equation_stack.setCurrentWidget(self.equation)

    def enter_equation_edit_mode(self):
        """Switch the equation field from the link view to the plain,
        editable QLineEdit (triggered by clicking the link view anywhere
        that isn't itself a metabolite link)."""
        self.equation_stack.setCurrentWidget(self.equation)
        self.equation.setFocus()
        #self.equation.selectAll()

    def jump_to_metabolite_by_id(self, metabolite_id: str):
        """Handle a click on a metabolite link, whether in the inline
        equation view or in the expanded overlay."""
        self.jumpToMetabolite.emit(metabolite_id)

    def update_equation_expand_button(self):
        """Show the dropdown/expand button only once the equation is too
        wide to fit in the field at its current size."""
        if self.reaction is None:
            self.equation_expand_button.setVisible(False)
            return
        metrics = self.equation_link_label.fontMetrics()
        text_width = metrics.horizontalAdvance(self.reaction.build_reaction_string())
        available_width = self.equation_link_label.width()
        self.equation_expand_button.setVisible(text_width > available_width)

    def build_overlay_label(self, overlay: "EquationOverlay") -> "ClickableEquationLabel":
        """Build the read-only, word-wrapped, link-ified equation view used
        to fill the overlay, sized (and the overlay resized) to fit its
        content exactly. Shared by show_equation_overlay (initial open) and
        restore_overlay_to_link_view (after committing an edit), so the two
        never drift out of sync.
        """
        margin = 8
        content_width = max(200, self.width() - 2 * margin)

        label = ClickableEquationLabel(overlay)
        # Reset to a plain Preferred policy for this instance: the
        # "Ignored" horizontal policy set by ClickableEquationLabel's
        # constructor (needed so the compact inline view can shrink below
        # its sizeHint instead of stretching the mask's layout) confuses
        # Qt's heightForWidth bookkeeping once word-wrap is turned on here,
        # which left a large empty band above the text instead of sizing
        # the overlay to the actual wrapped content.
        label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        label.setWordWrap(True)
        label.setText(self.build_equation_html(self.reaction, multiline=True))
        label.set_metabolite_names(self.reaction)
        label.linkActivated.connect(self.jump_to_metabolite_by_id)
        # Closing on link-click as well as on focus-out (default Popup
        # behavior) keeps the overlay from lingering after it's served its
        # purpose.
        label.linkActivated.connect(overlay.close)
        # Clicking anywhere else in the overlay's equation view switches it
        # into an editable one (see enter_equation_edit_mode_in_overlay).
        label.clicked.connect(self.enter_equation_edit_mode_in_overlay)

        # Compute the wrapped height directly for the fixed content width
        # instead of going through a layout + adjustSize(), and position
        # the label explicitly -- see the size-policy note above for why.
        label.setFixedWidth(content_width)
        label.setFixedHeight(label.heightForWidth(content_width))
        label.move(margin, margin)
        overlay.setFixedSize(content_width + 2 * margin, label.height() + 2 * margin)
        return label

    def enter_equation_edit_mode_in_overlay(self):
        """Triggered by clicking the overlay's read-only equation view
        anywhere except a metabolite link: replaces it with a throwaway
        EquationTextEdit that fills the *entire* overlay, so the whole
        (possibly very long) equation is editable at once with proper word
        wrap, rather than shrinking down to a single cramped line.

        self.equation itself is never touched here -- it stays put in
        equation_stack the whole time -- so there is nothing shared that
        could be left dangling if the overlay closes mid-edit; see
        commit_overlay_equation_edit/handle_overlay_closing for how the
        result gets written back into it.
        """
        overlay = self._equation_overlay
        if overlay is None or self._overlay_editor is not None:
            return
        self._overlay_label.hide()

        margin = 8
        editor = EquationTextEdit(overlay)
        editor.setPlainText(self.equation.text())
        editor.editingFinished.connect(self.commit_overlay_equation_edit)
        editor.cancelled.connect(self.cancel_overlay_equation_edit)
        editor.move(margin, margin)
        editor.resize(overlay.width() - 2 * margin, overlay.height() - 2 * margin)
        editor.show()
        editor.setFocus()
        #editor.selectAll()
        self._overlay_editor = editor

    def commit_overlay_equation_edit(self, closing: bool = False):
        """Write the overlay editor's text back into self.equation and run
        it through the normal validation/apply pipeline. Called on Enter,
        on focus-out (blur), and -- with closing=True -- when the overlay
        itself is being dismissed while an edit is still in progress.
        """
        if self._overlay_editor is None:
            return
        # Collapse any wrapping/whitespace introduced by the multi-line
        # display back into the single-line string self.equation expects.
        new_text = " ".join(self._overlay_editor.toPlainText().split())
        if new_text != self.equation.text():
            self.equation.setText(new_text)
            self.equation.setModified(True)
        if self.equation.isModified():
            self.reaction_data_changed()  # validates, applies and calls refresh_equation_view()
        if not closing:
            if self.equation_valid:
                self.restore_overlay_to_link_view()
            else:
                turn_red(self._overlay_editor)

    def cancel_overlay_equation_edit(self):
        """Escape in the overlay editor: discard whatever was typed and go
        back to the read-only view without touching self.equation at all."""
        self.restore_overlay_to_link_view()

    def restore_overlay_to_link_view(self):
        """Swap the overlay's editor back out for the read-only, link-ified
        view, resizing the overlay to fit the (possibly just-changed)
        equation."""
        overlay = self._equation_overlay
        if overlay is None or self._overlay_editor is None:
            return
        editor = self._overlay_editor
        self._overlay_editor = None  # cleared first: see commit_overlay_equation_edit's guard
        editor.hide()
        editor.deleteLater()
        self._overlay_label = self.build_overlay_label(overlay)
        self._overlay_label.show()

    def handle_overlay_closing(self):
        """Called by EquationOverlay before it is destroyed, however it was
        dismissed (outside click, Escape closing the whole overlay, a
        metabolite link, or the toggle button). Commits any edit still in
        progress in the overlay's editor before it goes away, and schedules
        equation_expand_button's click handler to be reconnected -- see
        show_equation_overlay for why a short real delay is used rather
        than reconnecting immediately or via a queued (0 ms) call.
        """
        if self._overlay_editor is not None:
            self.commit_overlay_equation_edit(closing=True)
        self._equation_overlay = None
        self._overlay_label = None
        self._overlay_editor = None
        self.equation_expand_button.setText("\u25be")
        self.equation_expand_button.setToolTip("Show full reaction equation")
        QTimer.singleShot(200, self._reconnect_equation_expand_button)

    @Slot()
    def _reconnect_equation_expand_button(self):
        self.equation_expand_button.clicked.connect(self.show_equation_overlay)

    def show_equation_overlay(self):
        """Show the full reaction equation, formatted with word-wrap and
        clickable metabolite links, in a popup overlay spanning the width
        of the Reactions tab.

        equation_expand_button's own clicked signal is disconnected for as
        long as the overlay stays open, and only reconnected -- after a
        short delay, see handle_overlay_closing -- once it's fully closed
        again. This is what makes the button double as a close button
        without any risk of it immediately reopening what it just closed:
        a Qt::Popup's automatic outside-click dismissal can redeliver that
        same closing click to the button underneath as an ordinary second
        click, but since nothing is connected to react to it for the
        entire time the overlay is open, that redelivered click (however
        many times it happens to fire) simply does nothing.

        The reconnect uses a short (200 ms) QTimer rather than a queued
        (0 ms) call: a queued call's ordering relative to the redelivered
        click turned out to be platform-dependent -- on Windows, hiding
        the popup appears to pump the native event queue as part of tearing
        the window down, which can drain even a 0 ms queued call before
        the redelivered click is dispatched, reconnecting too early; on
        Linux it does not. A real, if brief, delay reconnects reliably
        after both have settled on either platform, while still being far
        too short to affect a genuine, deliberate next click.
        """
        if self.reaction is None or self._equation_overlay is not None:
            return
        self.equation_expand_button.clicked.disconnect(self.show_equation_overlay)

        overlay = EquationOverlay(self)
        overlay.setFrameShape(QFrame.Shape.StyledPanel)
        overlay.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        # overlay.setAttribute(Qt.WidgetAttribute.WA_NoMouseReplay)
        # overlay.setAttribute(Qt.WidgetAttribute.WA_NoMousePropagation)
        self._equation_overlay = overlay

        # This mask sits in a vertical splitter above/below the reaction
        # list, so it already spans the Reactions tab's full width; using
        # that width (instead of a narrow fixed-size popup that can run off
        # the right edge of the window) gives word-wrap enough room to lay
        # out several metabolites per line, which is what long equations
        # like biomass reactions need.
        self._overlay_label = self.build_overlay_label(overlay)

        top_left = self.mapToGlobal(QPoint(0, 0))
        button_bottom = self.equation_expand_button.mapToGlobal(
            QPoint(0, self.equation_expand_button.height())).y()
        overlay.move(top_left.x(), button_bottom)
        self.equation_expand_button.setText("\u25b4")
        self.equation_expand_button.setToolTip("Hide full reaction equation")
        overlay.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update_equation_expand_button()

    jumpToMap = Signal(str, str)
    jumpToMetabolite = Signal(str)
    reactionChanged = Signal(cobra.Reaction)
    reactionDeleted = Signal(cobra.Reaction)
