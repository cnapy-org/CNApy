# QML map view migration notes

This note outlines how `cnapy.gui_elements.map_view.MapView` can be ported from `QGraphicsView` to a Qt Quick scene while keeping the existing Python model and signal API.

## Recommended architecture

1. Keep `MapView` as a compatibility wrapper initially, but make it a `QQuickWidget` or a `QWidget` containing `QQuickWidget` so the rest of `central_widget.py` can still add the map tab as a `QWidget`.
2. Move map state into a Python `QObject` controller, for example `QmlMapController`, with properties for `zoom`, `boxSize`, `background`, `bgSize`, selected reaction ids, and a `QAbstractListModel` of reaction boxes.
3. Expose the controller to QML with `engine.rootContext().setContextProperty("mapController", controller)` or register it with `qmlRegisterType`.
4. Render the map in QML with a `Flickable` for panning, an inner `Item` with a `Scale` transform for zooming, an `Image` for the SVG background, and a `Repeater`/`ListView`-like delegate for reaction boxes.
5. Keep editing and business logic in Python. QML should call controller slots such as `setBoxPosition()`, `setReactionValue()`, `removeBox()`, `maximizeReaction()`, and `minimizeReaction()`, and the controller should emit the same signals currently emitted by `MapView`.

## Mapping the current implementation

| Current `map_view.py` behavior | QML/Qt Quick equivalent |
| --- | --- |
| `QGraphicsView` with `QGraphicsScene` | `QQuickWidget` loading a `MapView.qml` root item |
| Scroll bars storing `project.maps[name]["pos"]` | `Flickable.contentX` and `Flickable.contentY` bound through controller properties |
| `QGraphicsSvgItem` background | QML `Image { source: controller.backgroundUrl; scale: controller.bgSize }` |
| `ReactionBox(QGraphicsItem)` plus `QGraphicsProxyWidget`/`QLineEdit` | QML delegate containing `Rectangle`, `TextInput`, `MouseArea`, and `DragHandler` |
| Rubber-band selection | QML transparent `Rectangle` plus controller hit testing, or `SelectionRectangle` if available in the target Qt version |
| Context `QMenu` on each line edit | QML `Menu` from Qt Quick Controls, calling Python slots |
| `mapChanged`, `reactionValueChanged`, and related signals | Re-emitted by the Python controller to preserve `CentralWidget.connect_map_view_signals()` |

## Minimal Python wrapper sketch

```python
from pathlib import Path

from qtpy.QtCore import QObject, Property, QAbstractListModel, QModelIndex, Qt, Signal, Slot, QUrl
from qtpy.QtQuickWidgets import QQuickWidget
from qtpy.QtWidgets import QWidget, QVBoxLayout


class ReactionBoxModel(QAbstractListModel):
    IdRole = Qt.ItemDataRole.UserRole + 1
    NameRole = IdRole + 1
    XRole = NameRole + 1
    YRole = XRole + 1
    ValueRole = YRole + 1
    ColorRole = ValueRole + 1
    SelectedRole = ColorRole + 1

    def __init__(self, appdata, map_name, parent=None):
        super().__init__(parent)
        self.appdata = appdata
        self.map_name = map_name
        self.ids = list(appdata.project.maps[map_name]["boxes"])

    def roleNames(self):
        return {
            self.IdRole: b"reactionId",
            self.NameRole: b"reactionName",
            self.XRole: b"boxX",
            self.YRole: b"boxY",
            self.ValueRole: b"valueText",
            self.ColorRole: b"boxColor",
            self.SelectedRole: b"selected",
        }

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.ids)

    def data(self, index, role):
        if not index.isValid():
            return None
        reaction_id = self.ids[index.row()]
        boxes = self.appdata.project.maps[self.map_name]["boxes"]
        if role == self.IdRole:
            return reaction_id
        if role == self.XRole:
            return boxes[reaction_id][0]
        if role == self.YRole:
            return boxes[reaction_id][1]
        # Fill name, value, color, and selected state from appdata/project here.
        return None


class QmlMapController(QObject):
    mapChanged = Signal(str)
    reactionValueChanged = Signal(str, str)
    reactionAdded = Signal(str)
    reactionRemoved = Signal(str)
    switchToReactionMask = Signal(str)
    maximizeReaction = Signal(str)
    minimizeReaction = Signal(str)
    setScenValue = Signal(str)

    zoomChanged = Signal()
    boxSizeChanged = Signal()
    backgroundChanged = Signal()

    def __init__(self, appdata, central_widget, name, parent=None):
        super().__init__(parent)
        self.appdata = appdata
        self.central_widget = central_widget
        self.name = name
        self.boxes = ReactionBoxModel(appdata, name, self)

    @Property(QObject, constant=True)
    def reactionBoxes(self):
        return self.boxes

    @Property(float, notify=zoomChanged)
    def zoom(self):
        return self.appdata.project.maps[self.name]["zoom"]

    @Slot(str, float, float)
    def setBoxPosition(self, reaction_id, x, y):
        self.appdata.project.maps[self.name]["boxes"][reaction_id] = (x, y)
        self.mapChanged.emit(reaction_id)

    @Slot(str, str)
    def setReactionValue(self, reaction_id, value):
        # Reuse validate_value() and the existing Python value update path.
        self.reactionValueChanged.emit(reaction_id, value)


class QmlMapView(QWidget):
    def __init__(self, appdata, central_widget, name, parent=None):
        super().__init__(parent)
        self.controller = QmlMapController(appdata, central_widget, name, self)
        self.quick = QQuickWidget(self)
        self.quick.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self.quick.rootContext().setContextProperty("mapController", self.controller)
        self.quick.setSource(QUrl.fromLocalFile(str(Path(__file__).with_name("MapView.qml"))))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.quick)
```

