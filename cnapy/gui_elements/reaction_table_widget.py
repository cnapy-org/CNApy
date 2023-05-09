from enum import Enum
from qtpy.QtCore import Qt, Signal, Slot
from qtpy.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QAbstractItemView, QPlainTextEdit
from qtpy.QtGui import QMouseEvent, QTextCursor


class ModelElementType(Enum):
    METABOLITE = 1
    GENE = 2


class ReactionString(QPlainTextEdit):
    def __init__(self, reaction, metabolite_list):
        super().__init__()
        reaction_string = reaction.build_reaction_string() + " " # extra space to be able to click outside the equation without triggering a jump to the metabolite
        self.setPlainText(reaction_string)
        self.text_width = self.fontMetrics().horizontalAdvance(reaction_string)
        self.setReadOnly(True)
        self.model = reaction.model
        self.metabolite_list = metabolite_list

    jumpToMetabolite = Signal(str)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.LeftButton:
            text_cursor: QTextCursor = self.textCursor()
            if not text_cursor.hasSelection():
                start: int = text_cursor.position()
                text: str = self.toPlainText()
                if start >= len(text):
                    return
                while start > 0:
                    start -= 1
                    if text[start].isspace():
                        break
                text = text[start:].split(maxsplit=1)[0]
                if self.model.metabolites.has_id(text):
                    self.jumpToMetabolite.emit(text)
                    self.metabolite_list.set_current_item(text)

class ReactionTableWidget(QTableWidget):
    def __init__(self, appdata, element_type: ModelElementType) -> None:
        super().__init__()

        self.appdata = appdata
        self.element_type = element_type
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["Id", "Reaction"])
        self.horizontalHeader().setStretchLastSection(True)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.horizontalHeader().sectionResized.connect(self.section_resized)

    def update_state(self, id_text, metabolite_list):
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
                item.setToolTip(reaction.name)
                self.setItem(i, 0, item)
                reaction_string_widget = ReactionString(reaction, metabolite_list)
                reaction_string_widget.jumpToMetabolite.connect(self.emit_jump_to_metabolite)
                self.setCellWidget(i, 1, reaction_string_widget)
            self.setSortingEnabled(True)
        QApplication.restoreOverrideCursor()

    @Slot(int, int, int)
    def section_resized(self, index: int, old_size: int, new_size: int):
        if index == 1 and old_size != new_size:
            for row in range(self.rowCount()):
                reaction_string_widget: ReactionString = self.cellWidget(row, index)
                base_height = reaction_string_widget.fontMetrics().height()
                # TODO: determined 12 empirically, but how programmatically?
                if reaction_string_widget.text_width + 12 > new_size:
                    reaction_string_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                    self.setRowHeight(row, base_height*2 + 12)
                else:
                    reaction_string_widget.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                    self.setRowHeight(row, base_height + 12)

    jumpToMetabolite = Signal(str)
    def emit_jump_to_metabolite(self, metabolite):
        self.jumpToMetabolite.emit(metabolite)
