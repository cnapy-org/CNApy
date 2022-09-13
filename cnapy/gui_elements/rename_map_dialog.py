"""The rename map dialog"""
from qtpy.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                            QPushButton, QVBoxLayout)
from cnapy.appdata import AppData


class RenameMapDialog(QDialog):
    """A dialog to rename maps"""

    def __init__(self, appdata: AppData, central_widget):
        QDialog.__init__(self)
        self.setWindowTitle("Rename map")

        self.appdata = appdata
        self.central_widget = central_widget
        self.layout = QVBoxLayout()
        h1 = QHBoxLayout()
        label = QLabel("Enter new map name")
        self.layout.addWidget(label)
        self.idx = self.central_widget.map_tabs.currentIndex()
        self.old_name = self.central_widget.map_tabs.tabText(self.idx)

        self.name_field = QLineEdit(self.old_name)
        h1.addWidget(self.name_field)
        self.layout.addItem(h1)

        l2 = QHBoxLayout()
        self.button = QPushButton("Rename")
        self.cancel = QPushButton("Cancel")
        l2.addWidget(self.button)
        l2.addWidget(self.cancel)
        self.layout.addItem(l2)
        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.apply)

    def apply(self):
        new_name = self.name_field.text()
        if not new_name in self.appdata.project.maps.keys():
            self.appdata.project.maps[new_name] = self.appdata.project.maps.pop(
                self.old_name)
            self.central_widget.map_tabs.setTabText(self.idx, new_name)
            m = self.central_widget.map_tabs.widget(self.idx)
            m.name = new_name
            self.central_widget.parent.unsaved_changes()
        self.accept()
