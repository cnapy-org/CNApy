import QtQuick
import QtQuick.Controls

Item {
    id: mapRoot
    objectName: "qmlMapRoot"
    focus: true

    property var filterTerms: []

    function setFilterTerms(terms) {
        filterTerms = terms
    }

    function acceptsReaction(reactionId, reactionName) {
        if (filterTerms.length === 0) {
            return true
        }
        const id = reactionId.toLowerCase()
        const name = reactionName.toLowerCase()
        for (let i = 0; i < filterTerms.length; ++i) {
            if (id.indexOf(filterTerms[i]) !== -1 || name.indexOf(filterTerms[i]) !== -1) {
                return true
            }
        }
        return false
    }

    function mapToMapLayer(x, y) {
        const point = flick.mapToItem(mapLayer, x, y)
        return Qt.point(point.x / mapLayer.scale, point.y / mapLayer.scale)
    }

    function centerOnPoint(x, y) {
        flick.contentX = Math.max(0, x * mapLayer.scale - flick.width / 2)
        flick.contentY = Math.max(0, y * mapLayer.scale - flick.height / 2)
    }

    function fitToView() {
        if (mapLayer.implicitWidth <= 0 || mapLayer.implicitHeight <= 0) {
            return
        }
        const widthScale = flick.width / mapLayer.implicitWidth
        const heightScale = flick.height / mapLayer.implicitHeight
        const target = Math.min(widthScale, heightScale)
        // Keep project zoom integral, matching the existing QGraphicsView semantics.
        let steps = 0
        let factor = 1.0
        while (factor * 1.1 < target) {
            factor *= 1.1
            steps += 1
        }
        while (factor > target) {
            factor /= 1.1
            steps -= 1
        }
        mapController.zoomSteps(steps - Math.round(Math.log(mapController.zoomFactor) / Math.log(1.1)))
        flick.contentX = 0
        flick.contentY = 0
    }

    Flickable {
        id: flick
        anchors.fill: parent
        clip: true
        contentWidth: Math.max(width, mapLayer.implicitWidth * mapLayer.scale)
        contentHeight: Math.max(height, mapLayer.implicitHeight * mapLayer.scale)
        boundsBehavior: Flickable.StopAtBounds
        interactive: true
        Component.onCompleted: {
            contentX = mapController.contentX
            contentY = mapController.contentY
        }
        onContentXChanged: mapController.setViewportPosition(contentX, contentY)
        onContentYChanged: mapController.setViewportPosition(contentX, contentY)

        Item {
            id: mapLayer
            property real implicitWidth: Math.max(background.implicitWidth * mapController.backgroundScale, 2000)
            property real implicitHeight: Math.max(background.implicitHeight * mapController.backgroundScale, 1200)
            width: implicitWidth
            height: implicitHeight
            scale: mapController.zoomFactor
            transformOrigin: Item.TopLeft

            Image {
                id: background
                source: mapController.backgroundUrl
                asynchronous: true
                cache: true
                width: implicitWidth * mapController.backgroundScale
                height: implicitHeight * mapController.backgroundScale
                fillMode: Image.PreserveAspectFit
            }

            Repeater {
                model: mapController.reactionBoxes
                delegate: ReactionBoxDelegate {
                    x: boxX
                    y: boxY
                    reactionId: model.reactionId
                    reactionName: model.reactionName
                    valueText: model.valueText
                    fillColor: model.fillColor
                    foregroundColor: model.foregroundColor
                    selected: model.selected
                    tooltipText: model.tooltipText
                    onMoved: (newX, newY) => mapController.setBoxPosition(reactionId, newX, newY)
                    onValueEdited: value => mapController.setReactionValue(reactionId, value)
                }
            }
        }
    }

    WheelHandler {
        acceptedModifiers: Qt.NoModifier
        onWheel: event => mapController.zoomSteps(event.angleDelta.y > 0 ? 1 : -1)
    }

    WheelHandler {
        acceptedModifiers: Qt.ControlModifier
        onWheel: event => mapController.scaleBoxesBy(event.angleDelta.y > 0 ? 1.1 : 1 / 1.1)
    }
}
