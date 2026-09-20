from enum import Enum
from qtpy.QtCore import Qt, Signal, Slot
from qtpy.QtWidgets import QApplication, QTableWidget, QTableWidgetItem, QAbstractItemView, QTextEdit, QFrame, QToolTip
from qtpy.QtGui import QMouseEvent

from cnapy.gui_elements.reactions_list import build_reaction_equation_html


class ModelElementType(Enum):
    METABOLITE = 1
    GENE = 2


class ReactionString(QTextEdit):
    """Read-only display of a reaction equation with clickable metabolite
    links, built the exact same way (build_reaction_equation_html) as the
    Equation field in ReactionMask: every metabolite id is an HTML link
    (href = metabolite id) and a click is resolved via anchorAt() rather
    than by guessing word boundaries in plain text.
    """

    def __init__(self, reaction, metabolite_list):
        super().__init__()
        self.setReadOnly(True)
        self.setFrameStyle(QFrame.Shape.NoFrame)
        self.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self.setTextInteractionFlags(
            Qt.TextInteractionFlag.LinksAccessibleByMouse | Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.setMouseTracking(True)
        self.setHtml(build_reaction_equation_html(reaction))
        # Natural (unwrapped) width of the equation, used by
        # ReactionTableWidget.section_resized to decide whether the row
        # needs a second line.
        self.document().setTextWidth(-1)
        self.text_width = self.document().idealWidth()
        self.model = reaction.model
        self.metabolite_list = metabolite_list

    jumpToMetabolite = Signal(str)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        link = self.anchorAt(event.pos())
        if link and self.model.metabolites.has_id(link):
            self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
            QToolTip.showText(event.globalPos(), self.model.metabolites.get_by_id(link).name, self)
        else:
            self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
            QToolTip.hideText()

    def mouseReleaseEvent(self, event: QMouseEvent):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and not self.textCursor().hasSelection():
            metabolite_id = self.anchorAt(event.pos())
            if metabolite_id and self.model.metabolites.has_id(metabolite_id):
                self.jumpToMetabolite.emit(metabolite_id)
                self.metabolite_list.set_current_item(metabolite_id)

class ReactionTableWidget(QTableWidget):
    def __init__(self, appdata, element_type: ModelElementType) -> None:
        super().__init__()

        self.appdata = appdata
        self.element_type = element_type
        self.setColumnCount(2)
        self.setHorizontalHeaderLabels(["Id", "Reaction"])
        self.horizontalHeader().setStretchLastSection(True)
        self.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.horizontalHeader().sectionResized.connect(self.section_resized)

    def update_state(self, id_text, metabolite_list):
        QApplication.setOverrideCursor(Qt.CursorShape.BusyCursor)
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
        self.section_resized(1, self.horizontalHeader().sectionSize(1), self.horizontalHeader().sectionSize(1))
        QApplication.restoreOverrideCursor()

    @Slot(int, int, int)
    def section_resized(self, index: int, old_size: int, new_size: int):
        if index == 1:
            for row in range(self.rowCount()):
                reaction_string_widget: ReactionString = self.cellWidget(row, index)
                font_metrics= reaction_string_widget.fontMetrics()
                base_height = font_metrics.lineSpacing()
                margins = reaction_string_widget.contentsMargins()
                height_margin = 12
                if reaction_string_widget.text_width + margins.left() + margins.right() > new_size:
                    reaction_string_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
                    self.setRowHeight(row, base_height*2 + font_metrics.leading() + height_margin) # font_metrics.leading(): space between two lines
                else:
                    reaction_string_widget.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
                    self.setRowHeight(row, base_height + height_margin)

    jumpToMetabolite = Signal(str)
    def emit_jump_to_metabolite(self, metabolite):
        self.jumpToMetabolite.emit(metabolite)
