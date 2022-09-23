from enum import Enum
from qtpy.QtCore import Qt, Signal, Slot
from qtpy.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QAbstractItemView, QPlainTextEdit


class ModelElementType(Enum):
    METABOLITE = 1
    GENE = 2


class ReactionString(QPlainTextEdit):
    def __init__(self, reaction, metabolite_or_gene_list):
        super().__init__()
        self.setPlainText(reaction.build_reaction_string())
        self.setReadOnly(True)
        self.model = reaction.model
        self.metabolite_or_gene_list = metabolite_or_gene_list
        self.selectionChanged.connect(self.switch_metabolite)

    @Slot()
    def switch_metabolite(self):
        selected_text = self.textCursor().selectedText()
        if self.model.metabolites.has_id(selected_text):
            self.metabolite_or_gene_list.set_current_item(selected_text)


class ReactionTreeWidget(QTableWidget):
    def __init__(self, appdata, element_type: ModelElementType) -> None:
        super().__init__()

        self.appdata = appdata
        self.element_type = element_type
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["Id", "Reaction"])
        self.horizontalHeader().setStretchLastSection(True)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)

    def update_state(self, id_text, metabolite_or_gene_list):
        QApplication.setOverrideCursor(Qt.BusyCursor)
        QApplication.processEvents() # to put the change above into effect
        self.clearContents()
        self.setRowCount(0) # also resets manually changed row heights

        if self.element_type is ModelElementType.METABOLITE:
            model_elements = self.appdata.project.cobra_py_model.metabolites
        elif self.element_type is ModelElementType.GENE:
            model_elements = self.appdata.project.cobra_py_model.genes

        if model_elements.has_id(id_text):
            metabolite_or_gene = model_elements.get_by_id(
                id_text
            )
            self.setSortingEnabled(False)
            self.setRowCount(len(metabolite_or_gene.reactions))
            for i, reaction in enumerate(metabolite_or_gene.reactions):
                item = QTableWidgetItem(reaction.id)
                self.setItem(i, 0, item)
                reaction_string_widget = ReactionString(reaction, metabolite_or_gene_list)
                self.setCellWidget(i, 1, reaction_string_widget)
            self.setSortingEnabled(True)
        QApplication.restoreOverrideCursor()
