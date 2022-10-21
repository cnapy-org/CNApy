"""The cnapy clipboard calculator dialog"""
from tkinter.tix import X_REGION
from qtpy.QtWidgets import (QButtonGroup, QComboBox, QDialog, QHBoxLayout, QLabel,
                            QLineEdit, QMessageBox, QPushButton, QRadioButton,
                            QVBoxLayout)

from cnapy.appdata import AppData
# from cnapy.gui_elements.map_view import ReactionBox


class BoxPositionDialog(QDialog):
    """A dialog to perform exact box positioning."""

    def __init__(self, reaction_box, map):
        QDialog.__init__(self)
        self.setWindowTitle("Set reaction box position")

        self.reaction_box = reaction_box
        self.map = map

        self.layout = QVBoxLayout()
        x_label = QLabel("X coordinate (horizontal):")
        hor_x = QHBoxLayout()
        self.x_pos = QLineEdit()
        self.x_pos.setText(str(round(self.reaction_box.x())))
        hor_x.addWidget(x_label)
        hor_x.addWidget(self.x_pos)

        hor_y = QHBoxLayout()
        y_label = QLabel("Y coordinate (vertical):")
        self.y_pos = QLineEdit()
        self.y_pos.setText(str(round(self.reaction_box.y())))
        hor_y.addWidget(y_label)
        hor_y.addWidget(self.y_pos)

        self.layout.addItem(hor_x)
        self.layout.addItem(hor_y)

        hor_buttons = QHBoxLayout()
        self.button = QPushButton("Set position")
        self.close = QPushButton("Close")
        hor_buttons.addWidget(self.button)
        hor_buttons.addWidget(self.close)
        self.layout.addItem(hor_buttons)
        self.setLayout(self.layout)

        # Connecting the signal
        self.close.clicked.connect(self.accept)
        self.button.clicked.connect(self.set_position)

    def set_position(self):
        x_str = self.x_pos.text()
        y_str = self.y_pos.text()

        try:
            x_float = float(x_str)
        except ValueError:
            msgBox = QMessageBox()
            msgBox.setWindowTitle("X position error")
            msgBox.setText("The X value you typed in is no valid number, hence, the new box position could not be set.")
            msgBox.setIcon(QMessageBox.Warning)
            msgBox.exec()
            return

        try:
            y_float = float(y_str)
        except ValueError:
            msgBox = QMessageBox()
            msgBox.setWindowTitle("Y position error")
            msgBox.setText("The Y value you typed in is no valid number, hence, the new box position could not be set.")
            msgBox.setIcon(QMessageBox.Warning)
            msgBox.exec()
            return

        self.map.appdata.project.maps[self.map.name]["boxes"][self.reaction_box.id][0] = x_float
        self.map.appdata.project.maps[self.map.name]["boxes"][self.reaction_box.id][1] = y_float
        self.map.update_reaction(self.reaction_box.id, self.reaction_box.id)
        self.map.central_widget.parent.unsaved_changes()
        self.accept()
