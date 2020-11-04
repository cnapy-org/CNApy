"""The PyNetAnalyzer metabolite list"""
import cobra
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                            QMessageBox, QPushButton, QSplitter,
                            QTableWidget, QTableWidgetItem, QTreeWidget,
                            QTreeWidgetItem, QVBoxLayout, QWidget)

from cnapy.cnadata import CnaData


class MetaboliteList(QWidget):
    """A list of metabolites"""

    def __init__(self, appdata: CnaData):
        QWidget.__init__(self)
        self.appdata = appdata
        self.last_selected = None

        self.metabolite_list = QTreeWidget()
        # self.metabolite_list.setHeaderLabels(["Name", "Reversible"])
        self.metabolite_list.setHeaderLabels(["Id", "Name"])
        self.metabolite_list.setSortingEnabled(True)

        for r in self.appdata.project.cobra_py_model.metabolites:
            self.add_metabolites(r)

        self.metabolites_mask = metabolitesMask(appdata)
        self.metabolites_mask.hide()

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.splitter = QSplitter()
        self.splitter.setOrientation(Qt.Vertical)
        self.splitter.addWidget(self.metabolite_list)
        self.splitter.addWidget(self.metabolites_mask)
        self.layout.addWidget(self.splitter)
        self.setLayout(self.layout)

        self.metabolite_list.currentItemChanged.connect(
            self.metabolites_selected)
        self.metabolites_mask.changedMetaboliteList.connect(
            self.emit_changedModel)

    def clear(self):
        self.metabolite_list.clear()
        self.metabolites_mask.hide()

    def add_metabolites(self, metabolites):
        item = QTreeWidgetItem(self.metabolite_list)
        item.setText(0, metabolites.id)
        item.setText(1, metabolites.name)
        item.setData(2, 0, metabolites)

    def update_annotations(self, annotation):

        self.metabolites_mask.annotation.itemChanged.disconnect(
            self.metabolites_mask.metabolites_data_changed)
        c = self.metabolites_mask.annotation.rowCount()
        for i in range(0, c):
            self.metabolites_mask.annotation.removeRow(0)
        i = 0
        for key in annotation:
            self.metabolites_mask.annotation.insertRow(i)
            keyl = QTableWidgetItem(key)
            iteml = QTableWidgetItem(str(annotation[key]))
            self.metabolites_mask.annotation.setItem(i, 0, keyl)
            self.metabolites_mask.annotation.setItem(i, 1, iteml)
            i += 1

        self.metabolites_mask.annotation.itemChanged.connect(
            self.metabolites_mask.metabolites_data_changed)

    def emit_changedModel(self):
        self.last_selected = self.metabolites_mask.id.text()
        self.changedModel.emit()

    def update_selected(self, string):
        print("metabolite_list:update_selected", string)
        root = self.metabolite_list.invisibleRootItem()
        child_count = root.childCount()
        for i in range(child_count):
            item = root.child(i)
            item.setHidden(True)

        for item in self.metabolite_list.findItems(string, Qt.MatchContains, 0):
            item.setHidden(False)
        for item in self.metabolite_list.findItems(string, Qt.MatchContains, 1):
            item.setHidden(False)

    def metabolites_selected(self, item, _column):
        # print("metabolites_selected")
        if item is None:
            self.metabolites_mask.hide()
        else:
            self.metabolites_mask.show()
            metabolites: cobra.Metabolite = item.data(2, 0)
            self.metabolites_mask.id.setText(metabolites.id)
            self.metabolites_mask.name.setText(metabolites.name)
            self.metabolites_mask.formula.setText(metabolites.formula)
            self.metabolites_mask.charge.setText(str(metabolites.charge))
            self.metabolites_mask.compartment.setText(metabolites.compartment)
            self.update_annotations(metabolites.annotation)
            self.metabolites_mask.old = metabolites
            self.metabolites_mask.changed = False
            self.metabolites_mask.update_state()

    def update(self):
        # print("MetaboliteList::update")
        self.metabolite_list.clear()
        for m in self.appdata.project.cobra_py_model.metabolites:
            self.add_metabolites(m)

        if self.last_selected is None:
            pass
        else:
            # print("something was previosly selected")
            items = self.metabolite_list.findItems(
                self.last_selected, Qt.MatchExactly)

            for i in items:
                self.metabolite_list.setCurrentItem(i)
                print(i.text(0))
                break

    def setCurrentItem(self, key):
        self.last_selected = key
        self.update()

    itemActivated = Signal(str)
    changedModel = Signal()


