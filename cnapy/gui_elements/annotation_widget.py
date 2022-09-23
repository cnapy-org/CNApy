from qtpy.QtCore import Qt, Signal, Slot
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import QHBoxLayout, QHeaderView, QLabel, QPushButton, QSizePolicy, QTableWidget, QTableWidgetItem, QVBoxLayout

from cnapy.utils_for_cnapy_api import check_in_identifiers_org


class AnnotationWidget(QVBoxLayout):
    def __init__(self, parent):
        super().__init__()
        self.parent = parent

        lh = QHBoxLayout()
        label = QLabel("Annotations:")
        lh.addWidget(label)

        check_button = QPushButton("identifiers.org check")
        check_button.setIcon(QIcon.fromTheme("list-add"))
        policy = QSizePolicy()
        policy.ShrinkFlag = True
        check_button.setSizePolicy(policy)
        check_button.clicked.connect(self.check_in_identifiers_org)
        lh.addWidget(check_button)
        self.addItem(lh)

        lh2 = QHBoxLayout()
        self.annotation = QTableWidget(0, 2)
        self.annotation.setHorizontalHeaderLabels(
            ["key", "value"])
        self.annotation.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lh2.addWidget(self.annotation)

        lh3 = QVBoxLayout()
        self.add_anno = QPushButton("+")
        self.add_anno.clicked.connect(self.add_anno_row)
        lh3.addWidget(self.add_anno)
        self.add_anno = QPushButton("-")
        self.add_anno.clicked.connect(self.delete_anno_row)
        lh3.addWidget(self.add_anno)
        lh2.addItem(lh3)
        self.addItem(lh2)

        self.annotation.itemChanged.connect(parent.throttler.throttle)

    def add_anno_row(self):
        i = self.annotation.rowCount()
        self.annotation.insertRow(i)

    def apply_annotation(self, model_element):
        model_element.annotation = {}
        rows = self.annotation.rowCount()
        for i in range(0, rows):
            key = self.annotation.item(i, 0).text()
            if self.annotation.item(i, 1) is None:
                value = ""
            else:
                value = self.annotation.item(i, 1).text()

            model_element.annotation[key] = value

    def check_in_identifiers_org(self):
        check_in_identifiers_org(self.parent)

    deleteAnnotation = Signal(int)
    def delete_anno_row(self):
        row_to_delete = self.annotation.currentRow()
        self.annotation.removeRow(row_to_delete)
        self.deleteAnnotation.emit(row_to_delete)

    def update_annotations(self, annotation):
        self.annotation.itemChanged.disconnect(
            self.parent.throttler.throttle
        )
        c = self.annotation.rowCount()
        for i in range(0, c):
            self.annotation.removeRow(0)
        i = 0
        for key in annotation:
            self.annotation.insertRow(i)
            keyl = QTableWidgetItem(key)
            iteml = QTableWidgetItem(str(annotation[key]))
            self.annotation.setItem(i, 0, keyl)
            self.annotation.setItem(i, 1, iteml)
            i += 1

        self.annotation.itemChanged.connect(
            self.parent.throttler.throttle)
