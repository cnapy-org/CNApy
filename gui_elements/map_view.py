"""The PyNetAnalyzer map view"""
from PySide2.QtGui import QPainter, QDrag
from PySide2.QtCore import Qt, QRectF, QMimeData
from PySide2.QtWidgets import (QWidget, QGraphicsItem, QGraphicsScene, QGraphicsView, QLineEdit,
                               QGraphicsSceneDragDropEvent, QGraphicsSceneMouseEvent)


class MapView(QGraphicsView):
    """A map of reaction boxes"""

    def __init__(self, scene: QGraphicsScene):
        QGraphicsView.__init__(self, scene)
        self.setAcceptDrops(True)
        self.drag_over = False
        self.reaction_boxes = {}

    def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
        event.setAccepted(True)
        event.accept()
        event.acceptProposedAction()
        self.drag_over = True

    def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent):
        # print("dragMoveEvent")
        event.setAccepted(True)
        point = event.pos()
        point_item = self.mapToScene(point)
        key = event.mimeData().text()
        self.reaction_boxes[key].setPos(point_item.x(), point_item.y())
        self.update()

    def dragLeaveEvent(self, _event):
        self.drag_over = False
        self.update()

    def dropEvent(self, event: QGraphicsSceneDragDropEvent):
        self.drag_over = False
        point = event.pos()
        point_item = self.mapToScene(point)
        key = event.mimeData().text()
        self.reaction_boxes[key].setPos(point_item.x(), point_item.y())
        self.update()


class ReactionBox(QGraphicsItem):
    """Handle to the line edits on the map"""

    def __init__(self, item: QLineEdit, key: int):
        self.key = key
        self.item = item
        QGraphicsItem.__init__(self)
        self.setCursor(Qt.OpenHandCursor)
        self.setAcceptedMouseButtons(Qt.LeftButton)

    def boundingRect(self):
        return QRectF(-15, -15, 20, 20)

    def paint(self, painter: QPainter, _option, _widget: QWidget):
        # pass
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.darkGray)
        painter.drawEllipse(-12, -12, 15, 15)
        # painter.drawEllipse(-12, -12, 20, 20)
        # painter.setPen(QPen(Qt.black, 1))
        # painter.setBrush(QBrush(Qt.blue))
        # painter.drawEllipse(-15, -15, 20, 20)
        # self.item.show()
        # bool drag_over = false;};

    def mousePressEvent(self, _event: QGraphicsSceneMouseEvent):
        pass

    def mouseReleaseEvent(self, _event: QGraphicsSceneMouseEvent):
        pass

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        # print("mouseMoveEvent")
        drag = QDrag(event.widget())
        mime = QMimeData()
        mime.setText(str(self.key))
        drag.setMimeData(mime)
        # self.setCursor(Qt.ClosedHandCursor)
        drag.exec_()
        # self.setCursor(Qt.OpenHandCursor)

    def setPos(self, x, y):
        self.item.setPos(x, y)
        super().setPos(x, y)
