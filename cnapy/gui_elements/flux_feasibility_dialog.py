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

        g1 = QGroupBox("Resolve infeasibility minimizing the weighted changes of given fluxes with:")
        s1 = QVBoxLayout()
        self.method_lp = QRadioButton("Linear Program")
        s1.addWidget(self.method_lp)
        self.method_qp = QRadioButton("Quadratic Program")
        s1.addWidget(self.method_qp)
        self.method_lp.setChecked(True)
        g1.setLayout(s1)
        self.layout.addWidget(g1)

        g2 = QGroupBox("Select weights for correcting given fluxes:")
        s2 = QVBoxLayout()
        self.fixed_weight_button = QRadioButton("Weight all fluxes equally")
        s2.addWidget(self.fixed_weight_button)
        self.abs_flux_weights_button = QRadioButton("Relative to given flux (reciprocal of absolute flux)")
        s2.addWidget(self.abs_flux_weights_button)
        l21 = QHBoxLayout()
        self.weights_key_button = QRadioButton("Use reciprocal of value from annotation with key: ")
        l21.addWidget(self.weights_key_button)
        self.weights_key = QLineEdit("variance")
        l21.addWidget(self.weights_key)
        s2.addLayout(l21)
        self.abs_flux_weights_button.setChecked(True)
        h1 = QHBoxLayout()
        h1.addWidget(QLabel("        Default weight: "))
        self.default_weight = QLineEdit()
        self.default_weight.setText("1.0")
        h1.addWidget(self.default_weight)
        h1.addWidget(QLabel(" Reciprocal of this is used where a value\n from the annotation is unavailable"))
        s2.addLayout(h1)
        g2.setLayout(s2)
        self.layout.addWidget(g2)

        self.layout.addWidget(QLabel("Reactions that are set to 0 in the scenario are considered to be switched off"))

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
        default_weight: float = 1.0
        abs_flux_weights: bool = False
        weights_key: str = None

        if self.abs_flux_weights_button.isChecked():
            abs_flux_weights = True
        elif self.weights_key_button.isChecked():
            try:
                default_weight = float(self.default_weight.text())
            except ValueError:
                default_weight = 0
            if default_weight <= 0:
                QMessageBox.critical(self, "Invalid default weight",
                    "Default weight must be a positive number.")
                return
            weights_key = self.weights_key.text()

        self.setCursor(Qt.BusyCursor)
        try:
            self.solution, self.reactions_in_objective = make_scenario_feasible(self.appdata.project.cobra_py_model,
                self.appdata.project.scen_values, use_QP=self.method_qp.isChecked(), default_weight=default_weight,
                abs_flux_weights=abs_flux_weights, weights_key=weights_key)
            self.accept()
        except QPnotSupportedException:
            QMessageBox.critical(self, "Solver with support for quadratic objectives required",
                "Choose an appropriate solver, e.g. cplex, gurobi, cbc-coinor (see Configure COBRApy in the Config menu).")
            self.reject()
        finally:
            self.setCursor(Qt.ArrowCursor)
