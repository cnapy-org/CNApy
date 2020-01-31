#!/usr/bin/env python3
#
# Copyright 2019 PSB & ST
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""""""

from PySide2.QtGui import QPainter, QDrag, QPen, QBrush
from PySide2.QtCore import Slot, Qt, QRectF, QMimeData
import os
from libsbml import readSBMLFromFile
import sys
from PySide2.QtWidgets import (QMainWindow, QAction, QApplication, QLabel, QPushButton, QTreeWidget, QTreeWidgetItem, QHBoxLayout, QVBoxLayout,
                               QWidget, QFileDialog, QTabWidget, QGraphicsItem, QGraphicsScene, QGraphicsView, QLineEdit, QGraphicsSceneDragDropEvent, QGraphicsObject, QGraphicsSceneMouseEvent)


# Internal modules
from gui_elements.about_dialog import AboutDialog


class MyView(QGraphicsView):
    def __init__(self, scene: QGraphicsScene):
        QGraphicsView.__init__(self, scene)
        self.setAcceptDrops(True)
        self.dragOver = False
        self.reaction_box = None

    def dragEnterEvent(self, event: QGraphicsSceneDragDropEvent):
        print("dragEnterEvent")
        event.setAccepted(True)
        event.accept()
        event.acceptProposedAction()
        self.dragOver = True
        # self.update()

    def dragMoveEvent(self, event: QGraphicsSceneDragDropEvent):
        # print("dragMoveEvent")
        event.setAccepted(True)
        point = event.pos()
        point_item = self.mapToScene(point)
        self.reaction_box.setPos(point_item)
        self.update()

    def dragLeaveEvent(self, event):
        print("dragLeaveEvent")
        self.dragOver = False
        self.update()

    def dropEvent(self, event: QGraphicsSceneDragDropEvent):
        print("dropEvent")
        self.dragOver = False
        point = event.pos()
        point_item = self.mapToScene(point)
        self.reaction_box.setPos(point_item)
        self.update()


class ReactionBox(QGraphicsItem):
    def __init__(self, item: QLineEdit):
        self.item = item
        QGraphicsItem.__init__(self)
        self.setCursor(Qt.OpenHandCursor)
        self.setAcceptedMouseButtons(Qt.LeftButton)

    def boundingRect(self):
        return QRectF(-15.5, -15.5, 34, 34)

    def paint(self, painter: QPainter, option, widget: QWidget):
        painter.setPen(Qt.NoPen)
        painter.setBrush(Qt.darkGray)
        painter.drawEllipse(-12, -12, 30, 30)
        painter.setPen(QPen(Qt.black, 1))
        painter.setBrush(QBrush(Qt.blue))
        painter.drawEllipse(-15, -15, 30, 30)
        # self.item.show()
        # bool dragOver = false;};

    def mousePressEvent(self, event: QGraphicsSceneMouseEvent):
        print("mousePressEvent")
        # self.setCursor(Qt.ClosedHandCursor)

    def mouseReleaseEvent(self, event: QGraphicsSceneMouseEvent):
        print("mouseReleaseEvent")
        # self.setCursor(Qt.OpenHandCursor)

    def mouseMoveEvent(self, event: QGraphicsSceneMouseEvent):
        print("mouseMoveEvent")
        drag = QDrag(event.widget())
        mime = QMimeData()
        drag.setMimeData(mime)
        # self.setCursor(Qt.ClosedHandCursor)
        drag.exec_()
        # self.setCursor(Qt.OpenHandCursor)


class PnaData:
    def __init__(self):
        self.reactions = []
        self.species = []


class Reaction:
    def __init__(self, name):
        self.name = name
        self.reversible = True


class Specie:
    def __init__(self, name):
        self.name = name


