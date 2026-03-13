"""The gene list"""

import cobra
import cobra.manipulation
from qtpy.QtCore import Qt, Signal, Slot
from qtpy.QtWidgets import (QAction, QHBoxLayout, QLabel,
                            QLineEdit, QMenu, QMessageBox, QPushButton, QSizePolicy, QSplitter,
                            QTableWidgetItem, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from cnapy.appdata import AppData, ModelItemType
from cnapy.utils import SignalThrottler, turn_red, turn_white, update_selected
from cnapy.gui_elements.annotation_widget import AnnotationWidget
from cnapy.gui_elements.reaction_table_widget import ModelElementType, ReactionTableWidget


class GeneTreeWidgetItem(QTreeWidgetItem):
    """QTreeWidgetItem that sorts the Active column by check state."""

    def __lt__(self, other):
        col = self.treeWidget().sortColumn()
        if col == 2:  # Active column — sort by UserRole (1=active, 0=KO)
            return (self.data(2, Qt.UserRole) or 0) < (other.data(2, Qt.UserRole) or 0)
        return super().__lt__(other)


class GeneList(QWidget):
    """A list of genes"""

    def __init__(self, central_widget):
        QWidget.__init__(self)
        self.appdata: AppData = central_widget.appdata
        self.central_widget = central_widget
        self.last_selected = None

        self.gene_list = QTreeWidget()
        self.gene_list.setHeaderLabels(["Id", "Name", "Active"])
        self.gene_list.setSortingEnabled(True)
        self.gene_list.sortByColumn(0, Qt.AscendingOrder)

        for m in self.appdata.project.cobra_py_model.genes:
            self.add_gene(m)
        self.gene_list.setColumnWidth(2, 55)
        self.gene_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.gene_list.customContextMenuRequested.connect(
            self.on_context_menu)

        # create context menu
        self.pop_menu = QMenu(self.gene_list)
        ko_action = QAction("Knock out this gene", self.gene_list)
        ko_action.triggered.connect(self.knockout_selected_gene)
        self.pop_menu.addAction(ko_action)
        restore_action = QAction("Restore this gene", self.gene_list)
        restore_action.triggered.connect(self.restore_selected_gene)
        self.pop_menu.addAction(restore_action)
        self.pop_menu.addSeparator()
        restore_all_action = QAction("Restore all genes", self.gene_list)
        restore_all_action.triggered.connect(self.restore_all_genes)
        self.pop_menu.addAction(restore_all_action)

        self.gene_mask = GenesMask(self, self.appdata)
        self.gene_mask.hide()

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Vertical)
        self.splitter.addWidget(self.gene_list)
        self.splitter.addWidget(self.gene_mask)
        self.layout.addWidget(self.splitter)
        self.setLayout(self.layout)

        self.gene_list.currentItemChanged.connect(
            self.gene_selected)
        self.gene_list.itemChanged.connect(
            self._on_item_changed)
        self.gene_mask.geneChanged.connect(
            self.handle_changed_gene)
        self.gene_mask.jumpToReaction.connect(
            self.emit_jump_to_reaction)
        self.gene_mask.jumpToMetabolite.connect(
            self.emit_jump_to_metabolite
        )

    def clear(self):
        self.gene_list.clear()
        self.gene_mask.hide()

    def add_gene(self, gene):
        item = GeneTreeWidgetItem(self.gene_list)
        item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
        item.setText(0, gene.id)
        item.setText(1, gene.name)
        item.setCheckState(2, Qt.Checked)
        item.setData(2, Qt.UserRole, 1)  # sort key: 1=active, 0=KO
        item.setData(3, 0, gene)

    def on_context_menu(self, point):
        if len(self.appdata.project.cobra_py_model.genes) > 0:
            self.pop_menu.exec_(self.mapToGlobal(point))

    def handle_changed_gene(self, gene: cobra.Gene):
        # Update gene item in list
        root = self.gene_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            if item.data(3, 0) == gene:
                old_id = item.text(0)
                item.setText(0, gene.id)
                item.setText(1, gene.name)
                break

        for reaction_x in self.appdata.project.cobra_py_model.reactions:
            reaction: cobra.Reaction = reaction_x
            gpr = reaction.gene_reaction_rule + " "
            if old_id in gpr:
                reaction.gene_reaction_rule = gpr.replace(old_id+" ", gene.id+" ").strip()

        self.last_selected = self.gene_mask.id.text()
        self.geneChanged.emit(old_id, gene)

    def update_selected(self, string, with_annotations):
        return update_selected(
            string=string,
            with_annotations=with_annotations,
            model_elements=self.appdata.project.cobra_py_model.genes,
            element_list=self.gene_list,
        )

    def gene_selected(self, item, _column):
        if item is None:
            self.gene_mask.hide()
        else:
            self.gene_mask.show()
            gene: cobra.Gene = item.data(3, 0)

            self.gene_mask.gene = gene

            self.gene_mask.id.setText(gene.id)
            self.gene_mask.name.setText(gene.name)
            self.gene_mask.changed = False
            self.gene_mask.annotation_widget.update_annotations(gene.annotation)

            turn_white(self.gene_mask.name, self.appdata.is_in_dark_mode)
            self.gene_mask.is_valid = True
            self.gene_mask.reactions.update_state(self.gene_mask.id.text(), self.gene_mask.gene_list)
            self.central_widget.add_model_item_to_history(gene.id, gene.name, ModelItemType.Gene)

    def update(self):
        # Preserve KO states across update
        ko_genes = self.get_knocked_out_genes()
        self.gene_list.blockSignals(True)
        self.gene_list.clear()
        for m in self.appdata.project.cobra_py_model.genes:
            self.add_gene(m)
        # Restore KO states
        for gene_id in ko_genes:
            items = self.gene_list.findItems(gene_id, Qt.MatchExactly, 0)
            for item in items:
                item.setCheckState(2, Qt.Unchecked)
                item.setData(2, Qt.UserRole, 0)
        self.gene_list.blockSignals(False)

        if self.last_selected is None:
            self.gene_list.setCurrentItem(None)
        else:
            items = self.gene_list.findItems(
                self.last_selected, Qt.MatchExactly, 0)

            for i in items:
                self.gene_list.setCurrentItem(i)
                self.gene_list.scrollToItem(i)
                break

    def set_current_item(self, key):
        self.last_selected = key
        self.update()

    def emit_jump_to_reaction(self, item: QTableWidgetItem):
        self.jumpToReaction.emit(item)

    def emit_jump_to_metabolite(self, metabolite):
        self.jumpToMetabolite.emit(metabolite)

    def _on_item_changed(self, item, column):
        """When a checkbox is toggled, update sort key and scenario."""
        if column == 2:
            item.setData(2, Qt.UserRole, 1 if item.checkState(2) == Qt.Checked else 0)
            self.apply_gene_kos()

    def get_knocked_out_genes(self):
        """Return list of gene IDs for unchecked (knocked-out) genes."""
        ko_genes = []
        root = self.gene_list.invisibleRootItem()
        for i in range(root.childCount()):
            item = root.child(i)
            if item.checkState(2) == Qt.Unchecked:
                ko_genes.append(item.text(0))  # gene ID in column 0
        return ko_genes

    def knockout_selected_gene(self):
        """Uncheck the currently selected gene."""
        item = self.gene_list.currentItem()
        if item is not None:
            item.setCheckState(2, Qt.Unchecked)

    def restore_selected_gene(self):
        """Re-check the currently selected gene."""
        item = self.gene_list.currentItem()
        if item is not None:
            item.setCheckState(2, Qt.Checked)

    def restore_all_genes(self):
        """Re-check all genes and clear gene KO scenario values."""
        self.gene_list.blockSignals(True)
        root = self.gene_list.invisibleRootItem()
        for i in range(root.childCount()):
            root.child(i).setCheckState(2, Qt.Checked)
        self.gene_list.blockSignals(False)
        self._clear_gene_ko_scenario_values()
        self.central_widget.update()

    def _clear_gene_ko_scenario_values(self):
        """Remove scenario values that were set by gene KO simulation."""
        if hasattr(self, '_last_ko_reactions'):
            for r_id in self._last_ko_reactions:
                self.appdata.scen_values_pop(r_id)
            self._last_ko_reactions = set()

    def apply_gene_kos(self, silent=False):
        """Evaluate GPR rules for unchecked genes and set affected reactions to 0 in scenario.

        When called from checkbox toggle (silent=True via _on_item_changed),
        no message boxes are shown.
        """
        from straindesign.networktools import gene_kos_to_constraints

        # First, clear previous gene KO scenario values
        self._clear_gene_ko_scenario_values()

        ko_genes = self.get_knocked_out_genes()
        if not ko_genes:
            self.central_widget.update()
            return

        model = self.appdata.project.cobra_py_model
        constraints = gene_kos_to_constraints(model, ko_genes)

        # Set affected reactions to (0, 0) in the scenario
        reactions = []
        values = []
        for c in constraints:
            r_id = list(c[0].keys())[0]
            reactions.append(r_id)
            values.append((0.0, 0.0))

        # Track which reactions we set so restore_all can undo them
        self._last_ko_reactions = set(reactions)

        if reactions:
            self.appdata.scen_values_set_multiple(reactions, values)
        self.central_widget.update()
        if reactions:
            self.central_widget.console._append_plain_text(
                f"\nGene KO: {len(ko_genes)} gene(s) knocked out, "
                f"{len(reactions)} reaction(s) set to 0: {', '.join(reactions)}",
                before_prompt=True)

    itemActivated = Signal(str)
    geneChanged = Signal(str, cobra.Gene)
    jumpToReaction = Signal(str)
    jumpToMetabolite = Signal(str)
    computeInOutFlux = Signal(str)