class metabolitesMask(QWidget):
    """The input mask for a metabolites"""

    def __init__(self, appdata):
        QWidget.__init__(self)
        self.appdata = appdata
        self.old = None
        self.is_valid = True
        self.changed = False
        layout = QVBoxLayout()
        l = QHBoxLayout()
        label = QLabel("Id:")
        self.id = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.id)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Name:")
        self.name = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.name)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Formula:")
        self.formula = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.formula)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Charge:")
        self.charge = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.charge)
        layout.addItem(l)

        l = QHBoxLayout()
        label = QLabel("Compartment:")
        self.compartment = QLineEdit()
        l.addWidget(label)
        l.addWidget(self.compartment)
        layout.addItem(l)

        l = QVBoxLayout()
        label = QLabel("Annotations:")
        l.addWidget(label)
        l2 = QHBoxLayout()
        self.annotation = QTableWidget(0, 2)
        self.annotation.setHorizontalHeaderLabels(
            ["key", "value"])
        self.annotation.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        l2.addWidget(self.annotation)

        self.add_anno = QPushButton("+")
        self.add_anno.clicked.connect(self.add_anno_row)
        l2.addWidget(self.add_anno)
        l.addItem(l2)
        layout.addItem(l)

        l = QHBoxLayout()
        self.apply_button = QPushButton("apply changes")

        l.addWidget(self.apply_button)
        layout.addItem(l)

        self.setLayout(layout)

        self.id.textEdited.connect(self.metabolites_data_changed)
        self.name.textEdited.connect(self.metabolites_data_changed)
        self.formula.textEdited.connect(self.metabolites_data_changed)
        self.charge.textEdited.connect(self.metabolites_data_changed)
        self.compartment.textEdited.connect(self.metabolites_data_changed)
        self.annotation.itemChanged.connect(self.metabolites_data_changed)
        self.apply_button.clicked.connect(self.apply)
        self.update_state()

    def add_anno_row(self):
        i = self.annotation.rowCount()
        self.annotation.insertRow(i)
        self.changed = True

    def apply(self):
        if self.old is None:
            self.old = cobra.metabolites(
                id=self.id.text())
            self.appdata.project.cobra_py_model.add_metabolites(self.old)
        try:
            self.old.id = self.id.text()
        except:
            msgBox = QMessageBox()
            msgBox.setText("Could not apply changes identifier already used.")
            msgBox.exec()
            pass
        else:
            self.old.name = self.name.text()
            self.old.formula = self.formula.text()
            self.old.charge = int(self.charge.text())
            self.old.compartment = self.compartment.text()
            self.old.annotation = {}
            rows = self.annotation.rowCount()
            for i in range(0, rows):
                key = self.annotation.item(i, 0).text()
                value = self.annotation.item(i, 1).text()
                print(key, value)
                self.old.annotation[key] = value

            self.changed = False
            self.changedMetaboliteList.emit()

    def verify_id(self):
        # print("metabolitesMask::verify_id")
        palette = self.id.palette()
        role = self.id.foregroundRole()
        palette.setColor(role, Qt.black)
        self.id.setPalette(palette)

        with self.appdata.project.cobra_py_model as model:
            try:
                m = cobra.Metabolite(id=self.id.text())
                model.add_metabolites([m])
            except:
                self.id.setStyleSheet("background: #ff9999")
                return False
            else:
                self.id.setStyleSheet("background: white")
                return True

    def verify_name(self):
        # print("metabolitesMask::verify_name")
        palette = self.name.palette()
        role = self.name.foregroundRole()
        palette.setColor(role, Qt.black)
        self.name.setPalette(palette)

        with self.appdata.project.cobra_py_model as model:
            try:
                m = cobra.Metabolite(id="test_id", name=self.name.text())
                model.add_metabolites([m])
            except:
                self.name.setStyleSheet("background: #ff9999")
                return False
            else:
                self.name.setStyleSheet("background: white")
                return True

    def verify_formula(self):

        self.formula.setStyleSheet("background: white")
        palette = self.formula.palette()
        role = self.formula.foregroundRole()
        palette.setColor(role, Qt.black)
        self.formula.setPalette(palette)
        return True

    def verify_charge(self):

        palette = self.charge.palette()
        role = self.charge.foregroundRole()
        palette.setColor(role, Qt.black)
        self.charge.setPalette(palette)
        try:
            x = int(self.charge.text())
        except:
            self.charge.setStyleSheet("background: #ff9999")
            return False
        else:
            self.charge.setStyleSheet("background: white")
            return True

    def verify_compartment(self):

        palette = self.compartment.palette()
        role = self.compartment.foregroundRole()
        palette.setColor(role, Qt.black)
        self.compartment.setPalette(palette)

        try:
            m = cobra.Metabolite(id="test_id", name=self.compartment.text())
        except:
            self.compartment.setStyleSheet("background: #ff9999")
            return False
        else:
            self.compartment.setStyleSheet("background: white")
            return True

    def verify_mask(self):
        if self.verify_id() & self.verify_name() & self.verify_formula() & self.verify_charge() & self.verify_compartment():
            self.is_valid = True
        else:
            self.is_valid = False

    def metabolites_data_changed(self):
        self.changed = True
        self.verify_mask()
        self.update_state()

    def update_state(self):
        # print("metabolitesMask::update_state")
        if self.old is None:
            pass
        else:
            if self.is_valid & self.changed:
                self.apply_button.setEnabled(True)
            else:
                self.apply_button.setEnabled(False)

    changedMetaboliteList = Signal()
