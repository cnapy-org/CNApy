"""The PyNetAnalyzer map view"""
from PySide2.QtGui import QPainter, QDrag, QColor, QPalette, QMouseEvent
from PySide2.QtCore import Qt, QPoint, QRectF, QMimeData
from PySide2.QtWidgets import (QWidget, QGraphicsItem, QGraphicsScene, QGraphicsView, QLineEdit,
                               QGraphicsSceneDragDropEvent, QGraphicsSceneMouseEvent, QAction, QMenu)
from PySide2.QtSvg import QGraphicsSvgItem
from PySide2.QtCore import Signal


class MapView(QGraphicsView):
    """A map of reaction boxes"""

    def __init__(self, appdata, idx):
        self.scene = QGraphicsScene()
        QGraphicsView.__init__(self, self.scene)
        palette = self.palette()
        palette.setColor(QPalette.Base, Qt.white)
        self.setPalette(palette)

        self.appdata = appdata
        self.idx = idx
        self.setAcceptDrops(True)
        self.drag_over = False
        self.reaction_boxes = {}
        self._zoom = 0
        self.drag = False

        # initial scale
        self._zoom = self.appdata.maps[self.idx]["zoom"]
        if self._zoom > 0:
            for i in range(1, self._zoom):
                self.scale(1.25, 1.25)
        if self._zoom < 0:
            for i in range(self._zoom, -1):
                self.scale(0.8, 0.8)

        # connect events to methods
        self.horizontalScrollBar().valueChanged.connect(self.on_hbar_change)
        self.verticalScrollBar().valueChanged.connect(self.on_vbar_change)

    def on_hbar_change(self, x):
        self.appdata.maps[self.idx]["pos"] = (
            x, self.verticalScrollBar().value())

    def on_vbar_change(self, y):
        self.appdata.maps[self.idx]["pos"] = (
            self.horizontalScrollBar().value(), y)

    def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
        event.setAccepted(True)
        event.accept()
        event.acceptProposedAction()
        self.drag_over = True

    def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent):
        event.setAccepted(True)
        point = event.pos()
        point_item = self.mapToScene(point)
        key = event.mimeData().text()
        (_, _, name) = self.appdata.maps[self.idx]["boxes"][key]
        self.appdata.maps[self.idx]["boxes"][key] = (
            point_item.x(), point_item.y(), name)
        self.update()

    def dragLeaveEvent(self, _event):
        self.drag_over = False
        self.update()

    def dropEvent(self, event: QGraphicsSceneDragDropEvent):
        self.drag_over = False
        point = event.pos()
        point_item = self.mapToScene(point)
        key = event.mimeData().text()
        (_, _, name) = self.appdata.maps[self.idx]["boxes"][key]
        self.appdata.maps[self.idx]["boxes"][key] = (
            point_item.x(), point_item.y(), name)
        self.update()

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            factor = 1.25
            self._zoom += 1
        else:
            factor = 0.8
            self._zoom -= 1

        self.appdata.maps[self.idx]["zoom"] = self._zoom
        self.scale(factor, factor)

    # def toggleDragMode(self):
    #     if self.dragMode() == QGraphicsView.ScrollHandDrag:
    #         self.setDragMode(QGraphicsView.NoDrag)
    #     elif not self._photo.pixmap().isNull():
    #         self.setDragMode(QGraphicsView.ScrollHandDrag)

    def mousePressEvent(self, event):
        self.drag = True
        super(MapView, self).mousePressEvent(event)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        if self.drag:
            self.centerOn(event.pos())
        super(MapView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        self.drag = False
        super(MapView, self).mouseReleaseEvent(event)

    def update(self):
        print("MapView::update", self.idx)
        self.scene.clear()
        background = QGraphicsSvgItem(
            self.appdata.maps[self.idx]["background"])
        background.setFlags(QGraphicsItem.ItemClipsToShape)
        background.setScale(self.appdata.maps[self.idx]["bg-size"])
        self.scene.addItem(background)

        for key in self.appdata.maps[self.idx]["boxes"]:
            le1 = QLineEdit()
            le1.setMaximumWidth(80)
            le1.setToolTip(self.appdata.maps[self.idx]["boxes"][key][2])
            proxy1 = self.scene.addWidget(le1)
            proxy1.show()
            ler1 = ReactionBox(self, proxy1, le1, key)
            ler1.setPos(self.appdata.maps[self.idx]["boxes"][key]
                        [0], self.appdata.maps[self.idx]["boxes"][key][1])
            self.scene.addItem(ler1)
            self.reaction_boxes[key] = ler1

        self.set_values()

        # set scrollbars

        self.horizontalScrollBar().setValue(
            self.appdata.maps[self.idx]["pos"][0])
        self.verticalScrollBar().setValue(
            self.appdata.maps[self.idx]["pos"][1])

    def set_values(self):

        for key in self.appdata.maps[self.idx]["boxes"]:
            if key in self.appdata.scen_values.keys():
                self.reaction_boxes[key].set_val_and_color(
                    self.appdata.scen_values[key])
            elif key in self.appdata.comp_values.keys():
                self.reaction_boxes[key].set_val_and_color(
                    self.appdata.comp_values[key])

    def delete_box(self, key):
        # print("MapView::delete_box", key)
        del self.appdata.maps[self.idx]["boxes"][key]
        self.update()

    def emit_doubleClickedReaction(self, reaction: str):
        self.doubleClickedReaction.emit(reaction)

    def emit_value_changed(self, reaction: str, value: str):
        print("emit_value_changed")
        self.reactionValueChanged.emit(reaction, value)

    doubleClickedReaction = Signal(str)
    reactionValueChanged = Signal(str, str)


class ReactionBox(QGraphicsItem):
    """Handle to the line edits on the map"""

    def __init__(self, parent: MapView, proxy, item: QLineEdit, key: int):
        self.map = parent
        self.key = key
        self.proxy = proxy
        self.item = item
        QGraphicsItem.__init__(self)
        self.setCursor(Qt.OpenHandCursor)
        self.setAcceptedMouseButtons(Qt.LeftButton)
        self.item.textEdited.connect(self.value_changed)
        self.item.returnPressed.connect(self.returnPressed)

        self.item.setContextMenuPolicy(Qt.CustomContextMenu)
        self.item.customContextMenuRequested.connect(self.on_context_menu)

        # create context menu
        self.popMenu = QMenu(parent)
        delete_action = QAction('remove from map', parent)
        self.popMenu.addAction(delete_action)
        delete_action.triggered.connect(self.delete)
        self.popMenu.addSeparator()

    def returnPressed(self):
        print(self.key, "return pressed to", self.item.text())
        if verify_value(self.item.text()):
            self.map.emit_value_changed(self.key, self.item.text())

        # TODO: actually I want to repaint not scale
        self.map.scale(2, 2)
        self.map.scale(0.5, 0.5)

    def value_changed(self):
        print(self.key, "value changed to", self.item.text())
        if self.item.text() == "":
            self.map.emit_value_changed(self.key, self.item.text())
        elif verify_value(self.item.text()):
            self.map.emit_value_changed(self.key, self.item.text())
            self.set_color(self.map.appdata.compute_color(
                float(self.item.text())))

        # TODO: actually I want to repaint not scale
        self.map.scale(2, 2)
        self.map.scale(0.5, 0.5)

    def set_val_and_color(self, value):
        self.item.setText(str(value))
        self.item.setCursorPosition(0)
        color = self.map.appdata.compute_color(value)
        self.set_color(color)

    def set_color(self, color: QColor):
        palette = self.item.palette()
        palette.setColor(QPalette.Base, color)
        role = self.item.foregroundRole()
        palette.setColor(role, Qt.black)
        self.item.setPalette(palette)

    def boundingRect(self):
        return QRectF(-15, -15, 20, 20)

    def paint(self, painter: QPainter, option, widget: QWidget):
        painter.setPen(Qt.NoPen)
        # set color depending on wether the value belongs to the scenario
        if self.key in self.map.appdata.scen_values.keys():
            painter.setBrush(Qt.darkGreen)
        else:
            painter.setBrush(Qt.darkGray)

        painter.drawEllipse(-8, -8, 10, 10)

    def mousePressEvent(self, _event: QGraphicsSceneMouseEvent):
        pass

    def mouseReleaseEvent(self, _event: QGraphicsSceneMouseEvent):
        pass

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        drag = QDrag(event.widget())
        mime = QMimeData()
        mime.setText(str(self.key))
        drag.setMimeData(mime)
        # self.setCursor(Qt.ClosedHandCursor)
        drag.exec_()
        # self.setCursor(Qt.OpenHandCursor)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.map.emit_doubleClickedReaction(self.key)

    def setPos(self, x, y):
        self.proxy.setPos(x, y)
        super().setPos(x, y)

    def on_context_menu(self, point):
        # show context menu
        self.popMenu.exec_(self.item.mapToGlobal(point))

    def delete(self):
        # print('ReactionBox:delete')
        self.map.delete_box(self.key)


def verify_value(value):
    print("TODO: implement verify_value")
    return True
