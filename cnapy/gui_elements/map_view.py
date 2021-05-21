"""The PyNetAnalyzer map view"""
import math
from ast import literal_eval as make_tuple
from math import isclose
from typing import Dict, Tuple

from qtpy.QtCore import QMimeData, QRectF, Qt, Signal
from qtpy.QtGui import QPen, QColor, QDrag, QMouseEvent, QPainter
from qtpy.QtSvg import QGraphicsSvgItem
from qtpy.QtWidgets import (QApplication, QAction, QGraphicsItem, QGraphicsScene,
                            QGraphicsSceneDragDropEvent,
                            QGraphicsSceneMouseEvent, QGraphicsView,
                            QLineEdit, QMenu, QWidget)

from cnapy.appdata import AppData

INCREASE_FACTOR = 1.1
DECREASE_FACTOR = 1/INCREASE_FACTOR


class MapView(QGraphicsView):
    """A map of reaction boxes"""

    def __init__(self, appdata: AppData, name: str):
        self.scene = QGraphicsScene()
        QGraphicsView.__init__(self, self.scene)
        palette = self.palette()
        # palette.setColor(QPalette.Base, Qt.white)
        self.setPalette(palette)

        self.appdata = appdata
        self.name = name
        self.setAcceptDrops(True)
        self.drag = False
        self.reaction_boxes: Dict[str, ReactionBox] = {}
        self._zoom = 0
        self.drag = False
        self.drag_start = None

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
            self.appdata.project.maps[self.name]["boxes"][r_id] = (
                point_item.x(), point_item.y())
            self.mapChanged.emit(r_id)
        else:
            self.appdata.project.maps[self.name]["boxes"][r_id] = (
                point_item.x(), point_item.y())
            self.reactionAdded.emit(r_id)

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
                self.appdata.project.maps[self.name]["bg-size"] *= INCREASE_FACTOR
            else:
                self.appdata.project.maps[self.name]["bg-size"] *= DECREASE_FACTOR

            self.mapChanged.emit("dummy")
            self.update()

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
        self.drag = True
        self.drag_start = event.pos()
        super(MapView, self).mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        modifiers = QApplication.queryKeyboardModifiers()
        if modifiers == Qt.ControlModifier:
            if self.drag:
                point = event.pos()
                move_x = self.drag_start.x() - point.x()
                move_y = self.drag_start.y() - point.y()
                self.drag_start = point
                for key, val in self.appdata.project.maps[self.name]["boxes"].items():
                    self.appdata.project.maps[self.name]["boxes"][key] = (
                        val[0]-move_x, val[1]-move_y)
                self.mapChanged.emit("dummy")
                self.update()
        else:
            if self.drag:
                self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
                self.translate(1, 1)
            super(MapView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.drag:
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
            self.translate(1, 1)
        self.drag = False
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

    def update(self):
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
                box.setPos(self.appdata.project.maps[self.name]["boxes"][r_id]
                           [0], self.appdata.project.maps[self.name]["boxes"][r_id][1])
                self.scene.addItem(box)
                self.reaction_boxes[r_id] = box
            except KeyError:
                print("failed to add reaction box for", r_id)

        self.set_values()

        # set scrollbars
        self.horizontalScrollBar().setValue(
            self.appdata.project.maps[self.name]["pos"][0])
        self.verticalScrollBar().setValue(
            self.appdata.project.maps[self.name]["pos"][1])

    def set_values(self):
        for r_id in self.appdata.project.maps[self.name]["boxes"]:
            if r_id in self.appdata.project.scen_values.keys():
                self.reaction_boxes[r_id].set_val_and_color(
                    self.appdata.project.scen_values[r_id])
            elif r_id in self.appdata.project.comp_values.keys():
                self.reaction_boxes[r_id].set_val_and_color(
                    self.appdata.project.comp_values[r_id])

    def remove_box(self, reaction: str):
        del self.appdata.project.maps[self.name]["boxes"][reaction]
        del self.reaction_boxes[reaction]
        self.update()
        self.reactionRemoved.emit(reaction)

    # def emit_doubleClickedReaction(self, reaction: str):
    #     print("emit_doubleClickedReaction")
    #     self.doubleClickedReaction.emit(reaction)

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


class ReactionBox(QGraphicsItem):
    """Handle to the line edits on the map"""

    def __init__(self, parent: MapView, r_id: str, name):
        QGraphicsItem.__init__(self)

        self.map = parent
        self.id = r_id
        self.name = name

        self.item = QLineEdit()
        self.item.setTextMargins(1, -13, 0, -10)  # l t r b
        font = self.item.font()
        point_size = font.pointSize()
        font.setPointSize(point_size+13)
        self.item.setFont(font)
        self.item.setAttribute(Qt.WA_TranslucentBackground)

        self.item.setMaximumWidth(80)
        r = self.map.appdata.project.cobra_py_model.reactions.get_by_id(r_id)
        text = "Id: " + r.id + "\nName: " + r.name \
            + "\nEquation: " + r.build_reaction_string()\
            + "\nLowerbound: " + str(r.lower_bound) \
            + "\nUpper bound: " + str(r.upper_bound) \
            + "\nObjective coefficient: " + str(r.objective_coefficient)

        self.item.setToolTip(text)
        self.proxy = self.map.scene.addWidget(self.item)
        self.proxy.show()

        palette = self.item.palette()
        role = self.item.backgroundRole()
        color = self.map.appdata.default_color
        color.setAlphaF(0.4)
        palette.setColor(role, self.map.appdata.default_color)
        role = self.item.foregroundRole()
        palette.setColor(role, Qt.black)
        self.item.setPalette(palette)

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

    def returnPressed(self):
        if validate_value(self.item.text()):
            self.map.value_changed(self.id, self.item.text())

        # TODO: actually I want to repaint
        # self.map.update()

    def value_changed(self):
        test = self.item.text().replace(" ", "")
        if test == "":
            self.map.value_changed(self.id, test)
            self.set_color(self.map.appdata.default_color)
        elif validate_value(self.item.text()):
            self.map.value_changed(self.id, self.item.text())
            if self.id in self.map.appdata.project.scen_values.keys():
                self.set_color(self.map.appdata.scen_color)
            else:
                self.set_color(self.map.appdata.comp_color)
        else:
            self.set_color(Qt.magenta)

        # TODO: actually I want to repaint
        # self.map.update()

    def set_val_and_color(self, value: Tuple[float, float]):
        self.set_value(value)
        self.recolor()

    def set_value(self, value: Tuple[float, float]):
        (vl, vu) = value
        if isclose(vl, vu, abs_tol=self.map.appdata.abs_tol):
            self.item.setText(str(round(vl, self.map.appdata.rounding)))
        else:
            self.item.setText(
                str((round(vl, self.map.appdata.rounding), round(vu, self.map.appdata.rounding))))
        self.item.setCursorPosition(0)

    def recolor(self):
        value = self.item.text()
        test = value.replace(" ", "")
        if test == "":
            self.set_color(self.map.appdata.default_color)
        elif validate_value(value):
            if self.id in self.map.appdata.project.scen_values.keys():
                value = self.map.appdata.project.scen_values[self.id]
                self.set_color(self.map.appdata.scen_color)
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
                        self.set_color(self.map.appdata.comp_color)
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
            self.set_color(Qt.magenta)

    def set_color(self, color: QColor):
        palette = self.item.palette()
        role = self.item.backgroundRole()
        palette.setColor(role, color)
        role = self.item.foregroundRole()
        palette.setColor(role, Qt.black)
        self.item.setPalette(palette)

    def boundingRect(self):
        return QRectF(-15, -15, 20, 20)

    def paint(self, painter: QPainter, _option, _widget: QWidget):
        # set color depending on wether the value belongs to the scenario
        pen = QPen(self.map.appdata.scen_color_good)
        if self.id in self.map.appdata.project.scen_values.keys():
            painter.setPen(pen)
            pen.setWidth(4)
            painter.setPen(pen)
            painter.drawRect(0, 0, 80, 33)
            painter.setBrush(self.map.appdata.scen_color_good)
        else:
            painter.setPen(Qt.darkGray)

        painter.drawEllipse(-15, -15, 20, 20)
        painter.setPen(Qt.darkGray)
        painter.drawLine(-5, 0, -5, -10)
        painter.drawLine(0, -5, -10,  -5)

    def mousePressEvent(self, _event: QGraphicsSceneMouseEvent):
        pass

    def mouseReleaseEvent(self, _event: QGraphicsSceneMouseEvent):
        pass

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        drag = QDrag(event.widget())
        mime = QMimeData()
        mime.setText(str(self.id))
        drag.setMimeData(mime)
        # self.setCursor(Qt.ClosedHandCursor)
        drag.exec_()
        # self.setCursor(Qt.OpenHandCursor)

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
