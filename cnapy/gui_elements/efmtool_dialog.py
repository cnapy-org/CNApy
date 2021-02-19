"""The cnapy elementary flux modes calculator dialog"""
import io
import traceback

from qtpy.QtCore import Qt
from qtpy.QtGui import QIntValidator
from qtpy.QtWidgets import (QCheckBox, QDialog, QGroupBox, QHBoxLayout, QLabel,
                            QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from cnapy.cnadata import CnaData
import cnapy.efmtool_extern as efmtool_extern
from cobra.util.array import create_stoichiometric_matrix
import numpy

class EFMtoolDialog(QDialog):
    """A dialog to set up EFM calculation"""

    def __init__(self, appdata: CnaData, centralwidget):
        QDialog.__init__(self)
        self.appdata = appdata
        self.centralwidget = centralwidget
    
        self.layout = QVBoxLayout()

        l1 = QHBoxLayout()
        self.constraints = QCheckBox("consider 0 in current scenario as off")
        self.constraints.setCheckState(Qt.Checked)
        l1.addWidget(self.constraints)
        self.layout.addItem(l1)

        # l2 = QHBoxLayout()
        # self.flux_bounds = QGroupBox(
        #     "use flux bounds to calculate elementary flux vectors")
        # self.flux_bounds.setCheckable(True)
        # self.flux_bounds.setChecked(False)

        # vbox = QVBoxLayout()
        # label = QLabel("Threshold for bounds to be unconstrained")
        # vbox.addWidget(label)
        # self.threshold = QLineEdit("100")
        # validator = QIntValidator()
        # validator.setBottom(0)
        # self.threshold.setValidator(validator)
        # vbox.addWidget(self.threshold)
        # self.flux_bounds.setLayout(vbox)
        # l2.addWidget(self.flux_bounds)
        # self.layout.addItem(l2)

        # l3 = QHBoxLayout()
        # self.check_reversibility = QCheckBox(
        #     "check reversibility")
        # self.check_reversibility.setCheckState(Qt.Checked)
        # l3.addWidget(self.check_reversibility)
        # self.layout.addItem(l3)

        # l4 = QHBoxLayout()
        # self.convex_basis = QCheckBox(
        #     "only convex basis")
        # l4.addWidget(self.convex_basis)
        # self.layout.addItem(l4)

        # l5 = QHBoxLayout()
        # self.isozymes = QCheckBox(
        #     "consider isozymes only once")
        # l5.addWidget(self.isozymes)
        # self.layout.addItem(l5)

        # # TODO: choose solver

        # l7 = QHBoxLayout()
        # self.rational_numbers = QCheckBox(
        #     "use rational numbers")
        # l7.addWidget(self.rational_numbers)
        # self.layout.addItem(l7)

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
        stdf = create_stoichiometric_matrix(self.appdata.project.cobra_py_model, array_type='DataFrame')
        rev = [r.reversibility for r in self.appdata.project.cobra_py_model.reactions]
        scenario = {}
        if self.constraints.checkState() == Qt.Checked:
            for r in self.appdata.project.scen_values.keys():
                (vl, vu) = self.appdata.project.scen_values[r]
                if vl == vu and vl == 0:
                    del rev[stdf.columns.get_loc(r)]
                    del stdf[r] # delete the column with this reaction id from the data frame
                    scenario[r] = (0, 0)
        ems = efmtool_extern.calculate_flux_modes(stdf.values, numpy.array(rev, dtype=int))
        idx = stdf.columns.tolist()

        self.result2ui(ems, idx, scenario)

    def result2ui(self, ems, idx, scenario):
        if ems is None:
            QMessageBox.information(self, 'No modes',
                                    'An error occured and modes have not been calculated.')
        elif ems.shape[1] == 0:
            QMessageBox.information(self, 'No modes',
                                    'No elementary modes exist.')
        else:
            oems = [None] * ems.shape[1]
            for j in range(ems.shape[1]):
                oems[j] = {idx[i]: float(ems[i, j]) for i in range(ems.shape[0]) if ems[i, j] != 0}
                # print("Mode:")
                # count_ccc = 0
                # omode = {}
                # for element in mode:
                #     idx2 = int(idx[0][count_ccc])-1
                #     reaction = reac_id[idx2]
                #     print("element: ", count_ccc,
                #           idx2, reaction, element)
                #     count_ccc += 1
                #     if element != 0:
                #         omode[reaction] = float(element)
                # oems.append(omode)
            self.appdata.project.modes = oems
            self.centralwidget.mode_navigator.current = 0
            self.centralwidget.mode_navigator.scenario = scenario
            self.centralwidget.mode_navigator.title.setText("Mode Navigation")
            self.centralwidget.update_mode()
