"""Qt Quick based CNApy map view.

This module mirrors the signal and method surface of :mod:`map_view` while
moving the actual map canvas to the Qt Quick scene graph.  It is intentionally
feature-flagged by callers so the established QGraphicsView implementation can
remain the default until the QML path has seen broader testing.
"""

import importlib.resources as resources
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from qtpy.QtCore import (QAbstractListModel, QByteArray, QModelIndex, QObject,
                         Property, QMimeData, QRectF, Qt, QUrl, Signal, Slot)
from qtpy.QtGui import QColor, QDragEnterEvent, QDropEvent, QGuiApplication
from qtpy.QtQuickWidgets import QQuickWidget
from qtpy.QtWidgets import QVBoxLayout, QWidget

from cnapy.appdata import AppData
from cnapy.gui_elements.map_view import DECREASE_FACTOR, INCREASE_FACTOR, validate_value


class ReactionBoxRoles:
    IdRole = Qt.ItemDataRole.UserRole + 1
    NameRole = IdRole + 1
    XRole = NameRole + 1
    YRole = XRole + 1
    ValueRole = YRole + 1
    FillColorRole = ValueRole + 1
    ForegroundColorRole = FillColorRole + 1
    SelectedRole = ForegroundColorRole + 1
    TooltipRole = SelectedRole + 1


