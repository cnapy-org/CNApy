"""The PyNetAnalyzer map view"""
from PySide2.QtGui import QPainter, QDrag, QColor, QPalette
from PySide2.QtCore import Qt, QRectF, QMimeData
from PySide2.QtWidgets import (QWidget, QGraphicsItem, QGraphicsScene, QGraphicsView, QLineEdit,
                               QGraphicsSceneDragDropEvent, QGraphicsSceneMouseEvent)
from PySide2.QtSvg import QGraphicsSvgItem


class MapView(QGraphicsView):
    """A map of reaction boxes"""

    def __init__(self, appdata, scene: QGraphicsScene):
        QGraphicsView.__init__(self, scene)
        self.appdata = appdata
        self.setAcceptDrops(True)
        self.drag_over = False
        self.reaction_boxes = {}
        self._zoom = 0
        self.drag = False

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
        (_, _, name) = self.appdata.maps[0][key]
        self.appdata.maps[0][key] = (point_item.x(), point_item.y(), name)
        self.update()

    def dragLeaveEvent(self, _event):
        self.drag_over = False
        self.update()

    def dropEvent(self, event: QGraphicsSceneDragDropEvent):
        self.drag_over = False
        point = event.pos()
        point_item = self.mapToScene(point)
        key = event.mimeData().text()
        (_, _, name) = self.appdata.maps[0][key]
        self.appdata.maps[0][key] = (point_item.x(), point_item.y(), name)
        self.update()

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            factor = 1.25
            self._zoom += 1
        else:
            factor = 0.8
            self._zoom -= 1

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
        # print("MapView::update")
        self.scene().clear()
        background = QGraphicsSvgItem("testsvg.svg")
        background.setFlags(QGraphicsItem.ItemClipsToShape)
        self.scene().addItem(background)

        for key in self.appdata.maps[0]:
            le1 = QLineEdit()
            le1.setMaximumWidth(80)
            le1.setToolTip(self.appdata.maps[0][key][2])
            proxy1 = self.scene().addWidget(le1)
            proxy1.show()
            ler1 = ReactionBox(proxy1, le1, key)
            ler1.setPos(self.appdata.maps[0][key]
                        [0], self.appdata.maps[0][key][1])
            self.scene().addItem(ler1)
            self.reaction_boxes[key] = ler1

        self.set_values()

    def set_values(self):
        high = 0.0
        low = 0.0
        for key in self.appdata.values.keys():
            if self.appdata.values[key] > high:
                high = self.appdata.values[key]
            if self.appdata.values[key] < low:
                low = self.appdata.values[key]

        for key in self.appdata.maps[0]:
            if key in self.appdata.values.keys():
                self.reaction_boxes[key].item.setText(
                    str(self.appdata.values[key]))
                self.reaction_boxes[key].item.setCursorPosition(0)
                if self.appdata.values[key] > 0.0:
                    h = self.appdata.values[key] * 255 / high
                    color = QColor.fromRgb(255-h, 255, 255-h)
                else:
                    h = self.appdata.values[key]*255 / low
                    color = QColor.fromRgb(255, 255-h, 255-h)

                palette = self.reaction_boxes[key].item.palette()
                palette.setColor(QPalette.Base, color)
                role = self.reaction_boxes[key].item.foregroundRole()
                palette.setColor(role, Qt.black)
                self.reaction_boxes[key].item.setPalette(palette)


class ReactionBox(QGraphicsItem):
    """Handle to the line edits on the map"""

    def __init__(self, proxy, item: QLineEdit, key: int):
        self.key = key
        self.proxy = proxy
        self.item = item
        QGraphicsItem.__init__(self)
        self.setCursor(Qt.OpenHandCursor)
        self.setAcceptedMouseButtons(Qt.LeftButton)

    def boundingRect(self):
        return QRectF(-15, -15, 20, 20)

    def paint(self, painter: QPainter, _option, _widget: QWidget):
        painter.setPen(Qt.NoPen)
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

    def setPos(self, x, y):
        self.proxy.setPos(x, y)
        super().setPos(x, y)
