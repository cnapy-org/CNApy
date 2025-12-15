"""The PyNetAnalyzer map view"""

import math
from ast import literal_eval as make_tuple
from math import isclose
import importlib.resources as resources

from qtpy.QtCore import QMimeData, QPointF, QRectF, Qt, Signal
from qtpy.QtGui import (
    QPalette,
    QPen,
    QColor,
    QDrag,
    QMouseEvent,
    QKeyEvent,
    QPainter,
    QFont,
)
from qtpy.QtSvg import QGraphicsSvgItem
from qtpy.QtWidgets import (
    QApplication,
    QAction,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsSceneDragDropEvent,
    QTreeWidget,
    QGraphicsSceneMouseEvent,
    QGraphicsView,
    QLineEdit,
    QMenu,
    QWidget,
    QGraphicsProxyWidget,
)

from cnapy.appdata import AppData
from cnapy.gui_elements.box_position_dialog import BoxPositionDialog

INCREASE_FACTOR = 1.1
DECREASE_FACTOR = 1 / INCREASE_FACTOR


class ArrowItem(QGraphicsLineItem):
    def __init__(self, start: QPointF, end: QPointF, map_view: QGraphicsView, arrow_list_index: int):
        super().__init__(start.x(), start.y(), end.x(), end.y())
        self.map_view = map_view
        self.setPen(QPen(QColor("black"), 3))
        self.setFlags(QGraphicsItem.ItemIsSelectable | QGraphicsItem.ItemIsMovable)
        self.setAcceptHoverEvents(True)
        self._dragging = False
        self._last_mouse_scene_pos = None
        self.arrow_list_index = arrow_list_index

    def hoverEnterEvent(self, event):
        if self.map_view.arrow_drawing_mode:
            self.map_view.viewport().setCursor(Qt.PointingHandCursor)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.map_view.arrow_drawing_mode:
            self.map_view.viewport().setCursor(Qt.CrossCursor)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if self.map_view.arrow_drawing_mode:
            if event.button() == Qt.RightButton:
                # Remove arrow
                self.map_view.scene.removeItem(self)
                del self.map_view.appdata.project.maps[self.map_view.name]["arrows"][
                    self.arrow_list_index
                ]
                del self.map_view.arrows[self.arrow_list_index]
                for i, arrow in enumerate(self.map_view.arrows):
                    arrow.arrow_list_index = i
                event.accept()
                return
            elif event.button() == Qt.MiddleButton:
                # Start moving arrow
                self._dragging = True
                self._last_mouse_scene_pos = event.scenePos()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.map_view.arrow_drawing_mode and self._dragging:
            current_scene_pos = event.scenePos()
            dx = current_scene_pos.x() - self._last_mouse_scene_pos.x()
            dy = current_scene_pos.y() - self._last_mouse_scene_pos.y()
            self._last_mouse_scene_pos = current_scene_pos

            # Move both endpoints
            line = self.line()
            new_start = QPointF(line.x1() + dx, line.y1() + dy)
            new_end = QPointF(line.x2() + dx, line.y2() + dy)
            self.setLine(new_start.x(), new_start.y(), new_end.x(), new_end.y())
            self.map_view.appdata.project.maps[self.map_view.name]["arrows"][
                self.arrow_list_index
            ] = ((new_start.x(), new_start.y()), (new_end.x(), new_end.y()))

            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if (
            self.map_view.arrow_drawing_mode
            and self._dragging
            and event.button() == Qt.MiddleButton
        ):
            self._dragging = False
            new_coords = (
                (self.line().x1(), self.line().y1()),
                (self.line().x2(), self.line().y2()),
            )
            arrows_list = self.map_view.appdata.project.maps[self.map_view.name][
                "arrows"
            ]

            # Update stored coords
            for i, coords in enumerate(arrows_list):
                if coords == (
                    (self.line().x1(), self.line().y1()),
                    (self.line().x2(), self.line().y2()),
                ):
                    arrows_list[i] = new_coords
                    break

            event.accept()
            return
        super().mouseReleaseEvent(event)
    
    def paint(self, painter: QPainter, option, widget=None):
        # Draw the main line
        painter.setPen(self.pen())
        line = self.line()
        painter.drawLine(line)

        # Draw arrowhead
        arrow_size = 12.0  # length of arrowhead edges
        angle = math.atan2(line.dy(), line.dx())

        # Two points making the triangle arrowhead
        p1 = QPointF(
            line.x2() - arrow_size * math.cos(angle - math.pi / 6),
            line.y2() - arrow_size * math.sin(angle - math.pi / 6)
        )
        p2 = QPointF(
            line.x2() - arrow_size * math.cos(angle + math.pi / 6),
            line.y2() - arrow_size * math.sin(angle + math.pi / 6)
        )

        # Draw filled triangle
        arrow_head = [QPointF(line.x2(), line.y2()), p1, p2]
        painter.setBrush(self.pen().color())
        painter.drawPolygon(*arrow_head)


