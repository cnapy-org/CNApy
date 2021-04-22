"""A dialog to edit project description"""
from qtpy.QtWidgets import (QDialog, QHBoxLayout, QPushButton, QTextEdit,
                            QVBoxLayout)

from cnapy.cnadata import CnaData


class DescriptionDialog(QDialog):
    """A dialog to edit project description"""

    def __init__(self, appdata: CnaData):
        QDialog.__init__(self)
        self.setWindowTitle("Project description")

        self.appdata = appdata
        self.layout = QVBoxLayout()
        h1 = QHBoxLayout()
        self.description = QTextEdit()
        self.description.setPlaceholderText("Enter a project description")
        h1.addWidget(self.description)
        self.layout.addItem(h1)

        l2 = QHBoxLayout()
        self.button = QPushButton("Apply")
        self.cancel = QPushButton("Cancel")
        l2.addWidget(self.button)
        l2.addWidget(self.cancel)
        self.layout.addItem(l2)
        self.setLayout(self.layout)

        if "description" in self.appdata.project.meta_data:
            self.description.append(
                self.appdata.project.meta_data["description"])

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.apply)

    def apply(self):

        self.appdata.project.meta_data["description"] = self.description.toPlainText(
        )
        self.appdata.window.unsaved_changes()
        self.accept()
