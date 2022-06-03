"""The cnapy elementary flux modes calculator dialog"""
import io

from qtpy.QtCore import Qt
from qtpy.QtGui import QIntValidator
from qtpy.QtWidgets import (QCheckBox, QDialog, QGroupBox, QHBoxLayout, QLabel,
                            QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from cnapy.appdata import AppData
from cnapy.flux_vector_container import FluxVectorContainer


class EFMDialog(QDialog):
    """A dialog to set up EFM calculation"""

    def __init__(self, appdata: AppData, central_widget):
        QDialog.__init__(self)
        self.setWindowTitle("Elementary Flux Mode Computation")

        self.appdata = appdata
        self.central_widget = central_widget
        self.out = io.StringIO()
        self.err = io.StringIO()

        self.layout = QVBoxLayout()

        l1 = QHBoxLayout()
        self.constraints = QCheckBox("consider 0 in current scenario as off")
        self.constraints.setCheckState(Qt.Checked)
        l1.addWidget(self.constraints)
        self.layout.addItem(l1)

        l2 = QHBoxLayout()
        self.flux_bounds = QGroupBox(
            "use flux bounds to calculate elementary flux vectors")
        self.flux_bounds.setCheckable(True)
        self.flux_bounds.setChecked(False)

        vbox = QVBoxLayout()
        label = QLabel("Threshold for bounds to be unconstrained")
        vbox.addWidget(label)
        self.threshold = QLineEdit("100")
        validator = QIntValidator()
        validator.setBottom(0)
        self.threshold.setValidator(validator)
        vbox.addWidget(self.threshold)
        self.flux_bounds.setLayout(vbox)
        l2.addWidget(self.flux_bounds)
        self.layout.addItem(l2)

        l3 = QHBoxLayout()
        self.check_reversibility = QCheckBox(
            "check reversibility")
        self.check_reversibility.setCheckState(Qt.Checked)
        l3.addWidget(self.check_reversibility)
        self.layout.addItem(l3)

        l4 = QHBoxLayout()
        self.convex_basis = QCheckBox(
            "only convex basis")
        l4.addWidget(self.convex_basis)
        self.layout.addItem(l4)

        l5 = QHBoxLayout()
        self.isozymes = QCheckBox(
            "consider isozymes only once")
        l5.addWidget(self.isozymes)
        self.layout.addItem(l5)

        # TODO: choose solver

        l7 = QHBoxLayout()
        self.rational_numbers = QCheckBox(
            "use rational numbers")
        l7.addWidget(self.rational_numbers)
        self.layout.addItem(l7)

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

        # create CobraModel for matlab
        self.appdata.create_cobra_model()

        # get some data
        reac_id = self.eng.get_reacID()

        # setting parameters
        a = self.eng.eval("constraints = {};",
                          nargout=0, stdout=self.out, stderr=self.err)
        scenario = {}
        if self.constraints.checkState() == Qt.Checked or self.flux_bounds.isChecked():
            onoff_str = ""
            for r in reac_id:
                if r in self.appdata.project.scen_values.keys():
                    (vl, vu) = self.appdata.project.scen_values[r]
                    if vl == vu:
                        if vl > 0:
                            onoff_str = onoff_str+" NaN"  # efmtool does not support 1
                        elif vl == 0:
                            scenario[r] = (0, 0)
                            onoff_str = onoff_str+" 0"
                        else:
                            onoff_str = onoff_str+" NaN"
                            print("WARN: negative value in scenario")
                    else:
                        onoff_str = onoff_str+" NaN"
                        print("WARN: not fixed value in scenario")
                else:
                    onoff_str = onoff_str+" NaN"

            onoff_str = "reaconoff = ["+onoff_str+"];"
            a = self.eng.eval(onoff_str,
                              nargout=0, stdout=self.out, stderr=self.err)

            a = self.eng.eval("constraints.reaconoff = reaconoff;",
                              nargout=0, stdout=self.out, stderr=self.err)

        if self.flux_bounds.isChecked():
            threshold = float(self.threshold.text())
            lb_str = ""
            ub_str = ""
            for r in reac_id:
                c_reaction = self.appdata.project.cobra_py_model.reactions.get_by_id(
                    r)
                if r in self.appdata.project.scen_values:
                    (vl, vu) = self.appdata.project.scen_values[r]
                else:
                    vl = c_reaction.lower_bound
                    vu = c_reaction.upper_bound
                if vl <= -threshold:
                    vl = "NaN"
                if vu >= threshold:
                    vu = "NaN"
                if vl == 0 and vu == 0:  # already in reaconoff, can be skipped here
                    vl = "NaN"
                    vu = "NaN"
                lb_str = lb_str+" "+str(vl)
                ub_str = ub_str+" "+str(vu)

            lb_str = "lb = ["+lb_str+"];"
            a = self.eng.eval(lb_str, nargout=0,
                              stdout=self.out, stderr=self.err)
            a = self.eng.eval("constraints.lb = lb;", nargout=0,
                              stdout=self.out, stderr=self.err)

            ub_str = "ub = ["+ub_str+"];"
            a = self.eng.eval(ub_str, nargout=0,
                              stdout=self.out, stderr=self.err)
            a = self.eng.eval("constraints.ub = ub;", nargout=0,
                              stdout=self.out, stderr=self.err)

        # TODO set solver 4 = EFMTool 3 = MetaTool, 1 = cna Mex file, 0 = cna functions
        a = self.eng.eval("solver = 4;", nargout=0,
                          stdout=self.out, stderr=self.err)

        if self.check_reversibility.checkState() == Qt.Checked:
            a = self.eng.eval("irrev_flag = 1;", nargout=0,
                              stdout=self.out, stderr=self.err)
        else:
            a = self.eng.eval("irrev_flag = 0;",
                              nargout=0, stdout=self.out, stderr=self.err)

        # convex basis computation is only possible with METATOOL solver=3
        if self.convex_basis.checkState() == Qt.Checked:
            a = self.eng.eval("conv_basis_flag = 1; solver = 3;",
                              nargout=0, stdout=self.out, stderr=self.err)
        else:
            a = self.eng.eval("conv_basis_flag = 0;",
                              nargout=0, stdout=self.out, stderr=self.err)

        if self.isozymes.checkState() == Qt.Checked:
            a = self.eng.eval("iso_flag = 1;", nargout=0,
                              stdout=self.out, stderr=self.err)
        else:
            a = self.eng.eval("iso_flag = 0;",
                              nargout=0, stdout=self.out, stderr=self.err)

        # default we have no macromolecules and display is et to ALL
        a = self.eng.eval("c_macro=[]; display= 'ALL';",
                          nargout=0, stdout=self.out, stderr=self.err)

        if self.rational_numbers.checkState() == Qt.Checked:
            a = self.eng.eval("efmtool_options = {'arithmetic', 'fractional'};",
                              nargout=0, stdout=self.out, stderr=self.err)
        else:
            a = self.eng.eval("efmtool_options = {};",
                              nargout=0, stdout=self.out, stderr=self.err)


    def result2ui(self, ems, idx, reac_id, irreversible, unbounded, scenario):
        if len(ems) == 0:
            QMessageBox.information(self, 'No modes',
                                    'Modes have not been calculated or do not exist.')
        else:
            self.appdata.project.modes = FluxVectorContainer(
                ems, [reac_id[int(i)-1] for i in idx[0]], irreversible, unbounded)
            self.central_widget.mode_navigator.current = 0
            self.central_widget.mode_navigator.scenario = scenario
            self.central_widget.mode_navigator.set_to_efm()
            self.central_widget.update_mode()