## Minimal QML sketch

```qml
import QtQuick
import QtQuick.Controls

Item {
    id: root
    focus: true

    Flickable {
        id: flick
        anchors.fill: parent
        contentWidth: mapLayer.width * mapLayer.scale
        contentHeight: mapLayer.height * mapLayer.scale
        boundsBehavior: Flickable.StopAtBounds

        Item {
            id: mapLayer
            width: background.implicitWidth
            height: background.implicitHeight
            scale: Math.pow(1.1, mapController.zoom)

            Image {
                id: background
                source: mapController.backgroundUrl
                asynchronous: true
                cache: true
            }

            Repeater {
                model: mapController.reactionBoxes
                delegate: ReactionBoxDelegate {
                    x: boxX
                    y: boxY
                    reactionId: model.reactionId
                    reactionName: model.reactionName
                    valueText: model.valueText
                    selected: model.selected
                    onMoved: (newX, newY) => mapController.setBoxPosition(reactionId, newX, newY)
                    onValueEdited: value => mapController.setReactionValue(reactionId, value)
                }
            }
        }
    }

    WheelHandler {
        acceptedModifiers: Qt.NoModifier
        onWheel: event => mapController.zoomBy(event.angleDelta.y > 0 ? 1 : -1)
    }

    WheelHandler {
        acceptedModifiers: Qt.ControlModifier
        onWheel: event => mapController.scaleBoxes(event.angleDelta.y > 0 ? 1.1 : 1 / 1.1)
    }
}
```

## Migration order

1. Add `QmlMapView` beside the existing `MapView` and keep the old class untouched.
2. Implement the list model and controller signals until `CentralWidget.connect_map_view_signals()` can connect to either implementation.
3. Port only panning, zooming, background, and read-only reaction boxes first.
4. Add editing, selection, context menus, drag-and-drop from the reaction list, and hit testing.
5. Add a feature flag or config option to switch between the existing widget and QML implementation.
6. Benchmark with a large map before deleting the `QGraphicsView` implementation.

## Important caveats

* `QQuickWidget` embeds a Qt Quick scene into a QWidget UI but can incur extra offscreen rendering. For maximum throughput, a full `QQuickView`/`QQuickWindow` architecture is faster, but it is more invasive for the current tab-based QWidget UI.
* A QML `TextInput` is not a `QLineEdit`; validation, focus behavior, and editing history should stay in the Python controller to avoid divergent behavior.
* Qt Quick does not accelerate arbitrary Python painting. The performance win comes from replacing per-item `QPainter`/proxy-widget rendering with QML scene graph items, batched rectangles, text, images, and transforms.
* SVG rendering may still be CPU-bound when initially rasterized. For huge SVG backgrounds, consider pre-rendering tiles or using a cached image texture.
