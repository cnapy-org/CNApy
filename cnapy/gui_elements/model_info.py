"""The model info view"""

from qtpy.QtWidgets import (QLabel, QTextEdit, QVBoxLayout, QWidget)

from cnapy.appdata import AppData


class ModelInfo(QWidget):
    """A widget that shows infos about the model"""

    def __init__(self, appdata: AppData):
        QWidget.__init__(self)
        self.appdata = appdata

        self.layout = QVBoxLayout()
        label = QLabel("Description")
        self.layout.addWidget(label)
        self.description = QTextEdit()
        self.description.setPlaceholderText("Enter a project description")
        self.layout.addWidget(self.description)

        self.setLayout(self.layout)

        self.description.textChanged.connect(
            self.description_changed)

        self.update()

    def update(self):
        if "description" in self.appdata.project.meta_data:
            description = self.appdata.project.meta_data["description"]
        else:
            description = ""

        self.description.textChanged.disconnect(
            self.description_changed)
        self.description.setText(description)

        self.description.textChanged.connect(
            self.description_changed)

    def description_changed(self):
        self.appdata.project.meta_data["description"] = self.description.toPlainText(
        )
        self.appdata.window.unsaved_changes()
