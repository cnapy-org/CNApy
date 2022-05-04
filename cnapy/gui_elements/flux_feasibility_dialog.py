from qtpy.QtCore import Qt, Slot
from qtpy.QtWidgets import (QDialog, QGroupBox, QHBoxLayout,
                            QLabel, QLineEdit, QMessageBox, QPushButton,
                            QRadioButton, QVBoxLayout)

from cnapy.core import make_scenario_feasible, QPnotSupportedException

class FluxFeasibilityDialog(QDialog):
    def __init__(self, appdata):
        QDialog.__init__(self)
        self.setWindowTitle("Make scenario feasible")

        self.appdata = appdata

        self.layout = QVBoxLayout()

        g1 = QGroupBox("Optimization method:")
        s1 = QVBoxLayout()
        self.method_lp = QRadioButton("Linear Program")
        s1.addWidget(self.method_lp)
        self.method_qp = QRadioButton("Quadratic Program")
        s1.addWidget(self.method_qp)
        self.method_lp.setChecked(True)
        g1.setLayout(s1)
        self.layout.addWidget(g1)

        h1 = QHBoxLayout()
        h1.addWidget(QLabel("Default (weight) weight: "))
        self.default_weight = QLineEdit()
        self.default_weight.setText("1.0")
        h1.addWidget(self.default_weight)
        self.layout.addItem(h1)

        g2 = QGroupBox("Use as (reciprocal) weight:")
        s2 = QVBoxLayout()
        self.fixed_weight_button = QRadioButton("Set all weights equal")
        s2.addWidget(self.fixed_weight_button)
        self.abs_flux_weights_button = QRadioButton("Set according to absolute flux values")
        s2.addWidget(self.abs_flux_weights_button)
        l21 = QHBoxLayout()
        self.weights_key_button = QRadioButton("Use value from annotation with key: ")
        l21.addWidget(self.weights_key_button)
        self.weights_key = QLineEdit("variance")
        l21.addWidget(self.weights_key)
        s2.addLayout(l21)
        self.abs_flux_weights_button.setChecked(True)
        g2.setLayout(s2)
        self.layout.addWidget(g2)

        l3 = QHBoxLayout()
        self.button = QPushButton("Compute")
        self.cancel = QPushButton("Close")
        l3.addWidget(self.button)
        l3.addWidget(self.cancel)
        self.layout.addItem(l3)
        self.setLayout(self.layout)

        self.reactions_in_objective = []
        self.solution = None

        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

    @Slot()
    def compute(self):
        try:
            default_weight = float(self.default_weight.text())
        except ValueError:
            default_weight = 0
        if default_weight <= 0:
            QMessageBox.critical(self, "Invalid default weight",
                "Default weight must be a positive number.")
            return

        abs_flux_weights: bool = False
        weights_key: str=None
        if self.abs_flux_weights_button.isChecked():
            abs_flux_weights = True
        elif self.weights_key_button.isChecked():
            weights_key = self.weights_key.text()

        self.setCursor(Qt.BusyCursor)
        try:
            self.solution, self.reactions_in_objective = make_scenario_feasible(self.appdata.project.cobra_py_model,
                self.appdata.project.scen_values, use_QP=self.method_qp.isChecked(),
                abs_flux_weights=abs_flux_weights, weights_key=weights_key)
            self.accept()
        except QPnotSupportedException:
            QMessageBox.critical(self, "Solver with support for quadratic objectives required",
                "Choose an appropriate solver, e.g. cplex, gurobi, cbc-coinor (see Configure COBRApy in the Config menu).")
            self.reject()
        finally:
            self.setCursor(Qt.ArrowCursor)
