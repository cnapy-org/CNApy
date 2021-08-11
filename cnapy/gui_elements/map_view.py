"""The PyNetAnalyzer map view"""
import math
from ast import literal_eval as make_tuple
from math import isclose
from typing import Dict, Tuple

from qtpy.QtCore import QMimeData, QRectF, Qt, Signal
from qtpy.QtGui import QPen, QColor, QDrag, QMouseEvent, QPainter, QFont
from qtpy.QtSvg import QGraphicsSvgItem
from qtpy.QtWidgets import (QApplication, QAction, QGraphicsItem, QGraphicsScene,
                            QGraphicsSceneDragDropEvent,
                            QGraphicsSceneMouseEvent, QGraphicsView,
                            QLineEdit, QMenu, QWidget, QGraphicsProxyWidget)

from cnapy.appdata import AppData

INCREASE_FACTOR = 1.1
DECREASE_FACTOR = 1/INCREASE_FACTOR


class MapView(QGraphicsView):
    """A map of reaction boxes"""

    def __init__(self, appdata: AppData, name: str):
        self.scene = QGraphicsScene()
        QGraphicsView.__init__(self, self.scene)
        palette = self.palette()
        self.setPalette(palette)
        self.setInteractive(True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.appdata = appdata
        self.name = name
        self.setAcceptDrops(True)
        self.drag = False
        self.reaction_boxes: Dict[str, ReactionBox] = {}
        self._zoom = 0
        self.drag = False
        self.drag_start = None
        self.select = False
        self.select_start = None

        # initial scale
        self._zoom = self.appdata.project.maps[self.name]["zoom"]
        if self._zoom > 0:
            for _ in range(1, self._zoom):
                self.scale(INCREASE_FACTOR, INCREASE_FACTOR)
        if self._zoom < 0:
            for _ in range(self._zoom, -1):
                self.scale(DECREASE_FACTOR, DECREASE_FACTOR)

        # connect events to methods
        self.horizontalScrollBar().valueChanged.connect(self.on_hbar_change)
        self.verticalScrollBar().valueChanged.connect(self.on_vbar_change)

        self.rebuild_scene()
        self.update()

    def on_hbar_change(self, x):
        self.appdata.project.maps[self.name]["pos"] = (
            x, self.verticalScrollBar().value())

    def on_vbar_change(self, y):
        self.appdata.project.maps[self.name]["pos"] = (
            self.horizontalScrollBar().value(), y)

    def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
        event.setAccepted(True)
        event.accept()
        event.acceptProposedAction()

    def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent):
        event.setAccepted(True)
        point = event.pos()
        point_item = self.mapToScene(point)
        r_id = event.mimeData().text()

        if r_id in self.appdata.project.maps[self.name]["boxes"].keys():
            old = self.appdata.project.maps[self.name]["boxes"][r_id]
            move_x = point_item.x() - old[0]
            move_y = point_item.y() - old[1]

            selected = self.scene.selectedItems()
            for item in selected:
                pos = self.appdata.project.maps[self.name]["boxes"][item.id]

                self.appdata.project.maps[self.name]["boxes"][item.id] = (
                    pos[0]+move_x, pos[1]+move_y)
                self.mapChanged.emit(item.id)

        else:
            self.appdata.project.maps[self.name]["boxes"][r_id] = (
                point_item.x(), point_item.y())
            self.reactionAdded.emit(r_id)
            self.rebuild_scene()  # TDOO don't rebuild the whole scene only add one item

        self.update()

    def dragLeaveEvent(self, _event):
        self.update()

    def dropEvent(self, event: QGraphicsSceneDragDropEvent):
        self.drag = False
        point = event.pos()
        point_item = self.mapToScene(point)
        identifier = event.mimeData().text()
        self.appdata.project.maps[self.name]["boxes"][identifier] = (
            point_item.x(), point_item.y())
        self.mapChanged.emit(identifier)
        self.update()

    def wheelEvent(self, event):
        modifiers = QApplication.queryKeyboardModifiers()
        if modifiers == Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.appdata.project.maps[self.name]["box-size"] *= INCREASE_FACTOR
            else:
                self.appdata.project.maps[self.name]["box-size"] *= DECREASE_FACTOR

            self.mapChanged.emit("dummy")
            self.update()
        else:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()

    def fit(self):
        self.fitInView(self.scene.sceneRect(), Qt.KeepAspectRatio)

    def zoom_in(self):
        self._zoom += 1

        self.appdata.project.maps[self.name]["zoom"] = self._zoom
        self.scale(INCREASE_FACTOR, INCREASE_FACTOR)

    def zoom_out(self):
        self._zoom -= 1

        self.appdata.project.maps[self.name]["zoom"] = self._zoom
        self.scale(DECREASE_FACTOR, DECREASE_FACTOR)

    def mousePressEvent(self, event: QMouseEvent):
        modifiers = QApplication.queryKeyboardModifiers()
        if modifiers == Qt.ShiftModifier:
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.select = True
            self.select_start = self.mapToScene(event.pos())

        else:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.drag = True
            self.drag_start = event.pos()

        self.setCursor(Qt.ClosedHandCursor)
        super(MapView, self).mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self.drag:
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        super(MapView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.drag:
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)

        if self.select:
            point = self.mapToScene(event.pos())

            width = point.x() - self.select_start.x()
            height = point.y() - self.select_start.y()
            selected = self.scene.items(
                QRectF(self.select_start.x(), self.select_start.y(), width, height))

            for item in selected:
                if isinstance(item, QGraphicsProxyWidget):
                    item.widget().parent.setSelected(True)

        painter = QPainter()
        self.render(painter)

        self.select = False
        self.drag = False
        self.setCursor(Qt.OpenHandCursor)
        super(MapView, self).mouseReleaseEvent(event)

    def update_selected(self, string):

        for r_id in self.reaction_boxes:
            if string.lower() in r_id.lower():
                self.reaction_boxes[r_id].item.setHidden(False)
            elif string.lower() in self.reaction_boxes[r_id].name.lower():
                self.reaction_boxes[r_id].item.setHidden(False)
            else:
                self.reaction_boxes[r_id].item.setHidden(True)

    def focus_reaction(self, reaction: str):
        x = self.appdata.project.maps[self.name]["boxes"][reaction][0]
        y = self.appdata.project.maps[self.name]["boxes"][reaction][1]
        self.centerOn(x, y)
        self.zoom_in_reaction()

    def zoom_in_reaction(self):

        bg_size = self.appdata.project.maps[self.name]["bg-size"]
        print("zoom:", self._zoom, "bg-size:", bg_size)
        x = (INCREASE_FACTOR ** self._zoom)/bg_size
        while x < 1:
            x = (INCREASE_FACTOR ** self._zoom)/bg_size
            self._zoom += 1
            self.appdata.project.maps[self.name]["zoom"] = self._zoom
            self.scale(INCREASE_FACTOR, INCREASE_FACTOR)

    def highlight_reaction(self, string):
        treffer = self.reaction_boxes[string]
        treffer.item.setHidden(False)
        treffer.set_color(Qt.magenta)
        treffer.item.setFocus()

    def rebuild_scene(self):
        self.scene.clear()
        background = QGraphicsSvgItem(
            self.appdata.project.maps[self.name]["background"])
        background.setFlags(QGraphicsItem.ItemClipsToShape)
        background.setScale(self.appdata.project.maps[self.name]["bg-size"])

        self.scene.addItem(background)

        for r_id in self.appdata.project.maps[self.name]["boxes"]:
            try:
                name = self.appdata.project.cobra_py_model.reactions.get_by_id(
                    r_id).name
                box = ReactionBox(self, r_id, name)

                self.scene.addItem(box)
                box.add_line_widget()
                self.reaction_boxes[r_id] = box
            except KeyError:
                print("failed to add reaction box for", r_id)

    def update(self):
        for item in self.scene.items():
            if isinstance(item, QGraphicsSvgItem):
                item.setScale(
                    self.appdata.project.maps[self.name]["bg-size"])
            elif isinstance(item, ReactionBox):
                item.setScale(self.appdata.project.maps[self.name]["box-size"])
                item.proxy.setScale(
                    self.appdata.project.maps[self.name]["box-size"])
                item.setPos(self.appdata.project.maps[self.name]["boxes"][item.id]
                            [0], self.appdata.project.maps[self.name]["boxes"][item.id][1])
            else:
                pass

        self.set_values()
        self.recolor_all()

        # set scrollbars
        self.horizontalScrollBar().setValue(
            self.appdata.project.maps[self.name]["pos"][0])
        self.verticalScrollBar().setValue(
            self.appdata.project.maps[self.name]["pos"][1])

    def recolor_all(self):
        for r_id in self.appdata.project.maps[self.name]["boxes"]:
            if r_id in self.appdata.project.scen_values.keys():
                self.reaction_boxes[r_id].recolor()
            elif r_id in self.appdata.project.comp_values.keys():
                self.reaction_boxes[r_id].recolor()

    def set_values(self):
        for r_id in self.appdata.project.maps[self.name]["boxes"]:
            if r_id in self.appdata.project.scen_values.keys():
                self.reaction_boxes[r_id].set_value(
                    self.appdata.project.scen_values[r_id])
            elif r_id in self.appdata.project.comp_values.keys():
                self.reaction_boxes[r_id].set_value(
                    self.appdata.project.comp_values[r_id])

    def remove_box(self, reaction: str):
        box = self.reaction_boxes[reaction]
        lineedit = box.proxy
        self.scene.removeItem(lineedit)
        self.scene.removeItem(box)
        del self.appdata.project.maps[self.name]["boxes"][reaction]
        del self.reaction_boxes[reaction]
        self.update()
        self.reactionRemoved.emit(reaction)

    def value_changed(self, reaction: str, value: str):
        self.reactionValueChanged.emit(reaction, value)
        self.reaction_boxes[reaction].recolor()

    switchToReactionMask = Signal(str)
    maximizeReaction = Signal(str)
    minimizeReaction = Signal(str)
    reactionRemoved = Signal(str)
    reactionValueChanged = Signal(str, str)
    reactionAdded = Signal(str)
    mapChanged = Signal(str)


