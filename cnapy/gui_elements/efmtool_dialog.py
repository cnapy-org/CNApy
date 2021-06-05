"""The cnapy elementary flux modes calculator dialog"""
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QMessageBox,
                            QPushButton, QVBoxLayout)

import cnapy.core
from cnapy.appdata import AppData


class EFMtoolDialog(QDialog):
    """A dialog to set up EFM calculation"""

    def __init__(self, appdata: AppData, central_widget):
        QDialog.__init__(self)
        self.setWindowTitle("Elementary Flux Mode Computation")

        self.appdata = appdata
        self.central_widget = central_widget

        self.layout = QVBoxLayout()

        l1 = QHBoxLayout()
        self.constraints = QCheckBox("consider 0 in current scenario as off")
        self.constraints.setCheckState(Qt.Checked)
        l1.addWidget(self.constraints)
        self.layout.addItem(l1)

        lx = QHBoxLayout()
        self.button = QPushButton("Compute")
        self.cancel = QPushButton("Close")
        lx.addWidget(self.button)
        lx.addWidget(self.cancel)
        self.layout.addItem(lx)

        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

    def compute(self):
        self.setCursor(Qt.BusyCursor)
        (ems, scenario) = cnapy.core.efm_computation(
            self.appdata.project.cobra_py_model, self.appdata.project.scen_values,
            self.constraints.checkState() == Qt.Checked)

        self.setCursor(Qt.ArrowCursor)
        if ems is None:
            QMessageBox.information(self, 'No modes',
                                    'An error occured and modes have not been calculated.')
        else:
            if len(ems) == 0:
                QMessageBox.information(self, 'No modes',
                                        'No elementary modes exist.')
            else:
                print(scenario)
                self.appdata.project.modes = ems
                self.central_widget.mode_navigator.current = 0
                self.central_widget.mode_navigator.scenario = scenario
                self.central_widget.mode_navigator.set_to_efm()
                self.central_widget.update_mode()
