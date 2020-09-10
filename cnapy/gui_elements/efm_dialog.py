"""The cnapy elementary flux modes calculator dialog"""
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QCheckBox, QButtonGroup, QComboBox, QDialog, QHBoxLayout,
                               QLineEdit, QPushButton, QRadioButton,
                               QVBoxLayout)

from cnapy.cnadata import CnaData
import cnapy.legacy


class EFMDialog(QDialog):
    """A dialog to set up EFM calculation"""

    def __init__(self, appdata: CnaData, engine, out, err):
        QDialog.__init__(self)
        self.appdata = appdata
        self.eng = engine
        self.out = out
        self.err = err

        self.layout = QVBoxLayout()

        l1 = QHBoxLayout()
        self.constraints = QCheckBox("consider current scenario")
        l1.addWidget(self.constraints)
        self.layout.addItem(l1)

        l2 = QHBoxLayout()
        self.flux_bounds = QCheckBox(
            "use flux bounds to calculate elementary flux vectors")
        l2.addWidget(self.flux_bounds)
        self.layout.addItem(l2)

        l3 = QHBoxLayout()
        self.check_reversibility = QCheckBox(
            "check reversibility")
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
        self.cancel = QPushButton("Cancel")
        lx.addWidget(self.button)
        lx.addWidget(self.cancel)
        self.layout.addItem(lx)

        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

    def compute(self):

        # create CobraModel for matlab
        cnapy.legacy.createCobraModel(self.appdata.project.cobra_py_model)

        print(".")
        a = self.eng.eval("startcna(1)", nargout=0,
                          stdout=self.out, stderr=self.err)
        print(".")
        a = self.eng.eval("load('cobra_model.mat')",
                          nargout=0, stdout=self.out, stderr=self.err)
        print(".")
        a = self.eng.eval("cnap = CNAcobra2cna(cbmodel);",
                          nargout=0, stdout=self.out, stderr=self.err)
        print(".")

        # get some data
        a = self.eng.eval("reac_id = cellstr(cnap.reacID).';",
                          nargout=0, stdout=self.out, stderr=self.err)
        reac_id = self.eng.workspace['reac_id']

        # setting parameters
        oems = []
        print(".")
        # if self.constraints.checkState() == Qt.Checked:
        #     a = self.eng.eval("cnap.local.val_fixrates = 1;",
        #                       nargout=0, stdout=self.out, stderr=self.err)

        # if self.flux_bounds.checkState() == Qt.Checked:
        #     a = self.eng.eval("cnap.local.val_fixbounds = 1;",
        #                       nargout=0, stdout=self.out, stderr=self.err)
        # else:
        #     a = self.eng.eval("cnap.local.val_fixbounds = 0;",
        #                       nargout=0, stdout=self.out, stderr=self.err)

        if self.check_reversibility.checkState() == Qt.Checked:
            a = self.eng.eval("irrev_flag = 1;",
                              nargout=0, stdout=self.out, stderr=self.err)
        else:
            a = self.eng.eval("irrev_flag = 0;",
                              nargout=0, stdout=self.out, stderr=self.err)

        if self.convex_basis.checkState() == Qt.Checked:
            a = self.eng.eval("conv_basis_flag = 1;",
                              nargout=0, stdout=self.out, stderr=self.err)
        else:
            a = self.eng.eval("conv_basis_flag = 0;",
                              nargout=0, stdout=self.out, stderr=self.err)

        if self.isozymes.checkState() == Qt.Checked:
            a = self.eng.eval("iso_flag = 1;",
                              nargout=0, stdout=self.out, stderr=self.err)
        else:
            a = self.eng.eval("iso_flag = 0;",
                              nargout=0, stdout=self.out, stderr=self.err)

        # TODO set solver 4 = EFMTool 3 = MetaTool, 1 = cna Mex file, 0 = cna functions
        a = self.eng.eval("solver = 4;",
                          nargout=0, stdout=self.out, stderr=self.err)

        if self.rational_numbers.checkState() == Qt.Checked:
            a = self.eng.eval("efmtool_options = {'arithmetic', 'fractional'};",
                              nargout=0, stdout=self.out, stderr=self.err)
        else:
            a = self.eng.eval("efmtool_options = {};",
                              nargout=0, stdout=self.out, stderr=self.err)

        print(".")
        a = self.eng.eval("c_makro=[]; display= 'ALL';", nargout=0,
                          stdout=self.out, stderr=self.err)

        a = self.eng.eval("constraints= [];", nargout=0,
                          stdout=self.out, stderr=self.err)

        # get_rates(cnap);
        a = self.eng.eval("cnap.local.rb = [];",
                          nargout=0, stdout=self.out, stderr=self.err)

        i = 0

        print(self.appdata.project.scen_values)
        for r in self.appdata.project.scen_values:
            i = i + 1

            idx = 0
            count = 1
            for r2 in reac_id:
                if r2 == r:
                    idx = count
                    break
                else:
                    count += 1

            val = self.appdata.project.scen_values[r]

            if val != "":
                (vl, vu) = val
                if vl != vu:
                    print("Error scenario contains flux range in reaction", r)
                    print("this is not allowed for elementary mode computation")
                    return

                a = self.eng.eval("cnap.local.rb(" + str(i) + ",1) = " + str(idx) + ";" +
                                  "cnap.local.rb("+str(i)+", 2)="+str(vl)+";",
                                  nargout=0, stdout=self.out, stderr=self.err)

        a = eng.eval(
            "[ems, irrev_ems, ems_idx] = CNAcomputeEFM(cnap, constraints,solver,irrev_flag,convbasis_flag,iso_flag,c_macro,display,efmtool_options);", nargout=0, stdout=out, stderr=err)
        ems = eng.workspace['ems']
        idx = eng.workspace['ems_idx']

       # turn vectors into maps
       for mode in ems:
            print("Mode:")
            count_ccc=0
            omode={}
            for e in mode:
                idx2=int(idx[0][count_ccc])-1
                reaction=reac_id[idx2]
                print("element: ", count_ccc, idx2, reaction, e)
                count_ccc += 1
                omode[reaction]=e
            oems.append(omode)

        self.appdata.project.modes=oems

        self.accept()


def load_scenario_into_cnap_local_rb(self, model):
    for x in self.scen_values:
        try:
            y=model.reactions.get_by_id(x)
        except:
            print('reaction', x, 'not found!')
        else:
            (vl, vu)=self.scen_values[x]
            y.lower_bound=vl
            y.upper_bound=vu