class MapView(QGraphicsView):
    """A map of reaction boxes"""

    def __init__(self, appdata: AppData, central_widget, name: str):
        self.scene: QGraphicsScene = QGraphicsScene()
        QGraphicsView.__init__(self, self.scene)
        self.background: QGraphicsSvgItem = None
        palette = self.palette()
        if appdata.is_in_dark_mode:
            palette.setColor(QPalette.Base, QColor(90, 90, 90))  # Map etc. backgrounds
        else:
            palette.setColor(
                QPalette.Base, QColor(250, 250, 250)
            )  # Map etc. backgrounds
        self.setPalette(palette)
        self.setInteractive(True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.appdata = appdata
        self.central_widget = central_widget
        self.name: str = name
        self.setAcceptDrops(True)
        self.drag_map = False
        self.reaction_boxes: dict[str, ReactionBox] = {}
        self._zoom = 0
        self.previous_point = None
        self.select = False
        self.select_start = None

        self.arrow_drawing_mode = False
        self.arrow_start_point: QPointF = None
        self.temp_arrow_line: QGraphicsLineItem = None
        self.arrows: list[ArrowItem] = []

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
            x,
            self.verticalScrollBar().value(),
        )

    def on_vbar_change(self, y):
        self.appdata.project.maps[self.name]["pos"] = (
            self.horizontalScrollBar().value(),
            y,
        )

    def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
        self.previous_point = self.mapToScene(event.pos())
        event.acceptProposedAction()

    def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent):
        event.setAccepted(True)
        point_item = self.mapToScene(event.pos())
        r_id = event.mimeData().text()

        if r_id in self.appdata.project.maps[self.name]["boxes"].keys():
            if isinstance(
                event.source(), QTreeWidget
            ):  # existing/continued drag from reaction list
                self.appdata.project.maps[self.name]["boxes"][r_id] = (
                    point_item.x(),
                    point_item.y(),
                )
                self.mapChanged.emit(r_id)
            else:
                move_x = point_item.x() - self.previous_point.x()
                move_y = point_item.y() - self.previous_point.y()
                self.previous_point = point_item
                selected = self.scene.selectedItems()
                for item in selected:
                    pos = self.appdata.project.maps[self.name]["boxes"][item.id]

                    self.appdata.project.maps[self.name]["boxes"][item.id] = (
                        pos[0] + move_x,
                        pos[1] + move_y,
                    )
                    self.mapChanged.emit(item.id)

        else:  # drag reaction from list that has not yet a box on this map
            self.appdata.project.maps[self.name]["boxes"][r_id] = (
                point_item.x(),
                point_item.y(),
            )
            self.reactionAdded.emit(r_id)
            self.rebuild_scene()  # TODO don't rebuild the whole scene only add one item

        self.update()

    def dropEvent(self, event: QGraphicsSceneDragDropEvent):
        self.drag_map = False
        identifier = event.mimeData().text()
        self.mapChanged.emit(identifier)
        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        self.viewport().setCursor(Qt.OpenHandCursor)
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

    def keyPressEvent(self, event: QKeyEvent):
        # Handle Arrow Drawing Mode Toggle (ALT+A)
        if event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_A:
            self.enter_arrow_drawing_mode()
            event.accept()
            return

        if not self.drag_map and event.key() in (Qt.Key_Control, Qt.Key_Shift):
            self.viewport().setCursor(Qt.ArrowCursor)
            self.select = True
        else:
            super().keyPressEvent(event)

    def enterArrowDrawingMode(self) -> bool:
        self.arrow_drawing_mode = not self.arrow_drawing_mode
        if self.arrow_drawing_mode:
            self.setDragMode(QGraphicsView.NoDrag)
            self.viewport().setCursor(Qt.CrossCursor)
            print("Entered Arrow Drawing Mode")
            return True
        else:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.viewport().setCursor(Qt.OpenHandCursor)
            print("Exited Arrow Drawing Mode")
            return False

    def keyReleaseEvent(self, event: QKeyEvent):
        if (
            self.select
            and QApplication.mouseButtons() != Qt.LeftButton
            and event.key() in (Qt.Key_Control, Qt.Key_Shift)
        ):
            self.viewport().setCursor(Qt.OpenHandCursor)
            self.select = False
        else:
            super().keyReleaseEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if self.hasFocus():
            # Handle Arrow Drawing Mode Press
            if self.arrow_drawing_mode and event.button() == Qt.LeftButton:
                self.arrow_start_point = self.mapToScene(event.pos())

                # Start drawing a temporary line
                pen = QPen(Qt.blue)
                pen.setWidth(2)
                # Create a temporary line item (0 length for now)
                self.temp_arrow_line = QGraphicsLineItem(
                    self.arrow_start_point.x(),
                    self.arrow_start_point.y(),
                    self.arrow_start_point.x(),
                    self.arrow_start_point.y(),
                )
                self.temp_arrow_line.setPen(pen)
                self.scene.addItem(self.temp_arrow_line)

                event.accept()
                return  # Don't call super() to prevent default drag behavior

            if self.select:  # select multiple boxes
                self.setDragMode(
                    QGraphicsView.RubberBandDrag
                )  # switches to ArrowCursor
                self.select_start = self.mapToScene(event.pos())
            else:  # drag entire map
                self.viewport().setCursor(Qt.ClosedHandCursor)
                self.setDragMode(QGraphicsView.ScrollHandDrag)
                self.drag_map = True
            super(MapView, self).mousePressEvent(
                event
            )  # generates events for the graphics scene items

    def mouseMoveEvent(self, event: QMouseEvent):
        # Handle Arrow Drawing Mode Move
        if self.arrow_drawing_mode and self.arrow_start_point and self.temp_arrow_line:
            current_point = self.mapToScene(event.pos())

            # Update the temporary line end point
            self.temp_arrow_line.setLine(
                self.arrow_start_point.x(),
                self.arrow_start_point.y(),
                current_point.x(),
                current_point.y(),
            )

            event.accept()
            return

        super(MapView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        # Handle Arrow Drawing Mode Release
        if (
            self.arrow_drawing_mode
            and self.arrow_start_point
            and event.button() == Qt.LeftButton
        ):
            end_point = self.mapToScene(event.pos())

            # Remove temporary line
            if self.temp_arrow_line:
                self.scene.removeItem(self.temp_arrow_line)
                self.temp_arrow_line = None

            # Check if arrow is long enough to draw a final one
            if (
                end_point - self.arrow_start_point
            ).manhattanLength() > 5:  # minimum 5 pixels
                self.draw_final_arrow(self.arrow_start_point, end_point)
                self.appdata.project.maps[self.name]["arrows"].append(
                    (
                        (self.arrow_start_point.x(), self.arrow_start_point.y()),
                        (end_point.x(), end_point.y()),
                    )
                )

            self.arrow_start_point = None
            event.accept()
            return  # Don't call super() to prevent default release behavior

        if self.drag_map:
            self.viewport().setCursor(Qt.OpenHandCursor)
            self.drag_map = False
        if self.select:
            modifiers = QApplication.keyboardModifiers()
            if modifiers != Qt.ControlModifier and modifiers != Qt.ShiftModifier:
                self.viewport().setCursor(Qt.OpenHandCursor)
                self.select = False
            point = self.mapToScene(event.pos())

            width = point.x() - self.select_start.x()
            height = point.y() - self.select_start.y()
            selected = self.scene.items(
                QRectF(self.select_start.x(), self.select_start.y(), width, height)
            )

            for item in selected:
                if isinstance(item, QGraphicsProxyWidget):
                    item.widget().parent.setSelected(True)

        painter = QPainter()
        self.render(painter)

        super(MapView, self).mouseReleaseEvent(event)
        event.accept()

    def draw_final_arrow(self, start: QPointF, end: QPointF):
        arrow = ArrowItem(start, end, self, len(self.arrows))
        self.arrows.append(arrow)
        self.scene.addItem(arrow)
        return arrow

    def focusOutEvent(self, event):
        super(MapView, self).focusOutEvent(event)
        # Only reset cursor if not in arrow drawing mode
        if not self.arrow_drawing_mode:
            self.viewport().setCursor(Qt.OpenHandCursor)
        self.select = False

    def enterEvent(self, event) -> None:
        super().enterEvent(event)
        if not isinstance(QApplication.focusWidget(), QLineEdit):
            # only take focus if no QlineEdit is active to prevent
            # editingFinished signals there
            if len(self.scene.selectedItems()) == 1:
                self.scene.selectedItems()[0].item.setFocus()
            else:
                self.scene.setFocus()  # to capture Shift/Ctrl keys

    def leaveEvent(self, event) -> None:
        super().leaveEvent(event)
        self.scene.clearFocus()  # finishes editing of potentially active ReactionBox

    def update_selected(self, found_ids):
        for r_id, box in self.reaction_boxes.items():
            box.item.setHidden(True)
            for found_id in found_ids:
                if found_id.lower() in r_id.lower():
                    box.item.setHidden(False)
                elif found_id.lower() in box.name.lower():
                    box.item.setHidden(False)

    def focus_reaction(self, reaction: str):
        x = self.appdata.project.maps[self.name]["boxes"][reaction][0]
        y = self.appdata.project.maps[self.name]["boxes"][reaction][1]
        self.centerOn(x, y)
        self.zoom_in_reaction()

    def zoom_in_reaction(self):
        bg_size = self.appdata.project.maps[self.name]["bg-size"]
        x = (INCREASE_FACTOR**self._zoom) / bg_size
        while x < 1:
            x = (INCREASE_FACTOR**self._zoom) / bg_size
            self._zoom += 1
            self.appdata.project.maps[self.name]["zoom"] = self._zoom
            self.scale(INCREASE_FACTOR, INCREASE_FACTOR)

    def highlight_reaction(self, string):
        treffer = self.reaction_boxes[string]
        treffer.item.setHidden(False)
        treffer.item.setFocus()

    def select_single_reaction(self, reac_id: str):
        box: ReactionBox = self.reaction_boxes.get(reac_id, None)
        if box is not None:
            self.scene.clearSelection()
            self.scene.clearFocus()
            box.setSelected(True)

    def set_background(self):
        if self.background is not None:
            self.scene.removeItem(self.background)
        self.background = QGraphicsSvgItem(
            self.appdata.project.maps[self.name]["background"]
        )
        self.background.setFlags(QGraphicsItem.ItemClipsToShape)
        self.background.setScale(self.appdata.project.maps[self.name]["bg-size"])
        self.scene.addItem(self.background)

    def rebuild_scene(self):
        self.scene.clear()
        self.background = None

        if (
            len(self.appdata.project.maps[self.name]["boxes"]) > 0
        ) and self.appdata.project.maps[self.name]["background"].replace(
            "\\", "/"
        ).endswith("/data/default-bg.svg"):
            with resources.as_file(
                resources.files("cnapy") / "data" / "blank.svg"
            ) as path:
                self.appdata.project.maps[self.name]["background"] = str(path)

        self.set_background()

        for r_id in self.appdata.project.maps[self.name]["boxes"]:
            try:
                name = self.appdata.project.cobra_py_model.reactions.get_by_id(
                    r_id
                ).name
                box = ReactionBox(self, r_id, name)

                self.scene.addItem(box)
                box.add_line_widget()
                self.reaction_boxes[r_id] = box
            except KeyError:
                print("failed to add reaction box for", r_id)

        map_data = self.appdata.project.maps[self.name]
        if "arrows" in map_data:
            self.arrows = []
            for start_coords, end_coords in map_data["arrows"]:
                start_point = QPointF(*start_coords)
                end_point = QPointF(*end_coords)
                self.draw_final_arrow(start_point, end_point)

    def delete_box(self, reaction_id: str) -> bool:
        box = self.reaction_boxes.get(reaction_id, None)
        if box is not None:
            lineedit = box.proxy
            self.scene.removeItem(lineedit)
            self.scene.removeItem(box)
            return True
        else:
            # print(f"Reaction {reaction_id} does not occur on map {self.name}")
            return False

    def update_reaction(self, old_reaction_id: str, new_reaction_id: str):
        if not self.delete_box(old_reaction_id):  # reaction is not on map
            return
        try:
            name = self.appdata.project.cobra_py_model.reactions.get_by_id(
                new_reaction_id
            ).name
            box = ReactionBox(self, new_reaction_id, name)

            self.scene.addItem(box)
            box.add_line_widget()
            self.reaction_boxes[new_reaction_id] = box

            box.setScale(self.appdata.project.maps[self.name]["box-size"])
            box.proxy.setScale(self.appdata.project.maps[self.name]["box-size"])
            box.setPos(
                self.appdata.project.maps[self.name]["boxes"][box.id][0],
                self.appdata.project.maps[self.name]["boxes"][box.id][1],
            )

        except KeyError:
            print(
                f"Failed to add reaction box for {new_reaction_id} on map {self.name}"
            )

    def update(self):
        for item in self.scene.items():
            if isinstance(item, QGraphicsSvgItem):
                item.setScale(self.appdata.project.maps[self.name]["bg-size"])
            elif isinstance(item, ReactionBox):
                item.setScale(self.appdata.project.maps[self.name]["box-size"])
                item.proxy.setScale(self.appdata.project.maps[self.name]["box-size"])
                try:
                    item.setPos(
                        self.appdata.project.maps[self.name]["boxes"][item.id][0],
                        self.appdata.project.maps[self.name]["boxes"][item.id][1],
                    )
                except KeyError:
                    print(f"{item.id} not found as box")
            else:
                pass

        self.set_values()
        self.recolor_all()

        # set scrollbars
        self.horizontalScrollBar().setValue(
            self.appdata.project.maps[self.name]["pos"][0]
        )
        self.verticalScrollBar().setValue(
            self.appdata.project.maps[self.name]["pos"][1]
        )

    def recolor_all(self):
        for r_id in self.appdata.project.maps[self.name]["boxes"]:
            self.reaction_boxes[r_id].recolor()

    def set_values(self):
        for r_id in self.appdata.project.maps[self.name]["boxes"]:
            if r_id in self.appdata.project.scen_values.keys():
                self.reaction_boxes[r_id].set_value(
                    self.appdata.project.scen_values[r_id]
                )
            elif r_id in self.appdata.project.comp_values.keys():
                self.reaction_boxes[r_id].set_value(
                    self.appdata.project.comp_values[r_id]
                )
            else:
                self.reaction_boxes[r_id].item.setText("")

    def remove_box(self, reaction: str):
        self.delete_box(reaction)
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
    setScenValue = Signal(str)
    reactionRemoved = Signal(str)
    reactionValueChanged = Signal(str, str)
    reactionAdded = Signal(str)
    mapChanged = Signal(str)
    broadcastReactionID = Signal(str)


class CLineEdit(QLineEdit):
    """A special line edit implementation for the use in ReactionBox"""

    def __init__(self, parent):
        self.parent: ReactionBox = parent
        self.accept_next_change_into_history = True
        super().__init__()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.parent.setSelected(False)
        if self.isModified() and self.parent.map.appdata.auto_fba:
            self.parent.map.central_widget.parent.fba()
        self.parent.update()

    def focusInEvent(self, event):
        # is called before mousePressEvent
        super().focusInEvent(event)
        self.accept_next_change_into_history = True
        self.setModified(False)
        self.parent.setSelected(
            True
        )  # in case focus is regained via enterEvent of the map

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self.parent.switch_to_reaction_mask()

    def mousePressEvent(self, event: QMouseEvent):
        # is called after focusInEvent
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            if not self.parent.map.select:
                for bx in self.parent.map.reaction_boxes.values():
                    bx.setSelected(False)
            self.parent.setSelected(True)
            self.parent.broadcast_reaction_id()
        event.accept()


class ReactionBox(QGraphicsItem):
    """Handle to the line edits on the map"""

    def __init__(self, parent: MapView, r_id: str, name):
        QGraphicsItem.__init__(self)

        self.map = parent
        self.id = r_id
        self.name = name

        self.setFlag(QGraphicsItem.ItemIsSelectable)
        self.setFlag(QGraphicsItem.ItemIsMovable)
        self.setAcceptHoverEvents(True)
        self.item = CLineEdit(self)
        self.item.setTextMargins(1, -13, 0, -10)  # l t r b
        font = self.item.font()
        point_size = font.pointSize()
        font.setPointSizeF(point_size + 13.0)
        self.item.setFont(font)
        self.item.setAttribute(Qt.WA_TranslucentBackground)

        self.item.setFixedWidth(self.map.appdata.box_width)
        self.item.setMaximumHeight(self.map.appdata.box_height)
        self.item.setMinimumHeight(self.map.appdata.box_height)
        r = self.map.appdata.project.cobra_py_model.reactions.get_by_id(r_id)
        text = (
            "Id: "
            + r.id
            + "\nName: "
            + r.name
            + "\nEquation: "
            + r.build_reaction_string()
            + "\nLowerbound: "
            + str(r.lower_bound)
            + "\nUpper bound: "
            + str(r.upper_bound)
            + "\nObjective coefficient: "
            + str(r.objective_coefficient)
        )

        self.item.setToolTip(text)

        self.proxy = (
            None  # proxy is set in add_line_widget after the item has been added
        )

        self.set_default_style()

        self.setCursor(Qt.OpenHandCursor)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.item.textEdited.connect(self.value_changed)
        self.item.returnPressed.connect(self.returnPressed)

        self.item.setContextMenuPolicy(Qt.CustomContextMenu)
        self.item.customContextMenuRequested.connect(self.on_context_menu)

        # create context menu
        self.pop_menu = QMenu(parent)
        maximize_action = QAction("maximize flux for this reaction", parent)
        self.pop_menu.addAction(maximize_action)
        maximize_action.triggered.connect(self.emit_maximize_action)
        minimize_action = QAction("minimize flux for this reaction", parent)
        self.pop_menu.addAction(minimize_action)
        set_scen_value_action = QAction("add computed value to scenario", parent)
        set_scen_value_action.triggered.connect(self.emit_set_scen_value_action)
        self.pop_menu.addAction(set_scen_value_action)
        minimize_action.triggered.connect(self.emit_minimize_action)
        switch_action = QAction("switch to reaction mask", parent)
        self.pop_menu.addAction(switch_action)
        switch_action.triggered.connect(self.switch_to_reaction_mask)
        position_action = QAction("set box position...", parent)
        self.pop_menu.addAction(position_action)
        position_action.triggered.connect(self.position)
        remove_action = QAction("remove from map", parent)
        self.pop_menu.addAction(remove_action)
        remove_action.triggered.connect(self.remove)

        self.pop_menu.addSeparator()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        super().mousePressEvent(event)
        event.accept()
        if event.button() == Qt.MouseButton.LeftButton:
            if self.map.select:
                self.setSelected(not self.isSelected())
            else:
                self.setSelected(True)
        else:
            self.setCursor(Qt.ClosedHandCursor)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        event.accept()
        self.ungrabMouse()
        if not self.map.select:
            self.setCursor(Qt.OpenHandCursor)
            super().mouseReleaseEvent(
                event
            )  # here deselection of the other boxes occurs

    def hoverEnterEvent(self, event):
        if self.map.select:
            self.setCursor(Qt.ArrowCursor)
        else:
            self.setCursor(Qt.OpenHandCursor)
        super().hoverEnterEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        event.accept()
        drag = QDrag(event.widget())
        mime = QMimeData()
        mime.setText(str(self.id))
        drag.setMimeData(mime)
        drag.exec_()

    def add_line_widget(self):
        self.proxy = self.map.scene.addWidget(self.item)
        self.proxy.show()

    def returnPressed(self):
        # self.item.clearFocus() # does not yet yield focus...
        self.proxy.clearFocus()  # ...but this does
        self.map.setFocus()
        self.item.accept_next_change_into_history = (
            True  # reset so that next change will be recorded
        )

    def handle_editing_finished(self):
        if self.item.isModified() and self.map.appdata.auto_fba:
            self.map.central_widget.parent.fba()

    # @Slot() # using the decorator gives a connection error?
    def value_changed(self):
        test = self.item.text().replace(" ", "")
        if test == "":
            if not self.item.accept_next_change_into_history:
                if len(self.map.appdata.scenario_past) > 0:
                    self.map.appdata.scenario_past.pop()  # replace previous change
            self.item.accept_next_change_into_history = False
            self.map.value_changed(self.id, test)
            self.set_default_style()
        elif validate_value(self.item.text()):
            if not self.item.accept_next_change_into_history:
                if len(self.map.appdata.scenario_past) > 0:
                    self.map.appdata.scenario_past.pop()  # replace previous change
            self.item.accept_next_change_into_history = False
            self.map.value_changed(self.id, self.item.text())
            if self.id in self.map.appdata.project.scen_values.keys():
                self.set_scen_style()
            else:
                self.set_comp_style()
        else:
            self.set_error_style()

    def set_default_style(self):
        """set the reaction box to error style"""
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
        """set the reaction box to error style"""
        self.set_color(Qt.white)
        self.set_fg_color(self.map.appdata.scen_color_bad)
        self.set_font_style(QFont.StyleOblique)

    def set_comp_style(self):
        self.set_color(self.map.appdata.comp_color)
        self.set_font_style(QFont.StyleNormal)

    def set_scen_style(self):
        self.set_color(self.map.appdata.scen_color)
        self.set_font_style(QFont.StyleNormal)

    def set_value(self, value: tuple[float, float]):
        """Sets the text of and reaction box according to the given value"""
        (vl, vu) = value
        if isclose(vl, vu, abs_tol=self.map.appdata.abs_tol):
            self.item.setText(
                str(round(float(vl), self.map.appdata.rounding)).rstrip("0").rstrip(".")
            )
        else:
            self.item.setText(
                str(round(float(vl), self.map.appdata.rounding)).rstrip("0").rstrip(".")
                + ", "
                + str(round(float(vu), self.map.appdata.rounding))
                .rstrip("0")
                .rstrip(".")
            )
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
        """set foreground color of the reaction box"""
        palette = self.item.palette()
        role = self.item.foregroundRole()
        palette.setColor(role, color)
        self.item.setPalette(palette)

    def boundingRect(self):
        return QRectF(
            -15,
            -15,
            self.map.appdata.box_width + 15 + 8,
            self.map.appdata.box_height + 15 + 8,
        )

    def paint(self, painter: QPainter, _option, _widget: QWidget):
        # set color depending on wether the value belongs to the scenario
        if self.isSelected():
            light_blue = QColor(100, 100, 200)
            pen = QPen(light_blue)
            pen.setWidth(6)
            painter.setPen(pen)
            painter.drawRect(
                0 - 6,
                0 - 6,
                self.map.appdata.box_width + 12,
                self.map.appdata.box_height + 12,
            )

        if self.id in self.map.appdata.project.scen_values.keys():
            (vl, vu) = self.map.appdata.project.scen_values[self.id]
            ml = self.map.appdata.project.cobra_py_model.reactions.get_by_id(
                self.id
            ).lower_bound
            mu = self.map.appdata.project.cobra_py_model.reactions.get_by_id(
                self.id
            ).upper_bound

            if vu < ml or vl > mu:
                pen = QPen(self.map.appdata.scen_color_warn)
                painter.setBrush(self.map.appdata.scen_color_warn)
            else:
                pen = QPen(self.map.appdata.scen_color_good)
                painter.setBrush(self.map.appdata.scen_color_good)

            pen.setWidth(6)
            painter.setPen(pen)
            painter.drawRect(
                0 - 3,
                0 - 3,
                self.map.appdata.box_width + 6,
                self.map.appdata.box_height + 6,
            )

            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawEllipse(-15, -15, 20, 20)

        else:
            painter.setPen(Qt.darkGray)
            painter.drawEllipse(-15, -15, 20, 20)

        painter.setPen(Qt.darkGray)
        painter.drawLine(-5, 0, -5, -10)
        painter.drawLine(0, -5, -10, -5)

        self.item.setFixedWidth(self.map.appdata.box_width)

    def setPos(self, x, y):
        self.proxy.setPos(x, y)
        super().setPos(x, y)

    def on_context_menu(self, point):
        # show context menu
        self.pop_menu.exec_(self.item.mapToGlobal(point))

    def position(self):
        position_dialog = BoxPositionDialog(self, self.map)
        position_dialog.exec()

    def remove(self):
        self.map.remove_box(self.id)
        self.map.drag = False

    def switch_to_reaction_mask(self):
        self.map.switchToReactionMask.emit(self.id)
        self.map.drag = False

    def emit_maximize_action(self):
        self.map.maximizeReaction.emit(self.id)
        self.map.drag = False

    def emit_set_scen_value_action(self):
        self.map.setScenValue.emit(self.id)
        self.map.drag = False

    def emit_minimize_action(self):
        self.map.minimizeReaction.emit(self.id)
        self.map.drag = False

    def broadcast_reaction_id(self):
        self.map.central_widget.broadcastReactionID.emit(self.id)
        self.map.drag = False


def validate_value(value):
    try:
        _x = float(value)
    except ValueError:
        try:
            (vl, vh) = make_tuple(value)
            if (
                isinstance(vl, (int, float))
                and isinstance(vh, (int, float))
                and vl <= vh
            ):
                return True
            else:
                return False
        except (ValueError, SyntaxError, TypeError):
            return False
    else:
        return True
