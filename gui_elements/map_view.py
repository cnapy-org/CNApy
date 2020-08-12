"""The PyNetAnalyzer map view"""
from typing import Dict
from cnadata import CnaData
from PySide2.QtGui import QPainter, QDrag, QColor, QPalette, QMouseEvent
from PySide2.QtCore import Qt, QRectF, QMimeData
from PySide2.QtWidgets import (QWidget, QGraphicsItem, QGraphicsScene, QGraphicsView, QLineEdit,
                               QGraphicsSceneDragDropEvent, QGraphicsSceneMouseEvent, QAction, QMenu, QToolTip)
from PySide2.QtSvg import QGraphicsSvgItem
from PySide2.QtCore import Signal

INCREASE_FACTOR = 1.1
DECREASE_FACTOR = 0.9


class MapView(QGraphicsView):
    """A map of reaction boxes"""

    def __init__(self, appdata: CnaData, idx):
        self.scene = QGraphicsScene()
        QGraphicsView.__init__(self, self.scene)
        palette = self.palette()
        palette.setColor(QPalette.Base, Qt.white)
        self.setPalette(palette)

        self.appdata = appdata
        self.idx = idx
        self.setAcceptDrops(True)
        self.drag = False
        self.reaction_boxes: Dict[str, ReactionBox] = {}
        self._zoom = 0
        self.drag = False

        # initial scale
        self._zoom = self.appdata.project.maps[self.idx]["zoom"]
        if self._zoom > 0:
            for i in range(1, self._zoom):
                self.scale(INCREASE_FACTOR, INCREASE_FACTOR)
        if self._zoom < 0:
            for i in range(self._zoom, -1):
                self.scale(DECREASE_FACTOR, DECREASE_FACTOR)

        # connect events to methods
        self.horizontalScrollBar().valueChanged.connect(self.on_hbar_change)
        self.verticalScrollBar().valueChanged.connect(self.on_vbar_change)

    def on_hbar_change(self, x):
        self.appdata.project.maps[self.idx]["pos"] = (
            x, self.verticalScrollBar().value())

    def on_vbar_change(self, y):
        self.appdata.project.maps[self.idx]["pos"] = (
            self.horizontalScrollBar().value(), y)

    def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
        event.setAccepted(True)
        event.accept()
        event.acceptProposedAction()

    def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent):
        event.setAccepted(True)
        point = event.pos()
        point_item = self.mapToScene(point)
        key = event.mimeData().text()
        (_, _, name) = self.appdata.project.maps[self.idx]["boxes"][key]
        self.appdata.project.maps[self.idx]["boxes"][key] = (
            point_item.x(), point_item.y(), name)
        self.update()

    def dragLeaveEvent(self, _event):
        self.update()

    def dropEvent(self, event: QGraphicsSceneDragDropEvent):
        self.drag = False
        point = event.pos()
        point_item = self.mapToScene(point)
        key = event.mimeData().text()
        (_, _, name) = self.appdata.project.maps[self.idx]["boxes"][key]
        self.appdata.project.maps[self.idx]["boxes"][key] = (
            point_item.x(), point_item.y(), name)
        self.update()

    def wheelEvent(self, event):
        if event.angleDelta().y() > 0:
            factor = INCREASE_FACTOR
            self._zoom += 1
        else:
            factor = DECREASE_FACTOR
            self._zoom -= 1

        self.appdata.project.maps[self.idx]["zoom"] = self._zoom
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
        # print("mouse-move")
        if self.drag:
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
            self.translate(1, 1)
        super(MapView, self).mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        # print("mouse-release")
        if self.drag:
            self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
            self.translate(1, 1)
        self.drag = False
        super(MapView, self).mouseReleaseEvent(event)

    def update_selected(self, string):
        print("mapview:update_selected", string)

        for id in self.reaction_boxes:
            if string.lower() in id.lower():
                self.reaction_boxes[id].item.setHidden(False)
            else:
                self.reaction_boxes[id].item.setHidden(True)

    def focus_reaction(self, reaction: str):
        print("mapview:focus_reaction", reaction)
        x = self.appdata.project.maps[self.idx]["boxes"][reaction][0]
        y = self.appdata.project.maps[self.idx]["boxes"][reaction][1]
        self.centerOn(x, y)

    def highlight_reaction(self, string):
        print("mapview:highlight", string)

        # hide other boxes
        # for id in self.reaction_boxes:
        #     self.reaction_boxes[id].item.setHidden(True)

        treffer = self.reaction_boxes[string]
        treffer.item.setHidden(False)

        treffer.set_color(Qt.magenta)

    def update(self):
        print("MapView::update", self.idx)
        self.scene.clear()
        background = QGraphicsSvgItem(
            self.appdata.project.maps[self.idx]["background"])
        background.setFlags(QGraphicsItem.ItemClipsToShape)
        background.setScale(self.appdata.project.maps[self.idx]["bg-size"])
        self.scene.addItem(background)

        for key in self.appdata.project.maps[self.idx]["boxes"]:
            le1 = QLineEdit()
            le1.setMaximumWidth(80)
            le1.setToolTip(
                self.appdata.project.maps[self.idx]["boxes"][key][2])
            proxy1 = self.scene.addWidget(le1)
            proxy1.show()
            ler1 = ReactionBox(self, proxy1, le1, key)
            ler1.setPos(self.appdata.project.maps[self.idx]["boxes"][key]
                        [0], self.appdata.project.maps[self.idx]["boxes"][key][1])
            self.scene.addItem(ler1)
            self.reaction_boxes[key] = ler1

        self.set_values()

        # set scrollbars

        self.horizontalScrollBar().setValue(
            self.appdata.project.maps[self.idx]["pos"][0])
        self.verticalScrollBar().setValue(
            self.appdata.project.maps[self.idx]["pos"][1])

    def set_values(self):

        for key in self.appdata.project.maps[self.idx]["boxes"]:
            if key in self.appdata.project.scen_values.keys():
                self.reaction_boxes[key].set_val_and_color(
                    self.appdata.project.scen_values[key])
            elif key in self.appdata.project.comp_values.keys():
                self.reaction_boxes[key].set_val_and_color(
                    self.appdata.project.comp_values[key])

    # def recolor_all(self):
    #     for key in self.appdata.project.maps[self.idx]["boxes"]:
    #         self.reaction_boxes[key].recolor()

    def delete_box(self, key):
        # print("MapView::delete_box", key)
        del self.appdata.project.maps[self.idx]["boxes"][key]
        self.update()

    def emit_doubleClickedReaction(self, reaction: str):
        print("emit_doubleClickedReaction")
        self.doubleClickedReaction.emit(reaction)

    def value_changed(self, reaction: str, value: str):
        print("emit_value_changed")
        self.reactionValueChanged.emit(reaction, value)
        self.reaction_boxes[reaction].recolor()
        # self.recolor_all()

    doubleClickedReaction = Signal(str)
    reactionValueChanged = Signal(str, str)


