import QtQuick
import QtQuick.Controls

Item {
    id: root

    property string reactionId: ""
    property string reactionName: ""
    property string valueText: ""
    property string fillColor: "#66ffffff"
    property string foregroundColor: "#ff000000"
    property string tooltipText: ""
    property bool selected: false
    signal moved(real newX, real newY)
    signal valueEdited(string value)

    width: mapController.boxWidth * mapController.boxScale
    height: mapController.boxHeight * mapController.boxScale
    scale: mapController.boxScale
    transformOrigin: Item.TopLeft
    visible: mapRoot.acceptsReaction(reactionId, reactionName)

    Rectangle {
        anchors.fill: parent
        color: root.fillColor
        border.color: root.selected ? "#6464c8" : "#666666"
        border.width: root.selected ? 4 : 1
        radius: 2
    }

    TextInput {
        id: valueInput
        anchors.fill: parent
        anchors.margins: 2
        color: root.foregroundColor
        text: root.valueText
        selectByMouse: true
        verticalAlignment: TextInput.AlignVCenter
        font.pointSize: 14
        onEditingFinished: root.valueEdited(text)
        onAccepted: focus = false
    }

    Rectangle {
        x: -15
        y: -15
        width: 20
        height: 20
        radius: 10
        color: "transparent"
        border.color: "#a9a9a9"
        border.width: 1
    }

    Rectangle {
        x: -10
        y: -6
        width: 10
        height: 2
        color: "#a9a9a9"
    }

    Rectangle {
        x: -6
        y: -10
        width: 2
        height: 10
        color: "#a9a9a9"
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        acceptedButtons: Qt.LeftButton | Qt.RightButton
        hoverEnabled: true
        drag.target: root
        onPressed: mouse => {
            if (mouse.button === Qt.LeftButton) {
                mapController.setSelected(root.reactionId, !root.selected || !(mouse.modifiers & (Qt.ControlModifier | Qt.ShiftModifier)), !(mouse.modifiers & (Qt.ControlModifier | Qt.ShiftModifier)))
            } else if (mouse.button === Qt.RightButton) {
                contextMenu.popup()
            }
        }
        onDoubleClicked: mapController.switchToReaction(root.reactionId)
        onReleased: root.moved(root.x, root.y)
    }

    ToolTip.visible: mouseArea.containsMouse
    ToolTip.text: root.tooltipText

    Menu {
        id: contextMenu
        MenuItem { text: "maximize flux for this reaction"; onTriggered: mapController.maximize(root.reactionId) }
        MenuItem { text: "minimize flux for this reaction"; onTriggered: mapController.minimize(root.reactionId) }
        MenuItem { text: "add computed value to scenario"; onTriggered: mapController.useAsScenarioValue(root.reactionId) }
        MenuItem { text: "switch to reaction mask"; onTriggered: mapController.switchToReaction(root.reactionId) }
        MenuSeparator {}
        MenuItem { text: "remove from map"; onTriggered: mapController.removeBox(root.reactionId) }
    }
}
