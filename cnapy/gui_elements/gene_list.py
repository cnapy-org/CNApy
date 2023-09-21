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


class GeneList(QWidget):
    """A list of genes"""

    def __init__(self, central_widget):
        QWidget.__init__(self)
        self.appdata: AppData = central_widget.appdata
        self.central_widget = central_widget
        self.last_selected = None

        self.gene_list = QTreeWidget()
        self.gene_list.setHeaderLabels(["Id", "Name"])
        self.gene_list.setSortingEnabled(True)
        self.gene_list.sortByColumn(0, Qt.AscendingOrder)

        for m in self.appdata.project.cobra_py_model.genes:
            self.add_gene(m)
        self.gene_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.gene_list.customContextMenuRequested.connect(
            self.on_context_menu)

        # create context menu
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
        item = QTreeWidgetItem(self.gene_list)
        item.setText(0, gene.id)
        item.setText(1, gene.name)
        item.setData(2, 0, gene)

    def on_context_menu(self, point):
        if len(self.appdata.project.cobra_py_model.genes) > 0:
            self.pop_menu.exec_(self.mapToGlobal(point))

    def handle_changed_gene(self, gene: cobra.Gene):
        # Update gene item in list
        root = self.gene_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            if item.data(2, 0) == gene:
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
            gene: cobra.Gene = item.data(2, 0)

            self.gene_mask.gene = gene

            self.gene_mask.id.setText(gene.id)
            self.gene_mask.name.setText(gene.name)
            self.gene_mask.changed = False
            self.gene_mask.annotation_widget.update_annotations(gene.annotation)

            turn_white(self.gene_mask.name)
            self.gene_mask.is_valid = True
            self.gene_mask.reactions.update_state(self.gene_mask.id.text(), self.gene_mask.gene_list)
            self.central_widget.add_model_item_to_history(gene.id, gene.name, ModelItemType.Gene)

    def update(self):
        self.gene_list.clear()
        for m in self.appdata.project.cobra_py_model.genes:
            self.add_gene(m)

        if self.last_selected is None:
            self.gene_list.setCurrentItem(None)
        else:
            items = self.gene_list.findItems(
                self.last_selected, Qt.MatchExactly)

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
            turn_white(self.name)
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