class ReactionBox(QGraphicsItem):
    """Handle to the line edits on the map"""

    def __init__(self, parent: MapView, proxy, item: QLineEdit, key: int):
        QGraphicsItem.__init__(self)

        self.map = parent
        self.key = key
        self.proxy = proxy
        self.item = item

        palette = self.item.palette()
        palette.setColor(QPalette.Base, self.map.appdata.Defaultcolor)
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
        self.popMenu = QMenu(parent)
        delete_action = QAction('remove from map', parent)
        self.popMenu.addAction(delete_action)
        delete_action.triggered.connect(self.delete)
        self.popMenu.addSeparator()

    def returnPressed(self):
        print(self.key, "return pressed to", self.item.text())
        if verify_value(self.item.text()):
            self.map.value_changed(self.key, self.item.text())

        # TODO: actually I want to repaint not scale
        self.map.scale(2, 2)
        self.map.scale(0.5, 0.5)

    def value_changed(self):
        print(self.key, "value changed to", self.item.text())
        test = self.item.text().replace(" ", "")
        if test == "":
            self.map.value_changed(self.key, test)
            self.set_color(self.map.appdata.Defaultcolor)
        elif verify_value(self.item.text()):
            self.map.value_changed(self.key, self.item.text())
            if self.key in self.map.appdata.project.scen_values.keys():
                self.set_color(self.map.appdata.Scencolor)
            else:
                self.set_color(self.map.appdata.Compcolor)
        else:
            self.set_color(Qt.magenta)

        # TODO: actually I want to repaint not scale
        self.map.scale(2, 2)
        self.map.scale(0.5, 0.5)

    def set_val_and_color(self, value):
        self.set_value(value)
        self.recolor()
        # if self.key in self.map.appdata.project.scen_values.keys():
        #     self.set_color(self.map.appdata.Scencolor)
        # else:
        #     self.set_color(self.map.appdata.Compcolor)

    def set_value(self, value):
        self.item.setText(str(value))
        self.item.setCursorPosition(0)

    def recolor(self):
        print("in recolor")
        test = self.item.text().replace(" ", "")
        if test == "":
            self.set_color(self.map.appdata.Defaultcolor)
        elif verify_value(self.item.text()):
            if self.key in self.map.appdata.project.scen_values.keys():

                # Here we continue
                # We differentiate special cases like (vl==vh)

                self.set_color(self.map.appdata.Scencolor)
            else:
                # We differentiate special cases like (vl==vh)

                print("set Compcolor")
                self.set_color(self.map.appdata.Compcolor)
        else:
            self.set_color(Qt.magenta)

    def set_color(self, color: QColor):
        palette = self.item.palette()
        palette.setColor(QPalette.Base, color)
        role = self.item.foregroundRole()
        palette.setColor(role, Qt.black)
        self.item.setPalette(palette)

    def boundingRect(self):
        return QRectF(-15, -15, 20, 20)

    def paint(self, painter: QPainter, option, widget: QWidget):
        # painter.setPen(Qt.NoPen)
        # set color depending on wether the value belongs to the scenario
        if self.key in self.map.appdata.project.scen_values.keys():
            painter.setPen(Qt.magenta)
        else:
            # painter.setBrush(Qt.darkGray)
            painter.setPen(Qt.darkGray)

        # painter.drawEllipse(-8, -8, 10, 10)
        painter.drawLine(-5, 0, -5, -10)
        painter.drawLine(0, -5, -10,  -5)

    def mousePressEvent(self, _event: QGraphicsSceneMouseEvent):
        print("mousePressedEvent")
        pass

    def mouseReleaseEvent(self, _event: QGraphicsSceneMouseEvent):
        print("mouseReleaseEvent")
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
        print("double_clickEvent")
        self.map.emit_doubleClickedReaction(str(self.key))

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
    from ast import literal_eval as make_tuple
    try:
        x = float(value)
    except:
        try:
            (vl, vh) = make_tuple(value)
            if not isinstance(vl, float):
                return False
            if not isinstance(vh, float):
                return False
        except:
            return False
        else:
            return True
    else:
        return True