class ReactionBoxListModel(QAbstractListModel):
    """List model consumed by the QML reaction-box Repeater."""

    def __init__(self, appdata: AppData, map_name: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.appdata = appdata
        self.map_name = map_name
        self.ids: List[str] = []
        self.selected_ids = set()
        self.rebuild()

    def roleNames(self) -> Dict[int, QByteArray]:
        return {
            ReactionBoxRoles.IdRole: QByteArray(b"reactionId"),
            ReactionBoxRoles.NameRole: QByteArray(b"reactionName"),
            ReactionBoxRoles.XRole: QByteArray(b"boxX"),
            ReactionBoxRoles.YRole: QByteArray(b"boxY"),
            ReactionBoxRoles.ValueRole: QByteArray(b"valueText"),
            ReactionBoxRoles.FillColorRole: QByteArray(b"fillColor"),
            ReactionBoxRoles.ForegroundColorRole: QByteArray(b"foregroundColor"),
            ReactionBoxRoles.SelectedRole: QByteArray(b"selected"),
            ReactionBoxRoles.TooltipRole: QByteArray(b"tooltipText"),
        }

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self.ids)

    def data(self, index: QModelIndex, role: int):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self.ids):
            return None

        reaction_id = self.ids[index.row()]
        boxes = self.appdata.project.maps[self.map_name]["boxes"]
        if reaction_id not in boxes:
            return None

        if role == ReactionBoxRoles.IdRole:
            return reaction_id
        if role == ReactionBoxRoles.NameRole:
            return self._reaction_name(reaction_id)
        if role == ReactionBoxRoles.XRole:
            return float(boxes[reaction_id][0])
        if role == ReactionBoxRoles.YRole:
            return float(boxes[reaction_id][1])
        if role == ReactionBoxRoles.ValueRole:
            return self._value_text(reaction_id)
        if role == ReactionBoxRoles.FillColorRole:
            return self._fill_color(reaction_id).name(QColor.NameFormat.HexArgb)
        if role == ReactionBoxRoles.ForegroundColorRole:
            return self._foreground_color(reaction_id).name(QColor.NameFormat.HexArgb)
        if role == ReactionBoxRoles.SelectedRole:
            return reaction_id in self.selected_ids
        if role == ReactionBoxRoles.TooltipRole:
            return self._tooltip(reaction_id)
        return None

    def rebuild(self):
        self.beginResetModel()
        self.ids = list(self.appdata.project.maps[self.map_name]["boxes"].keys())
        self.selected_ids.intersection_update(self.ids)
        self.endResetModel()

    def index_for_reaction(self, reaction_id: str) -> QModelIndex:
        if reaction_id not in self.ids:
            return QModelIndex()
        return self.index(self.ids.index(reaction_id), 0)

    def emit_reaction_changed(self, reaction_id: str):
        index = self.index_for_reaction(reaction_id)
        if index.isValid():
            self.dataChanged.emit(index, index, list(self.roleNames().keys()))

    def add_or_refresh_reaction(self, reaction_id: str):
        if reaction_id in self.ids:
            self.emit_reaction_changed(reaction_id)
            return
        row = len(self.ids)
        self.beginInsertRows(QModelIndex(), row, row)
        self.ids.append(reaction_id)
        self.endInsertRows()

    def remove_reaction(self, reaction_id: str):
        if reaction_id not in self.ids:
            return
        row = self.ids.index(reaction_id)
        self.beginRemoveRows(QModelIndex(), row, row)
        self.ids.pop(row)
        self.selected_ids.discard(reaction_id)
        self.endRemoveRows()

    def set_selected(self, reaction_id: str, selected: bool, exclusive: bool):
        changed = set(self.selected_ids)
        if exclusive:
            self.selected_ids.clear()
        if selected:
            self.selected_ids.add(reaction_id)
        else:
            self.selected_ids.discard(reaction_id)
        changed.update(self.selected_ids)
        for changed_id in changed:
            self.emit_reaction_changed(changed_id)

    def clear_selection(self):
        previous = list(self.selected_ids)
        self.selected_ids.clear()
        for reaction_id in previous:
            self.emit_reaction_changed(reaction_id)

    def selected_reactions(self) -> List[str]:
        return list(self.selected_ids)

    def select_in_rect(self, rect: QRectF, exclusive: bool):
        if exclusive:
            self.selected_ids.clear()
        boxes = self.appdata.project.maps[self.map_name]["boxes"]
        width = self.appdata.box_width
        height = self.appdata.box_height
        for reaction_id, (x, y) in boxes.items():
            if rect.intersects(QRectF(float(x), float(y), width, height)):
                self.selected_ids.add(reaction_id)
        self._emit_all_selected_changed()

    def _emit_all_selected_changed(self):
        for reaction_id in self.ids:
            self.emit_reaction_changed(reaction_id)

    def _reaction_name(self, reaction_id: str) -> str:
        try:
            return self.appdata.project.cobra_py_model.reactions.get_by_id(reaction_id).name
        except KeyError:
            return ""

    def _value_text(self, reaction_id: str) -> str:
        value = None
        if reaction_id in self.appdata.project.scen_values:
            value = self.appdata.project.scen_values[reaction_id]
        elif reaction_id in self.appdata.project.comp_values:
            value = self.appdata.project.comp_values[reaction_id]
        if value is None:
            return ""
        vl, vu = value
        if math.isclose(vl, vu, abs_tol=self.appdata.abs_tol):
            return str(round(float(vl), self.appdata.rounding)).rstrip("0").rstrip(".")
        return (str(round(float(vl), self.appdata.rounding)).rstrip("0").rstrip(".")
                + ", "
                + str(round(float(vu), self.appdata.rounding)).rstrip("0").rstrip("."))

    def _fill_color(self, reaction_id: str) -> QColor:
        value_text = self._value_text(reaction_id)
        if value_text == "":
            color = QColor(self.appdata.default_color)
            color.setAlphaF(0.4)
            return color
        if not validate_value(value_text):
            return QColor(Qt.GlobalColor.white)
        if reaction_id in self.appdata.project.scen_values:
            return QColor(self.appdata.scen_color)
        if reaction_id in self.appdata.project.comp_values:
            vl, vu = self.appdata.project.comp_values[reaction_id]
            if math.isclose(vl, vu, abs_tol=self.appdata.abs_tol):
                if self.appdata.modes_coloring:
                    return QColor(Qt.GlobalColor.red if vl == 0 else Qt.GlobalColor.green)
                return QColor(self.appdata.comp_color)
            if (math.isclose(vl, 0.0, abs_tol=self.appdata.abs_tol)
                    or math.isclose(vu, 0.0, abs_tol=self.appdata.abs_tol)
                    or (vl <= 0 <= vu)):
                return QColor(self.appdata.special_color_1)
            return QColor(self.appdata.special_color_2)
        return QColor(self.appdata.comp_color)

    def _foreground_color(self, reaction_id: str) -> QColor:
        value_text = self._value_text(reaction_id)
        if value_text and not validate_value(value_text):
            return QColor(self.appdata.scen_color_bad)
        return QColor(Qt.GlobalColor.black)

    def _tooltip(self, reaction_id: str) -> str:
        try:
            r = self.appdata.project.cobra_py_model.reactions.get_by_id(reaction_id)
        except KeyError:
            return reaction_id
        return ("Id: " + r.id + "\nName: " + r.name
                + "\nEquation: " + r.build_reaction_string()
                + "\nLowerbound: " + str(r.lower_bound)
                + "\nUpper bound: " + str(r.upper_bound)
                + "\nObjective coefficient: " + str(r.objective_coefficient))