class CentralWidget(QWidget):
    def __init__(self):
        QWidget.__init__(self)
        tabs = QTabWidget()
        self.reaction_list = QTreeWidget()
        self.reaction_list.setHeaderLabels(["Name", "Reversible"])
        self.reaction_list.setSortingEnabled(True)
        self.specie_list = QTreeWidget()
        self.specie_list.setHeaderLabels(["Name"])
        self.specie_list.setSortingEnabled(True)
        tabs.addTab(self.reaction_list, "Reactions")
        tabs.addTab(self.specie_list, "Species")

        self.scene = QGraphicsScene()
        # self.view = QGraphicsView(self.scene)
        self.view = MyView(self.scene)
        self.view.show()
        tabs.addTab(self.view, "Map")

        layout = QHBoxLayout()
        layout.addWidget(tabs)
        self.setLayout(layout)


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.setWindowTitle("PyNetAnalyzer")

        # Data
        self.data = PnaData()

        # CentralWidget
        central_widget = CentralWidget()
        self.setCentralWidget(central_widget)

        self.centralWidget().reaction_list.itemActivated.connect(self.reaction_selected)

        # Menu
        self.menu = self.menuBar()
        self.file_menu = self.menu.addMenu("File")

        new_project_action = QAction("New project...", self)
        self.file_menu.addAction(new_project_action)

        open_project_action = QAction("Open project...", self)
        self.file_menu.addAction(open_project_action)
        open_project_action.triggered.connect(self.open_project)

        save_project_action = QAction("Save project...", self)
        self.file_menu.addAction(save_project_action)

        save_as_project_action = QAction("Save project as...", self)
        self.file_menu.addAction(save_as_project_action)

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        self.file_menu.addAction(exit_action)
        exit_action.triggered.connect(self.exit_app)

        self.edit_menu = self.menu.addMenu("Edit")
        network_compose_action = QAction("Network composer...", self)
        self.edit_menu.addAction(network_compose_action)

        self.find_menu = self.menu.addMenu("Find")
        find_reaction_action = QAction("Find reaction...", self)
        self.find_menu.addAction(find_reaction_action)

        self.analysis_menu = self.menu.addMenu("Analysis")
        fba_action = QAction("Flux Balance Analysis (FBA)...", self)
        self.analysis_menu.addAction(fba_action)
        fva_action = QAction("Flux Variability Analysis (FVA)...", self)
        self.analysis_menu.addAction(fva_action)

        self.help_menu = self.menu.addMenu("Help")
        about_action = QAction("About PyNetAnalyzer...", self)
        self.help_menu.addAction(about_action)
        about_action.triggered.connect(self.show_about)

    @Slot()
    def exit_app(self, checked):
        QApplication.quit()

    @Slot()
    def show_about(self, checked):
        dialog = AboutDialog()
        dialog.exec_()

    @Slot()
    def open_project(self, checked):
        dialog = QFileDialog(self)
        filename: str = dialog.getOpenFileName(dir=os.getcwd(), filter="*.xml")
        print(filename)
        doc = readSBMLFromFile(filename[0])
        # if doc.getNumErrors() > 0:
        #     messagebox.showerror("Error", "could not read "+filename )

        model = doc.getModel()

        self.data.reactions = []
        for r in model.getListOfReactions():
            reaction = Reaction(r.getName())
            reaction.reversible = r.getReversible()
            self.data.reactions.append(reaction)

        for s in model.getListOfSpecies():
            specie = Specie(s.getName())
            self.data.species.append(specie)

        self.update_view()

    def reaction_selected(self, item, column):
        print("something something itemActivated", item, column)
        print(item.data(2, 0).name)

    def update_view(self):
        self.centralWidget().reaction_list.clear()
        for r in self.data.reactions:
            item = QTreeWidgetItem(self.centralWidget().reaction_list)
            item.setText(0, r.name)
            item.setText(1, str(r.reversible))
            item.setData(2, 0, r)

        self.centralWidget().specie_list.clear()
        for s in self.data.species:
            item = QTreeWidgetItem(self.centralWidget().specie_list)
            item.setText(0, s.name)

        # draw a map
        scene = self.centralWidget().scene
        scene.addText("Hello, what!")
        view = self.centralWidget().view
        view.setAcceptDrops(True)
        le = QLineEdit()
        ler = ReactionBox(le)
        view.reaction_box = ler
        ler.setPos(100, 100)
        scene.addItem(ler)
        proxy = scene.addWidget(le)
        # item->setParentItem(anOtherItem);
        proxy.setPos(100, 100)
        proxy.show()
        le.show()


if __name__ == "__main__":
    # Qt Application
    app = QApplication(sys.argv)

    window = MainWindow()
    window.resize(800, 600)
    window.show()

    # Execute application
    sys.exit(app.exec_())
