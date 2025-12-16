"""The CellNetAnalyzer map view"""

import math
from ast import literal_eval as make_tuple
from math import isclose
import importlib.resources as resources
from typing import Literal

from qtpy.QtCore import QMimeData, QPointF, QRectF, Qt, Signal
from qtpy.QtGui import (
    QCursor,
    QPalette,
    QPen,
    QColor,
    QDrag,
    QMouseEvent,
    QKeyEvent,
    QPainter,
    QFont,
    QPainterPath,
)
from qtpy.QtSvg import QGraphicsSvgItem
from qtpy.QtWidgets import (
    QApplication,
    QAction,
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsSceneDragDropEvent,
    QGraphicsTextItem,
    QInputDialog,
    QLabel,
    QRadioButton,
    QSpinBox,
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


class LabelItem(QGraphicsTextItem):
    """
    Encapsulates all label logic:
    - Dragging
    - ALT+click deletion
    - Persistence in appdata maps["labels"]
    """

    def __init__(
        self,
        text: str,
        pos: QPointF,
        map_view: "MapView",
        label_index: int,
        font_size: int = 12,
        color: QColor | str = QColor("black"),
    ):
        super().__init__(text)

        self.map_view = map_view
        self.label_index = label_index

        self.font_size = int(font_size)
        self.color = QColor(color)

        font = QFont("Arial", self.font_size)
        self.setFont(font)
        self.setDefaultTextColor(self.color)
        self.setPos(pos)

        self.setAcceptHoverEvents(True)
        self.setAcceptedMouseButtons(Qt.LeftButton)

        self._dragging = False
        self._drag_offset = QPointF()

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        if not self.map_view.arrow_drawing_mode:
            super().mousePressEvent(event)
            return

        if event.button() == Qt.LeftButton and (event.modifiers() & Qt.AltModifier):
            self.delete()
            event.accept()
            return

        if event.button() == Qt.LeftButton:
            self._dragging = True
            self._drag_offset = event.scenePos() - self.pos()
            self.map_view.viewport().setCursor(Qt.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging:
            new_pos = event.scenePos() - self._drag_offset
            self.setPos(new_pos)
            self._store_geometry()
            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        if self._dragging:
            self._dragging = False
            self.map_view.viewport().setCursor(Qt.CrossCursor)
            self._store_geometry()
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def _store_geometry(self):
        labels = self.map_view.appdata.project.maps[self.map_view.name]["labels"]
        labels[self.label_index] = (
            self.toPlainText(),
            self.x(),
            self.y(),
            self.font_size,
            self.color.name(),
        )
    
    def delete(self):
        labels = self.map_view.appdata.project.maps[self.map_view.name]["labels"]
        idx = self.label_index

        self.map_view.scene.removeItem(self)
        del labels[idx]

        # Reindex remaining LabelItems
        for item in self.map_view.scene.items():
            if isinstance(item, LabelItem) and item.label_index > idx:
                item.label_index -= 1
    
    def mouseDoubleClickEvent(self, event):
            if not self.map_view.arrow_drawing_mode:
                return super().mouseDoubleClickEvent(event)

            dlg = LabelEditDialog(self)
            if dlg.exec():
                dlg.apply()

            event.accept()


class LabelEditDialog(QDialog):
    def __init__(self, label: "LabelItem"):
        super().__init__(label.map_view)
        self.label = label
        self.setWindowTitle("Edit Label")

        self.text_edit = QLineEdit(label.toPlainText())
        self.font_size_edit = QSpinBox()
        self.font_size_edit.setRange(1, 100)
        self.font_size_edit.setValue(label.font_size)

        self.color_edit = QLineEdit(label.color.name())

        layout = QFormLayout(self)
        layout.addRow("Text", self.text_edit)
        layout.addRow("Font size", self.font_size_edit)
        layout.addRow("Color (hex)", self.color_edit)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def apply(self):
        self.label.setPlainText(self.text_edit.text())

        self.label.font_size = self.font_size_edit.value()
        font = self.label.font()
        font.setPointSize(self.label.font_size)
        self.label.setFont(font)

        self.label.color = QColor(self.color_edit.text())
        self.label.setDefaultTextColor(self.label.color)

        self.label._store_geometry()


class ArrowItem(QGraphicsPathItem):
    """Quadratic Bézier arrow with a single scalar bending parameter.

    Stored data format in appdata:
        ((x_start, y_start), (x_end, y_end), bending)

    - bending = 0: straight line.
    - bending > 0 or < 0: curve to one side or the other.
    """

    def __init__(
        self,
        start: QPointF,
        end: QPointF,
        map_view: QGraphicsView,
        arrow_list_index: int,
        bending: float = 0.0,
        width: float = 3.0,
        color: QColor | str = QColor("black"),
        head_mode: Literal["end"] | Literal["both"] | Literal["none"]="end",
    ):
        super().__init__()

        self.map_view = map_view
        self.arrow_list_index = arrow_list_index

        self.start_point = QPointF(start)
        self.end_point = QPointF(end)
        self.bending = float(bending)

        self.width = float(width)
        self.color = QColor(color)
        self.head_mode = head_mode

        self.setPen(QPen(self.color, self.width))
        self.setAcceptHoverEvents(True)

        # drag state
        self._dragging = False
        self._last_mouse_scene_pos = None
        self.dragpoint_draw_radius = 8.0
        self.dragpoint_click_radius = 32.0
        self.dragging_start = False
        self.dragging_end = False
        self.dragging_middle = False

        self.update_path()

    # Geometry helpers (especially for bending)
    def _unit_perp_from_start_to_end(self) -> QPointF:
        """Unit vector perpendicular to the segment start->end."""
        dx = self.end_point.x() - self.start_point.x()
        dy = self.end_point.y() - self.start_point.y()
        length = math.hypot(dx, dy)
        if length == 0:
            return QPointF(0, 0)
        return QPointF(-dy / length, dx / length)

    def _control_point_from_bending(self) -> QPointF:
        """
        Compute quadratic Bézier control point from start, end, and bending.
        C = midpoint + bending * unit_perp.
        """
        mid = (self.start_point + self.end_point) / 2.0
        perp = self._unit_perp_from_start_to_end()
        return QPointF(
            mid.x() + self.bending * perp.x(), mid.y() + self.bending * perp.y()
        )

    def _bending_from_control_point(self, control: QPointF) -> float:
        """
        Given a control point, compute bending as the signed distance from
        the segment midpoint along the perpendicular direction.
        """
        mid = (self.start_point + self.end_point) / 2.0
        v = control - mid
        perp = self._unit_perp_from_start_to_end()
        return v.x() * perp.x() + v.y() * perp.y()

    def update_path(self):
        """Rebuild QPainterPath from start/end and current bending."""
        control = self._control_point_from_bending()
        path = QPainterPath(self.start_point)
        path.quadTo(control, self.end_point)
        self.setPath(path)

    @staticmethod
    def _dist2(p1: QPointF, p2: QPointF) -> float:
        dx = p1.x() - p2.x()
        dy = p1.y() - p2.y()
        return dx * dx + dy * dy

    def _bezier_midpoint(self) -> QPointF:
        """Midpoint on the Bézier curve at t=0.5."""
        control = self._control_point_from_bending()
        return QPointF(
            0.25 * self.start_point.x() + 0.5 * control.x() + 0.25 * self.end_point.x(),
            0.25 * self.start_point.y() + 0.5 * control.y() + 0.25 * self.end_point.y(),
        )

    def _store_geometry(self):
        self.map_view.appdata.project.maps[self.map_view.name]["arrows"][
            self.arrow_list_index
        ] = (
            (self.start_point.x(), self.start_point.y()),
            (self.end_point.x(), self.end_point.y()),
            float(self.bending),
            float(self.width),
            self.color.name(),
            self.head_mode,
        )
    
    def _handle_points(self):
        return self.start_point, self.end_point, self._bezier_midpoint()

    # Mouse events
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
            scene_pos = event.scenePos()

            # Left button and ALT: delete
            if event.button() == Qt.LeftButton and (event.modifiers() & Qt.AltModifier):
                self.map_view.scene.removeItem(self)
                del self.map_view.appdata.project.maps[self.map_view.name]["arrows"][
                    self.arrow_list_index
                ]
                del self.map_view.arrows[self.arrow_list_index]
                for i, arrow in enumerate(self.map_view.arrows):
                    arrow.arrow_list_index = i
                event.accept()
                return

            # Left button and no ALT/SHIFT: endpoints or middle
            if event.button() == Qt.LeftButton:
                r2 = self.dragpoint_click_radius ** 2
                if self._dist2(scene_pos, self.start_point) <= r2:
                    self.dragging_start = True
                    event.accept()
                    return
                if self._dist2(scene_pos, self.end_point) <= r2:
                    self.dragging_end = True
                    event.accept()
                    return

                mid = self._bezier_midpoint()
                if self._dist2(scene_pos, mid) <= self.dragpoint_click_radius ** 2:
                    self.dragging_middle = True
                    event.accept()
                    return

            # Middle button: move whole arrow
            if event.button() == Qt.LeftButton:
                self._dragging = True
                self._last_mouse_scene_pos = event.scenePos()
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.map_view.arrow_drawing_mode:
            new_pos = event.scenePos()

            # Drag endpoints or middle
            if self.dragging_start or self.dragging_end or self.dragging_middle:
                if self.dragging_start:
                    self.start_point = new_pos
                elif self.dragging_end:
                    self.end_point = new_pos
                elif self.dragging_middle:
                    self.bending = self._bending_from_control_point(new_pos)

                self.update_path()
                self._store_geometry()
                event.accept()
                return

            # Drag whole arrow
            if self._dragging:
                current = event.scenePos()
                dx = current.x() - self._last_mouse_scene_pos.x()
                dy = current.y() - self._last_mouse_scene_pos.y()
                self._last_mouse_scene_pos = current

                delta = QPointF(dx, dy)
                self.start_point += delta
                self.end_point += delta
                # bending unchanged under translation
                self.update_path()
                self._store_geometry()
                event.accept()
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.map_view.arrow_drawing_mode:
            if event.button() == Qt.LeftButton and (
                self.dragging_start or self.dragging_end or self.dragging_middle
            ):
                self.dragging_start = False
                self.dragging_end = False
                self.dragging_middle = False
                event.accept()
                return

            if self._dragging and event.button() == Qt.LeftButton:
                self._dragging = False
                event.accept()
                return

        super().mouseReleaseEvent(event)
    
    def _draw_arrowhead(self, painter, tip: QPointF, direction: QPointF):
        angle = math.atan2(direction.y(), direction.x())

        arrow_size = max(8.0, self.width * 4.0)
        phi = math.pi / 6 if self.width <= 5 else math.pi / 5

        p1 = QPointF(
            tip.x() - arrow_size * math.cos(angle - phi),
            tip.y() - arrow_size * math.sin(angle - phi),
        )
        p2 = QPointF(
            tip.x() - arrow_size * math.cos(angle + phi),
            tip.y() - arrow_size * math.sin(angle + phi),
        )

        painter.drawPolygon(tip, p1, p2)

    def paint(self, painter: QPainter, option, widget=None):
        painter.setPen(QPen(self.color, self.width))
        painter.drawPath(self.path())

        # arrowhead aligned with tangent at end of Bézier
        control = self._control_point_from_bending()
        tangent = QPointF(
            2 * (self.end_point.x() - control.x()),
            2 * (self.end_point.y() - control.y()),
        )
        if tangent.manhattanLength() == 0:
            return

        painter.setBrush(self.color)

        control = self._control_point_from_bending()

        # arrowhead at END → points INTO the curve
        if self.head_mode in ("end", "both"):
            direction = self.end_point - control
            self._draw_arrowhead(painter, self.end_point, direction)

        # arrowhead at START → points AWAY from the curve
        if self.head_mode == "both":
            direction = self.start_point - control
            self._draw_arrowhead(painter, self.start_point, direction)

        if self.map_view.arrow_drawing_mode:
            start, end, mid = self.start_point, self.end_point, self._bezier_midpoint()

            painter.save()
            painter.setPen(QPen(QColor("white"), 2))
            painter.setBrush(QColor(0, 120, 255, 200))  # simple blue fill

            r = self.dragpoint_draw_radius
            painter.drawEllipse(start, r, r)
            painter.drawEllipse(end, r, r)

            painter.setBrush(QColor(255, 170, 0, 220))  # middle handle different color
            painter.drawEllipse(mid, r, r)
            painter.restore()
    
    def mouseDoubleClickEvent(self, event):
        if not self.map_view.arrow_drawing_mode:
            return super().mouseDoubleClickEvent(event)

        dlg = ArrowEditDialog(self)
        if dlg.exec():
            dlg.apply()

        event.accept()
    
    def boundingRect(self) -> QRectF:
        # Start with the path bounding rect
        rect = self.path().boundingRect()

        # Maximum visual extension:
        # - pen width
        # - arrowhead size
        # - drag handles
        margin = max(
            self.width * 2.5,
            20.0, # arrowhead size
            self.dragpoint_draw_radius * 2,
        )

        return rect.adjusted(-margin, -margin, margin, margin)


class ArrowEditDialog(QDialog):
    def __init__(self, arrow: "ArrowItem"):
        super().__init__(arrow.map_view)
        self.arrow = arrow
        self.setWindowTitle("Edit Arrow")

        self.sx = QLineEdit(str(arrow.start_point.x()))
        self.sy = QLineEdit(str(arrow.start_point.y()))
        self.ex = QLineEdit(str(arrow.end_point.x()))
        self.ey = QLineEdit(str(arrow.end_point.y()))

        self.bending = QLineEdit(str(arrow.bending))
        self.width = QLineEdit(str(arrow.width))
        self.color = QLineEdit(arrow.color.name())

        layout = QFormLayout(self)
        layout.addRow("Start X", self.sx)
        layout.addRow("Start Y", self.sy)
        layout.addRow("End X", self.ex)
        layout.addRow("End Y", self.ey)
        layout.addRow("Bending", self.bending)
        layout.addRow("Width", self.width)
        layout.addRow("Color (hex)", self.color)

        self.head_none = QRadioButton("No arrowhead")
        self.head_end = QRadioButton("Arrowhead at end")
        self.head_both = QRadioButton("Arrowhead at both ends")
        buttons = QButtonGroup(self)
        buttons.addButton(self.head_none)
        buttons.addButton(self.head_end)
        buttons.addButton(self.head_both)
        layout.addRow(QLabel("Arrowhead"))
        layout.addRow(self.head_none)
        layout.addRow(self.head_end)
        layout.addRow(self.head_both)

        if arrow.head_mode == "none":
            self.head_none.setChecked(True)
        elif arrow.head_mode == "both":
            self.head_both.setChecked(True)
        else:
            self.head_end.setChecked(True)

        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
    
    def apply(self):
        arrow = self.arrow

        arrow.start_point = QPointF(float(self.sx.text()), float(self.sy.text()))
        arrow.end_point = QPointF(float(self.ex.text()), float(self.ey.text()))
        arrow.bending = float(self.bending.text())

        arrow.width = float(self.width.text())
        arrow.color = QColor(self.color.text())
        arrow.setPen(QPen(arrow.color, arrow.width))

        if self.head_none.isChecked():
            arrow.head_mode = "none"
        elif self.head_both.isChecked():
            arrow.head_mode = "both"
        else:
            arrow.head_mode = "end"

        arrow.update_path()
        arrow._store_geometry()


class MapView(QGraphicsView):
    """A map of reaction boxes"""

    def __init__(self, appdata: AppData, central_widget, name: str):
        self.scene: QGraphicsScene = QGraphicsScene()
        QGraphicsView.__init__(self, self.scene)
        self.background: QGraphicsSvgItem = None
        palette = self.palette()
        # Set color of Map etc. backgrounds
        if appdata.is_in_dark_mode:
            palette.setColor(QPalette.Base, QColor(90, 90, 90))
        else:
            palette.setColor(QPalette.Base, QColor(250, 250, 250))
        self.setPalette(palette)
        self.setInteractive(True)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.appdata = appdata
        self.central_widget = central_widget
        self.name: str = name
        self.setAcceptDrops(True)
        self.drag_map = False
        self.reaction_boxes: dict[str, "ReactionBox"] = {}
        self._zoom = 0
        self.previous_point = None
        self.select = False
        self.select_start = None

        self.arrow_drawing_mode = False
        self.arrow_start_point: QPointF = None
        self.temp_arrow_line: QGraphicsLineItem = None
        self.arrows: list[ArrowItem] = []

        self.dragged_label: QGraphicsTextItem | None = None
        self.label_drag_offset = QPointF()

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
        if event.modifiers() == Qt.AltModifier and event.key() == Qt.Key_A:
            self.enterArrowDrawingMode()
            event.accept()
            return

        if (
            self.arrow_drawing_mode
            and event.modifiers() == Qt.AltModifier
            and event.key() == Qt.Key_T
        ):
            self.add_text_at_mouse()
            event.accept()
            return

        if not self.drag_map and event.key() in (Qt.Key_Control, Qt.Key_Shift):
            self.viewport().setCursor(Qt.ArrowCursor)
            self.select = True
        else:
            super().keyPressEvent(event)

    def enterArrowDrawingMode(self) -> bool:
        self.arrow_drawing_mode = not self.arrow_drawing_mode
        for arrow in self.arrows:
            arrow.update()
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
        if not self.hasFocus():
            return
        if (
            self.arrow_drawing_mode
            and event.button() == Qt.LeftButton
            and not (event.modifiers() & Qt.AltModifier)
        ):
            scene_pos = self.mapToScene(event.pos())
            items = self.scene.items(scene_pos)

            for item in items:
                if isinstance(item, QGraphicsTextItem):
                    self.dragged_label = item
                    self.label_drag_offset = scene_pos - item.pos()
                    self.viewport().setCursor(Qt.ClosedHandCursor)
                    event.accept()
                    return

        if (
            self.arrow_drawing_mode
            and event.button() == Qt.LeftButton
            and (event.modifiers() & Qt.AltModifier)
        ):
            scene_pos = self.mapToScene(event.pos())
            items = self.scene.items(scene_pos)

            for item in items:
                if isinstance(item, QGraphicsTextItem):
                    idx = item.label_index

                    # remove graphics item
                    self.scene.removeItem(item)

                    # remove from stored labels
                    labels = self.appdata.project.maps[self.name]["labels"]
                    del labels[idx]

                    # reindex remaining label items
                    for it in self.scene.items():
                        if isinstance(it, QGraphicsTextItem) and hasattr(it, "label_index"):
                            if it.label_index > idx:
                                it.label_index -= 1

                    print(f"Deleted label: '{item.toPlainText()}'")
                    event.accept()
                    return

            # ALT+click did not hit a label → do nothing
            event.accept()
            return

        if (self.arrow_drawing_mode
        and event.button() == Qt.LeftButton
        and (event.modifiers() & Qt.ShiftModifier)):
            scene_pos = self.mapToScene(event.pos())
            items = self.scene.items(scene_pos)

            for it in items:
                if isinstance(it, ArrowItem):
                    QGraphicsView.mousePressEvent(self, event)
                    return

            self.arrow_start_point = scene_pos

            pen = QPen(Qt.blue)
            pen.setWidth(2)
            self.temp_arrow_line = QGraphicsLineItem(
                self.arrow_start_point.x(),
                self.arrow_start_point.y(),
                self.arrow_start_point.x(),
                self.arrow_start_point.y(),
            )
            self.temp_arrow_line.setPen(pen)
            self.scene.addItem(self.temp_arrow_line)

            event.accept()
            return

        if self.select:  # select multiple boxes
            self.setDragMode(QGraphicsView.RubberBandDrag)
            self.select_start = self.mapToScene(event.pos())
        else:  # drag entire map
            self.viewport().setCursor(Qt.ClosedHandCursor)
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.drag_map = True

        super(MapView, self).mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.arrow_drawing_mode and self.arrow_start_point and self.temp_arrow_line:
            current_point = self.mapToScene(event.pos())
            self.temp_arrow_line.setLine(
                self.arrow_start_point.x(),
                self.arrow_start_point.y(),
                current_point.x(),
                current_point.y(),
            )
            event.accept()
            return
        
        if self.arrow_drawing_mode and self.dragged_label:
            scene_pos = self.mapToScene(event.pos())
            self.dragged_label.setPos(scene_pos - self.label_drag_offset)
            event.accept()
            return

        super(MapView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.arrow_drawing_mode and self.dragged_label and event.button() == Qt.LeftButton:
            label = self.dragged_label
            self.dragged_label = None
            self.viewport().setCursor(Qt.CrossCursor)

            idx = label.label_index
            labels = self.appdata.project.maps[self.name]["labels"]

            text, _, _, font_size, color = labels[idx]
            labels[idx] = (text, label.x(), label.y(), font_size, color)

            event.accept()
            return
        if (
            self.arrow_drawing_mode
            and self.arrow_start_point
            and event.button() == Qt.LeftButton
        ):
            end_point = self.mapToScene(event.pos())

            if self.temp_arrow_line:
                self.scene.removeItem(self.temp_arrow_line)
                self.temp_arrow_line = None

            # Check if arrow is long enough to draw a final one
            if (end_point - self.arrow_start_point).manhattanLength() > 5:
                bending = 0.0
                self.draw_final_arrow(self.arrow_start_point, end_point, bending)
                self.appdata.project.maps[self.name]["arrows"].append(
                    (
                        (self.arrow_start_point.x(), self.arrow_start_point.y()),
                        (end_point.x(), end_point.y()),
                        float(bending),
                        3.0,
                        "#000000",
                        "end",
                    )
                )

            self.arrow_start_point = None
            event.accept()
            return

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

    def draw_final_arrow(self, start, end, bending=0.0, width=3.0, color="black"):
        arrow = ArrowItem(
            start,
            end,
            self,
            len(self.arrows),
            bending=bending,
            width=width,
            color=color,
        )
        self.arrows.append(arrow)
        self.scene.addItem(arrow)
        return arrow

    def focusOutEvent(self, event):
        super(MapView, self).focusOutEvent(event)
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
        box: "ReactionBox" = self.reaction_boxes.get(reac_id, None)
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
            for data in map_data["arrows"]:
                (sx, sy), (ex, ey), bending, width, color = data

                self.draw_final_arrow(
                    QPointF(sx, sy),
                    QPointF(ex, ey),
                    bending=bending,
                    width=width,
                    color=color,
                )
        else:
            map_data["arrows"] = []

        if "labels" in self.appdata.project.maps[self.name]:
            for i, data in enumerate(self.appdata.project.maps[self.name]["labels"]):
                text, x, y, font_size, color = data

                li = LabelItem(
                    text,
                    QPointF(x, y),
                    self,
                    i,
                    font_size=font_size,
                    color=color,
                )
                self.scene.addItem(li)
        else:
            map_data["labels"] = []

    def delete_box(self, reaction_id: str) -> bool:
        box = self.reaction_boxes.get(reaction_id, None)
        if box is not None:
            lineedit = box.proxy
            self.scene.removeItem(lineedit)
            self.scene.removeItem(box)
            return True
        else:
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

        self.set_values()
        self.recolor_all()

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

    def add_text_at_mouse(self):
        text, ok = QInputDialog.getText(self, "Add Text", "Enter text to display:")
        if ok and text.strip():
            mouse_pos = self.mapToScene(self.mapFromGlobal(QCursor.pos()))

            labels = self.appdata.project.maps[self.name].setdefault("labels", [])
            label_index = len(labels)
            labels.append((
                text,
                mouse_pos.x(),
                mouse_pos.y(),
                12,
                "#000000",
                "end",
            ))

            label_item = LabelItem(text, mouse_pos, self, label_index)
            self.scene.addItem(label_item)

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
        self.parent: "ReactionBox" = parent
        self.accept_next_change_into_history = True
        super().__init__()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.parent.setSelected(False)
        if self.isModified() and self.parent.map.appdata.auto_fba:
            self.parent.map.central_widget.parent.fba()
        self.parent.update()

    def focusInEvent(self, event):
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
        # to bes called after focusInEvent
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
        self.item.setTextMargins(1, -13, 0, -10)
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

        # create context menu (on right click)
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
        self.proxy.clearFocus()
        self.map.setFocus()
        self.item.accept_next_change_into_history = (
            True  # reset so that next change will be recorded
        )

    def handle_editing_finished(self):
        if self.item.isModified() and self.map.appdata.auto_fba:
            self.map.central_widget.parent.fba()

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
        if self.isSelected():
            light_blue = QColor(100, 100, 200)
            pen = QPen(light_blue)
            pen.setWidth(6)
            painter.setPen(pen)
            painter.drawRect(
                -6,
                -6,
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
                -3,
                -3,
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