class QmlMapController(QObject):
    """Python controller exposed to QML."""

    switchToReactionMask = Signal(str)
    maximizeReaction = Signal(str)
    minimizeReaction = Signal(str)
    setScenValue = Signal(str)
    reactionRemoved = Signal(str)
    reactionValueChanged = Signal(str, str)
    reactionAdded = Signal(str)
    mapChanged = Signal(str)
    broadcastReactionID = Signal(str)

    zoomChanged = Signal()
    boxSizeChanged = Signal()
    backgroundChanged = Signal()
    viewportPositionChanged = Signal()

    def __init__(self, appdata: AppData, central_widget, name: str, parent: Optional[QObject] = None):
        super().__init__(parent)
        self.appdata = appdata
        self.central_widget = central_widget
        self.name = name
        self.boxes_model = ReactionBoxListModel(appdata, name, self)

    @Property(QObject, constant=True)
    def reactionBoxes(self):
        return self.boxes_model

    @Property(float, notify=zoomChanged)
    def zoomFactor(self) -> float:
        return INCREASE_FACTOR ** self.appdata.project.maps[self.name]["zoom"]

    @Property(float, notify=boxSizeChanged)
    def boxScale(self) -> float:
        return float(self.appdata.project.maps[self.name]["box-size"])

    @Property(float, notify=backgroundChanged)
    def backgroundScale(self) -> float:
        return float(self.appdata.project.maps[self.name]["bg-size"])

    @Property(float, constant=True)
    def boxWidth(self) -> float:
        return float(self.appdata.box_width)

    @Property(float, constant=True)
    def boxHeight(self) -> float:
        return float(self.appdata.box_height)

    @Property(QUrl, notify=backgroundChanged)
    def backgroundUrl(self) -> QUrl:
        return QUrl.fromLocalFile(self.appdata.project.maps[self.name]["background"])

    @Property(float, notify=viewportPositionChanged)
    def contentX(self) -> float:
        return float(self.appdata.project.maps[self.name]["pos"][0])

    @Property(float, notify=viewportPositionChanged)
    def contentY(self) -> float:
        return float(self.appdata.project.maps[self.name]["pos"][1])

    @Slot(float, float)
    def setViewportPosition(self, x: float, y: float):
        self.appdata.project.maps[self.name]["pos"] = (x, y)
        self.viewportPositionChanged.emit()

    @Slot(float, float)
    def addReactionAt(self, x: float, y: float):
        mime_data = QGuiApplication.clipboard().mimeData()
        if mime_data.hasText():
            self.addReactionFromIdAt(mime_data.text(), x, y)

    @Slot(str, float, float)
    def addReactionFromIdAt(self, reaction_id: str, x: float, y: float):
        boxes = self.appdata.project.maps[self.name]["boxes"]
        is_new = reaction_id not in boxes
        boxes[reaction_id] = (x, y)
        self.boxes_model.add_or_refresh_reaction(reaction_id)
        if is_new:
            self.reactionAdded.emit(reaction_id)
        self.mapChanged.emit(reaction_id)

    @Slot(str, float, float)
    def setBoxPosition(self, reaction_id: str, x: float, y: float):
        boxes = self.appdata.project.maps[self.name]["boxes"]
        selected = self.boxes_model.selected_reactions()
        if reaction_id not in selected:
            selected = [reaction_id]
        old_x, old_y = boxes.get(reaction_id, (x, y))
        dx = x - old_x
        dy = y - old_y
        for selected_id in selected:
            current_x, current_y = boxes[selected_id]
            boxes[selected_id] = (current_x + dx, current_y + dy)
            self.boxes_model.emit_reaction_changed(selected_id)
            self.mapChanged.emit(selected_id)

    @Slot(str, str)
    def setReactionValue(self, reaction_id: str, value: str):
        self.reactionValueChanged.emit(reaction_id, value)
        self.boxes_model.emit_reaction_changed(reaction_id)

    @Slot(str)
    def removeBox(self, reaction_id: str):
        boxes = self.appdata.project.maps[self.name]["boxes"]
        if reaction_id in boxes:
            del boxes[reaction_id]
            self.boxes_model.remove_reaction(reaction_id)
            self.reactionRemoved.emit(reaction_id)

    @Slot(str, bool, bool)
    def setSelected(self, reaction_id: str, selected: bool, exclusive: bool):
        self.boxes_model.set_selected(reaction_id, selected, exclusive)
        if selected:
            self.broadcastReactionID.emit(reaction_id)

    @Slot()
    def clearSelection(self):
        self.boxes_model.clear_selection()

    @Slot(float, float, float, float, bool)
    def selectRect(self, x: float, y: float, width: float, height: float, exclusive: bool):
        rect = QRectF(x, y, width, height).normalized()
        self.boxes_model.select_in_rect(rect, exclusive)

    @Slot(str)
    def switchToReaction(self, reaction_id: str):
        self.switchToReactionMask.emit(reaction_id)

    @Slot(str)
    def maximize(self, reaction_id: str):
        self.maximizeReaction.emit(reaction_id)

    @Slot(str)
    def minimize(self, reaction_id: str):
        self.minimizeReaction.emit(reaction_id)

    @Slot(str)
    def useAsScenarioValue(self, reaction_id: str):
        self.setScenValue.emit(reaction_id)

    @Slot(int)
    def zoomSteps(self, steps: int):
        maps = self.appdata.project.maps[self.name]
        maps["zoom"] += steps
        self.zoomChanged.emit()

    @Slot(float)
    def scaleBoxesBy(self, factor: float):
        self.appdata.project.maps[self.name]["box-size"] *= factor
        self.boxSizeChanged.emit()
        self.boxes_model._emit_all_selected_changed()
        self.mapChanged.emit("dummy")

    @Slot()
    def rebuild(self):
        self._ensure_background()
        self.boxes_model.rebuild()
        self.backgroundChanged.emit()
        self.boxSizeChanged.emit()
        self.zoomChanged.emit()
        self.viewportPositionChanged.emit()

    def _ensure_background(self):
        maps = self.appdata.project.maps[self.name]
        if (len(maps["boxes"]) > 0
                and maps["background"].replace("\\", "/").endswith("/data/default-bg.svg")):
            with resources.as_file(resources.files("cnapy") / "data" / "blank.svg") as path:
                maps["background"] = str(path)

    def update_reaction(self, reaction_id: str):
        self.boxes_model.emit_reaction_changed(reaction_id)