class CLineEdit(QLineEdit):
    """A special line edit implementation for the use in ReactionBox"""

    def __init__(self, parent):
        self.parent = parent
        super().__init__()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if not validate_value(self.text()):
            self.parent.map.set_values()
            if self.parent.id in self.parent.map.appdata.project.scen_values.keys():
                self.parent.map.reaction_boxes[self.parent.id].set_value(
                    self.parent.map.appdata.project.scen_values[self.parent.id])
            elif self.parent.id in self.parent.map.appdata.project.comp_values.keys():
                self.parent.map.reaction_boxes[self.parent.id].set_value(
                    self.parent.map.appdata.project.comp_values[self.parent.id])
            else:
                self.setText("")
        self.parent.recolor()
        self.parent.update()

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self.parent.switch_to_reaction_mask()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if (event.button() == Qt.MouseButton.LeftButton):
            self.parent.setSelected(True)
            
        self.setCursor(Qt.ClosedHandCursor)

        super().mousePressEvent(event)

class ReactionBox(QGraphicsItem):
    """Handle to the line edits on the map"""

    def __init__(self, parent: MapView, r_id: str, name):
        QGraphicsItem.__init__(self)

        self.map = parent
        self.id = r_id
        self.name = name

        self.setFlags(QGraphicsItem.ItemIsSelectable)
        self.item = CLineEdit(self)
        self.item.setTextMargins(1, -13, 0, -10)  # l t r b
        font = self.item.font()
        point_size = font.pointSize()
        font.setPointSize(point_size+13)
        self.item.setFont(font)
        self.item.setAttribute(Qt.WA_TranslucentBackground)

        self.item.setMaximumWidth(self.map.appdata.box_width)
        self.item.setMaximumHeight(self.map.appdata.box_height)
        self.item.setMinimumHeight(self.map.appdata.box_height)
        r = self.map.appdata.project.cobra_py_model.reactions.get_by_id(r_id)
        text = "Id: " + r.id + "\nName: " + r.name \
            + "\nEquation: " + r.build_reaction_string()\
            + "\nLowerbound: " + str(r.lower_bound) \
            + "\nUpper bound: " + str(r.upper_bound) \
            + "\nObjective coefficient: " + str(r.objective_coefficient)

        self.item.setToolTip(text)

        self.proxy = None  # proxy is set in add_line_widget after the item has been added

        self.set_default_style()

        self.setCursor(Qt.OpenHandCursor)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.item.textEdited.connect(self.value_changed)
        self.item.returnPressed.connect(self.returnPressed)

        self.item.setContextMenuPolicy(Qt.CustomContextMenu)
        self.item.customContextMenuRequested.connect(self.on_context_menu)

        # create context menu
        self.pop_menu = QMenu(parent)
        maximize_action = QAction('maximize flux for this reaction', parent)
        self.pop_menu.addAction(maximize_action)
        maximize_action.triggered.connect(self.emit_maximize_action)
        minimize_action = QAction('minimize flux for this reaction', parent)
        self.pop_menu.addAction(minimize_action)
        minimize_action.triggered.connect(self.emit_minimize_action)
        switch_action = QAction('switch to reaction mask', parent)
        self.pop_menu.addAction(switch_action)
        switch_action.triggered.connect(self.switch_to_reaction_mask)
        remove_action = QAction('remove from map', parent)
        self.pop_menu.addAction(remove_action)
        remove_action.triggered.connect(self.remove)

        self.pop_menu.addSeparator()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if (event.button() == Qt.MouseButton.LeftButton):
            self.setSelected(True)
            

        self.setCursor(Qt.ClosedHandCursor)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        self.setCursor(Qt.OpenHandCursor)
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        drag = QDrag(event.widget())
        mime = QMimeData()
        mime.setText(str(self.id))
        drag.setMimeData(mime)
        drag.exec_()

    def add_line_widget(self):
        self.proxy = self.map.scene.addWidget(self.item)
        self.proxy.show()

    def returnPressed(self):
        if validate_value(self.item.text()):
            self.map.value_changed(self.id, self.item.text())

    def value_changed(self):
        test = self.item.text().replace(" ", "")
        if test == "":
            self.map.value_changed(self.id, test)
            self.set_default_style()
        elif validate_value(self.item.text()):
            self.map.value_changed(self.id, self.item.text())
            if self.id in self.map.appdata.project.scen_values.keys():
                self.set_scen_style()
            else:
                self.set_comp_style()
        else:
            self.set_error_style()

    def set_default_style(self):
        ''' set the reaction box to error style'''
        palette = self.item.palette()
        role = self.item.backgroundRole()
        color = self.map.appdata.default_color
        color.setAlphaF(0.4)
        palette.setColor(role, color)
        role = self.item.foregroundRole()
        palette.setColor(role, Qt.black)
        self.item.setPalette(palette)

        self.set_font_style(QFont.StyleNormal)

    def set_error_style(self):
        ''' set the reaction box to error style'''
        self.set_color(Qt.white)
        self.set_fg_color(self.map.appdata.scen_color_bad)
        self.set_font_style(QFont.StyleOblique)

    def set_comp_style(self):
        self.set_color(self.map.appdata.comp_color)
        self.set_font_style(QFont.StyleNormal)

    def set_scen_style(self):
        self.set_color(self.map.appdata.scen_color)
        self.set_font_style(QFont.StyleNormal)

    def set_value(self, value: Tuple[float, float]):
        ''' Sets the text of and reaction box according to the given value'''
        (vl, vu) = value
        if isclose(vl, vu, abs_tol=self.map.appdata.abs_tol):
            self.item.setText(
                str(round(float(vl), self.map.appdata.rounding)).rstrip("0").rstrip("."))
        else:
            self.item.setText(
                str(round(float(vl), self.map.appdata.rounding)).rstrip("0").rstrip(".")+", "+str(round(float(vu), self.map.appdata.rounding)).rstrip("0").rstrip("."))
        self.item.setCursorPosition(0)

    def recolor(self):
        value = self.item.text()
        test = value.replace(" ", "")
        if test == "":
            self.set_default_style()
        elif validate_value(value):
            if self.id in self.map.appdata.project.scen_values.keys():
                self.set_scen_style()
            else:
                value = self.map.appdata.project.comp_values[self.id]
                (vl, vu) = value
                if math.isclose(vl, vu, abs_tol=self.map.appdata.abs_tol):
                    if self.map.appdata.modes_coloring:
                        if vl == 0:
                            self.set_color(Qt.red)
                        else:
                            self.set_color(Qt.green)
                    else:
                        self.set_comp_style()
                else:
                    if math.isclose(vl, 0.0, abs_tol=self.map.appdata.abs_tol):
                        self.set_color(self.map.appdata.special_color_1)
                    elif math.isclose(vu, 0.0, abs_tol=self.map.appdata.abs_tol):
                        self.set_color(self.map.appdata.special_color_1)
                    elif vl <= 0 and vu >= 0:
                        self.set_color(self.map.appdata.special_color_1)
                    else:
                        self.set_color(self.map.appdata.special_color_2)
        else:
            self.set_error_style()

    def set_color(self, color: QColor):
        palette = self.item.palette()
        role = self.item.backgroundRole()
        palette.setColor(role, color)
        role = self.item.foregroundRole()
        palette.setColor(role, Qt.black)
        self.item.setPalette(palette)

    def set_font_style(self, style: QFont.Style):
        font = self.item.font()
        font.setStyle(style)
        self.item.setFont(font)

    def set_fg_color(self, color: QColor):
        ''' set foreground color of the reaction box'''
        palette = self.item.palette()
        role = self.item.foregroundRole()
        palette.setColor(role, color)
        self.item.setPalette(palette)

    def boundingRect(self):
        return QRectF(-15, -15, self.map.appdata.box_width +
                      15+8, self.map.appdata.box_height+15+8)

    def paint(self, painter: QPainter, _option, _widget: QWidget):
        # set color depending on wether the value belongs to the scenario

        if self.isSelected():
            light_blue = QColor(100, 100, 200)
            pen = QPen(light_blue)
            pen.setWidth(6)
            painter.setPen(pen)
            painter.drawRect(0-6, 0-6, self.map.appdata.box_width +
                             12, self.map.appdata.box_height+12)

        if self.id in self.map.appdata.project.scen_values.keys():
            (vl, vu) = self.map.appdata.project.scen_values[self.id]
            ml = self.map.appdata.project.cobra_py_model.reactions.get_by_id(
                self.id).lower_bound
            mu = self.map.appdata.project.cobra_py_model.reactions.get_by_id(
                self.id).upper_bound

            if vu < ml or vl > mu:
                pen = QPen(self.map.appdata.scen_color_warn)
                painter.setBrush(self.map.appdata.scen_color_warn)
            else:
                pen = QPen(self.map.appdata.scen_color_good)
                painter.setBrush(self.map.appdata.scen_color_good)

            pen.setWidth(6)
            painter.setPen(pen)
            painter.drawRect(0-3, 0-3, self.map.appdata.box_width +
                             6, self.map.appdata.box_height+6)

            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawEllipse(-15, -15, 20, 20)

        else:
            painter.setPen(Qt.darkGray)
            painter.drawEllipse(-15, -15, 20, 20)

        painter.setPen(Qt.darkGray)
        painter.drawLine(-5, 0, -5, -10)
        painter.drawLine(0, -5, -10,  -5)

    def setPos(self, x, y):
        self.proxy.setPos(x, y)
        super().setPos(x, y)

    def on_context_menu(self, point):
        # show context menu
        self.pop_menu.exec_(self.item.mapToGlobal(point))

    def remove(self):
        self.map.remove_box(self.id)
        self.map.drag = False

    def switch_to_reaction_mask(self):
        self.map.switchToReactionMask.emit(self.id)
        self.map.drag = False

    def emit_maximize_action(self):
        self.map.maximizeReaction.emit(self.id)
        self.map.drag = False

    def emit_minimize_action(self):
        self.map.minimizeReaction.emit(self.id)
        self.map.drag = False


def validate_value(value):
    try:
        _x = float(value)
    except ValueError:
        try:
            (vl, vh) = make_tuple(value)
            if not isinstance(vl, int) and not isinstance(vl, float):
                return False
            if not isinstance(vh, int) and not isinstance(vh, float):
                return False
        except (ValueError, SyntaxError, TypeError):
            return False
        else:
            return True
    else:
        return True
