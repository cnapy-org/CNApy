"""The PyNetAnalyzer species list"""
import cobra
from PySide2.QtCore import Qt, Signal
from PySide2.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QTreeWidget, QTreeWidgetItem,
                               QVBoxLayout, QWidget)

from cnapy.cnadata import CnaData


class SpeciesList(QWidget):
    """A list of species"""

    def __init__(self, appdata: CnaData):
        QWidget.__init__(self)
        self.appdata = appdata

        self.species_list = QTreeWidget()
        # self.species_list.setHeaderLabels(["Name", "Reversible"])
        self.species_list.setHeaderLabels(["Id", "Name"])
        self.species_list.setSortingEnabled(True)

        for r in self.appdata.project.cobra_py_model.metabolites:
            self.add_species(r)

        self.species_mask = SpeciesMask(appdata)
        self.species_mask.hide()

        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.layout.addWidget(self.species_list)
        self.layout.addWidget(self.species_mask)
        self.setLayout(self.layout)

        self.species_list.currentItemChanged.connect(self.species_selected)
        self.species_mask.changedspeciesList.connect(self.emit_changedModel)

    def clear(self):
        self.species_list.clear()
        self.species_mask.hide()

    def add_species(self, species):
        item = QTreeWidgetItem(self.species_list)
        item.setText(0, species.id)
        item.setText(1, species.name)
        item.setData(2, 0, species)

    def emit_changedModel(self):
        self.changedModel.emit()

    def species_selected(self, item, _column):
        # print("species_selected")
        if item is None:
            self.species_mask.hide()
        else:
            self.species_mask.show()
            species: cobra.Metabolite = item.data(2, 0)
            self.species_mask.id.setText(species.id)
            self.species_mask.name.setText(species.name)
            self.species_mask.formula.setText(species.formula)
            self.species_mask.charge.setText(str(species.charge))
            self.species_mask.compartment.setText(species.compartment)

            self.species_mask.old = species
            self.species_mask.changed = False
            self.species_mask.update_state()

    def update(self):
        # print("SpeciesList::update")
        self.species_list.clear()
        for m in self.appdata.project.cobra_py_model.metabolites:
            self.add_species(m)

    itemActivated = Signal(str)
    changedModel = Signal()


class SpeciesMask(QWidget):
    """The input mask for a species"""

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

        # l = QVBoxLayout()
        # label = QLabel("Notes and Comments:")
        # self.comments = QTextEdit()
        # self.comments.setFixedHeight(200)
        # l.addWidget(label)
        # l.addWidget(self.comments)
        # layout.addItem(l)

        l = QHBoxLayout()
        self.apply_button = QPushButton("apply changes")
        self.apply_button.setEnabled(False)

        l.addWidget(self.apply_button)
        layout.addItem(l)

        self.setLayout(layout)

        self.id.textEdited.connect(self.species_data_changed)
        self.name.textEdited.connect(self.species_data_changed)
        self.formula.textEdited.connect(self.species_data_changed)
        self.charge.textEdited.connect(self.species_data_changed)
        self.compartment.textEdited.connect(self.species_data_changed)

        # TODO
        self.apply_button.clicked.connect(self.apply)

    def apply(self):
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
            self.old.charge = float(self.charge.text())
            self.old.compartment = self.compartment.text()

            self.changed = False
            self.changedspeciesList.emit()

    def verify_id(self):
        # print("SpeciesMask::verify_id")
        palette = self.id.palette()
        role = self.id.foregroundRole()
        palette.setColor(role, Qt.black)
        self.id.setPalette(palette)

        with self.appdata.cobra_py_model as model:
            m = cobra.Metabolite()
            try:
                m.id = self.id.text()
                model.add_metabolites([m])
            except:
                self.id.setStyleSheet("background: #ff9999")
                return False
            else:
                self.id.setStyleSheet("background: white")
                return True

    def verify_name(self):
        # print("SpeciesMask::verify_name")
        palette = self.name.palette()
        role = self.name.foregroundRole()
        palette.setColor(role, Qt.black)
        self.name.setPalette(palette)

        with self.appdata.cobra_py_model as model:
            m = cobra.Metabolite(id="test_id")
            try:
                m.name = self.name.text()
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
            x = float(self.charge.text())
        except:
            self.charge.setStyleSheet("background: #ff9999")
            return False
        else:
            self.charge.setStyleSheet("background: white")
            return True

    def verify_compartment(self):
        self.compartment.setStyleSheet("background: white")
        palette = self.compartment.palette()
        role = self.compartment.foregroundRole()
        palette.setColor(role, Qt.black)
        self.compartment.setPalette(palette)
        return True

    def verify_mask(self):
        if self.verify_id() & self.verify_name() & self.verify_formula() & self.verify_charge() & self.verify_compartment():
            self.is_valid = True
        else:
            self.is_valid = False

    def species_data_changed(self):
        self.changed = True
        self.verify_mask()
        self.update_state()

    def update_state(self):
        # print("SpeciesMask::update_state")

        if self.is_valid & self.changed:
            self.apply_button.setEnabled(True)
        else:
            self.apply_button.setEnabled(False)

    changedspeciesList = Signal()