class GenesMask(QWidget):
    """The input mask for a genes"""

    def __init__(self, gene_list, appdata):
        QWidget.__init__(self)
        self.gene_list = gene_list
        self.appdata = appdata
        self.gene = None
        self.is_valid = True
        self.changed = False
        self.setAcceptDrops(False)

        layout = QVBoxLayout()
        l = QHBoxLayout()
        label = QLabel("Id:")
        self.id = QLabel("")
        l.addWidget(label)
        l.addWidget(self.id)
        layout.addItem(l)

        self.delete_button = QPushButton("Delete gene")
        self.delete_button.setToolTip(
            "Delete this gene and remove it from associated reactions."
        )
        policy = QSizePolicy()
        policy.ShrinkFlag = True
        self.delete_button.setSizePolicy(policy)
        l.addWidget(self.delete_button)

        l = QHBoxLayout()
        label = QLabel("Name:")
        self.name = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.name)
        layout.addItem(l)

        self.throttler = SignalThrottler(500)
        self.throttler.triggered.connect(self.genes_data_changed)

        self.annotation_widget = AnnotationWidget(self)
        layout.addItem(self.annotation_widget)

        l = QVBoxLayout()
        label = QLabel("Reactions using this gene:")
        l.addWidget(label)
        l2 = QHBoxLayout()
        self.reactions = ReactionTableWidget (self.appdata, ModelElementType.GENE)
        l2.addWidget(self.reactions)
        l.addItem(l2)
        self.reactions.itemDoubleClicked.connect(self.emit_jump_to_reaction)
        self.reactions.jumpToMetabolite.connect(self.emit_jump_to_metabolite)
        layout.addItem(l)

        self.setLayout(layout)


        self.delete_button.clicked.connect(self.delete_gene)
        self.name.textEdited.connect(self.throttler.throttle)

        self.annotation_widget.deleteAnnotation.connect(
            self.delete_selected_annotation
        )

        self.validate_mask()

    def add_anno_row(self):
        i = self.annotation.rowCount()
        self.annotation.insertRow(i)
        self.changed = True

    def apply(self):
        try:
            self.gene.name = self.name.text()
            self.annotation_widget.apply_annotation(self.gene)
            self.changed = False
            self.geneChanged.emit(self.gene)
        except ValueError:
            turn_red(self.name)
            QMessageBox.information(
                self, 'Invalid name', 'Could not apply name ' +
                self.name.text()+'.')

    def delete_gene(self):
        cobra.manipulation.remove_genes(
            model=self.appdata.project.cobra_py_model,
            gene_list=[self.gene],
            remove_reactions=False,
        )
        self.appdata.window.unsaved_changes()
        self.hide()
        current_row_index = self.gene_list.gene_list.currentIndex().row()
        self.gene_list.gene_list.setCurrentItem(None)
        self.gene_list.last_selected = None
        self.gene_list.gene_list.takeTopLevelItem(
            current_row_index)
        self.appdata.window.setFocus()

    def delete_selected_annotation(self, identifier_key):
        try:
            del(self.gene.annotation[identifier_key])
            self.appdata.window.unsaved_changes()
        except IndexError:
            pass

    def validate_name(self):
        try:
            cobra.Gene(id="test_id", name=self.name.text())
        except ValueError:
            turn_red(self.name)
            return False
        else:
            turn_white(self.name, self.appdata.is_in_dark_mode)
            return True

    def validate_mask(self):
        valid_name = self.validate_name()
        if valid_name:
            self.is_valid = True
        else:
            self.is_valid = False

    def genes_data_changed(self):
        self.changed = True
        self.validate_mask()
        if self.is_valid:
            self.apply()
            self.reactions.update_state(self.id.text(), self.gene_list)

    @Slot(QTableWidgetItem)
    def emit_jump_to_reaction(self, item: QTableWidgetItem):
        self.jumpToReaction.emit(item.text())

    def emit_jump_to_metabolite(self, metabolite):
        self.jumpToMetabolite.emit(metabolite)

    jumpToReaction = Signal(str)
    jumpToMetabolite = Signal(str)
    geneChanged = Signal(cobra.Gene)
