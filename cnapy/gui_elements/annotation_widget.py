import ast
import webbrowser

from qtpy.QtCore import Qt, Signal, Slot
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QPushButton, QSizePolicy, QTableWidget,
                            QTableWidgetItem, QVBoxLayout, QMessageBox)

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
        self.delete_anno = QPushButton("-")
        self.delete_anno.clicked.connect(self.delete_anno_row)
        lh3.addWidget(self.delete_anno)
        self.open_annotation = QPushButton("Open chosen\nin browser")
        self.open_annotation.clicked.connect(self.open_in_browser)
        lh3.addWidget(self.open_annotation)
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
            annotation_item = self.annotation.item(i, 0)
            if annotation_item is None:
                continue
            key = annotation_item.text()
            if self.annotation.item(i, 1) is None:
                value = ""
            else:
                value = self.annotation.item(i, 1).text()
                if value.startswith("["):
                    try:
                        value = ast.literal_eval(value)
                    except: # if parsing as list does not work keep the raw text
                        pass

            model_element.annotation[key] = value

    def check_in_identifiers_org(self):
        check_in_identifiers_org(self.parent)

    deleteAnnotation = Signal(str)
    def delete_anno_row(self):
        row_to_delete = self.annotation.currentRow()
        try:
            identifier_type = self.annotation.item(row_to_delete, 0).text()
            self.deleteAnnotation.emit(identifier_type)
            self.annotation.removeRow(row_to_delete)
        except AttributeError:
            pass

    def open_in_browser(self):
        current_row = self.annotation.currentRow()
        if current_row >= 0:
            try:
                identifier_type = self.annotation.item(current_row, 0).text()
                identifier_value = self.annotation.item(current_row, 1).text()
            except AttributeError:
                pass
            if identifier_value.startswith("["):
                identifier_value = ast.literal_eval(identifier_value)[0]
            url = f"https://identifiers.org/{identifier_type}:{identifier_value}"
            webbrowser.open_new_tab(url)
        else:
            QMessageBox.information(self.parent, 'Select annotation',
                'Select one of the annotations from the list by clicking on a row.')

    def update_annotations(self, annotation):
        self.annotation.itemChanged.disconnect(
            self.parent.throttler.throttle
        )
        self.annotation.setRowCount(len(annotation))
        self.annotation.clearContents()
        i = 0
        for key, anno in annotation.items():
            keyl = QTableWidgetItem(key)
            iteml = QTableWidgetItem(str(anno))
            self.annotation.setItem(i, 0, keyl)
            self.annotation.setItem(i, 1, iteml)
            i += 1

        self.annotation.itemChanged.connect(
            self.parent.throttler.throttle)