class QmlMapView(QWidget):
    """QWidget-compatible wrapper around the Qt Quick map canvas."""

    switchToReactionMask = Signal(str)
    maximizeReaction = Signal(str)
    minimizeReaction = Signal(str)
    setScenValue = Signal(str)
    reactionRemoved = Signal(str)
    reactionValueChanged = Signal(str, str)
    reactionAdded = Signal(str)
    mapChanged = Signal(str)
    broadcastReactionID = Signal(str)

    def __init__(self, appdata: AppData, central_widget, name: str):
        super().__init__()
        self.appdata = appdata
        self.central_widget = central_widget
        self.name = name
        self.controller = QmlMapController(appdata, central_widget, name, self)
        self.quick = QQuickWidget(self)
        self.quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.quick.setAcceptDrops(True)
        self.setAcceptDrops(True)
        self.quick.rootContext().setContextProperty("mapController", self.controller)
        qml_path = Path(__file__).with_name("qml") / "MapView.qml"
        self.quick.setSource(QUrl.fromLocalFile(str(qml_path)))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.quick)

        self.controller.switchToReactionMask.connect(self.switchToReactionMask)
        self.controller.maximizeReaction.connect(self.maximizeReaction)
        self.controller.minimizeReaction.connect(self.minimizeReaction)
        self.controller.setScenValue.connect(self.setScenValue)
        self.controller.reactionRemoved.connect(self.reactionRemoved)
        self.controller.reactionValueChanged.connect(self.reactionValueChanged)
        self.controller.reactionAdded.connect(self.reactionAdded)
        self.controller.mapChanged.connect(self.mapChanged)
        self.controller.broadcastReactionID.connect(self.broadcastReactionID)
        self.controller.rebuild()

    def update(self):
        self.controller.rebuild()
        super().update()

    def fit(self):
        root = self.quick.rootObject()
        if root is not None:
            root.fitToView()

    def focus_reaction(self, reaction: str):
        root = self.quick.rootObject()
        if root is not None and reaction in self.appdata.project.maps[self.name]["boxes"]:
            x, y = self.appdata.project.maps[self.name]["boxes"][reaction]
            root.centerOnPoint(float(x), float(y))
        self.zoom_in_reaction()

    def zoom_in(self):
        self.appdata.project.maps[self.name]["zoom"] += 1
        self.controller.zoomChanged.emit()

    def zoom_out(self):
        self.appdata.project.maps[self.name]["zoom"] -= 1
        self.controller.zoomChanged.emit()

    def zoom_in_reaction(self):
        bg_size = self.appdata.project.maps[self.name]["bg-size"]
        x = (INCREASE_FACTOR ** self.appdata.project.maps[self.name]["zoom"]) / bg_size
        while x < 1:
            self.appdata.project.maps[self.name]["zoom"] += 1
            x = (INCREASE_FACTOR ** self.appdata.project.maps[self.name]["zoom"]) / bg_size
        self.controller.zoomChanged.emit()

    def select_single_reaction(self, reac_id: str):
        self.controller.clearSelection()
        self.controller.setSelected(reac_id, True, True)

    def update_selected(self, found_ids):
        root = self.quick.rootObject()
        if root is not None:
            root.setFilterTerms([str(term).lower() for term in found_ids])

    def highlight_reaction(self, string):
        self.select_single_reaction(string)
        self.focus_reaction(string)

    def delete_box(self, reaction_id: str) -> bool:
        if reaction_id in self.appdata.project.maps[self.name]["boxes"]:
            self.controller.removeBox(reaction_id)
            return True
        return False

    def update_reaction(self, old_reaction_id: str, new_reaction_id: str):
        boxes = self.appdata.project.maps[self.name]["boxes"]
        if old_reaction_id in boxes:
            boxes[new_reaction_id] = boxes.pop(old_reaction_id)
            self.controller.rebuild()

    def remove_box(self, reaction: str):
        self.controller.removeBox(reaction)

    def recolor_all(self):
        self.controller.boxes_model._emit_all_selected_changed()

    def set_values(self):
        self.controller.boxes_model._emit_all_selected_changed()

    def value_changed(self, reaction: str, value: str):
        self.controller.setReactionValue(reaction, value)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasText():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent):
        mime: QMimeData = event.mimeData()
        if not mime.hasText():
            event.ignore()
            return
        root = self.quick.rootObject()
        position = event.position()
        x = position.x()
        y = position.y()
        if root is not None:
            mapped = root.mapToMapLayer(x, y)
            x = mapped.x()
            y = mapped.y()
        self.controller.addReactionFromIdAt(mime.text(), x, y)
        event.acceptProposedAction()
