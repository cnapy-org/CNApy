"""The cnapy yield optimization dialog"""

import re
import sys
import traceback

import cnapy.legacy as legacy
import matplotlib.pyplot as plt
import pandas
from cnapy.cnadata import CnaData
from cnapy.gui_elements.centralwidget import CentralWidget
from cnapy.legacy import get_matlab_engine
from matplotlib.pyplot import scatter
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (QCompleter, QDialog, QHBoxLayout, QLabel,
                            QLineEdit, QMessageBox, QPushButton, QVBoxLayout)


class CompleterLineEdit(QLineEdit):
    # does new completion after Plus '+'

    def __init__(self, wordlist, *args):
        QLineEdit.__init__(self, *args)
        self.mycompleter = QCompleter(wordlist)
        self.mycompleter.setCaseSensitivity(Qt.CaseInsensitive)
        self.mycompleter.setWidget(self)
        self.textChanged.connect(self.text_changed)
        self.mycompleter.activated.connect(self.complete_text)

    def text_changed(self, text):
        all_text = text
        text = all_text[:self.cursorPosition()]
        prefix = text.split('+')[-1].strip()
        prefix = prefix.split(' ')[-1].strip()
        self.mycompleter.setCompletionPrefix(prefix)
        if prefix != '':
            self.mycompleter.complete()

    def complete_text(self, text):
        cursor_pos = self.cursorPosition()
        before_text = self.text()[:cursor_pos]
        after_text = self.text()[cursor_pos:]
        prefix = before_text.split('+')[-1]
        prefix = prefix.split(' ')[-1]
        prefix_len = len(prefix.strip())
        self.setText(before_text[:cursor_pos - prefix_len] + text + after_text)
        self.setCursorPosition(cursor_pos - prefix_len + len(text))

    textChanged = Signal(str)


class YieldOptimizationDialog(QDialog):
    """A dialog to perform yield optimization"""

    def __init__(self, appdata: CnaData, centralwidget: CentralWidget):
        QDialog.__init__(self)
        self.setWindowTitle("Yield optimization")
        self.appdata = appdata
        self.centralwidget = centralwidget
        self.eng = get_matlab_engine()

        self.polynom_re = re.compile(
            '([ ]*(?P<factor>\d*)[ ]*[*]?[ ]*(?P<reac_id>[abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVW]+\w*)[ ]*)')
        completer = QCompleter(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)

        self.layout = QVBoxLayout()
        t1 = QLabel(
            "Define c of the yield function Y=c*r/d*r by providing relevant reaction identifiers (each optionally followed by a weighting factor)")
        self.layout.addWidget(t1)
        self.c = CompleterLineEdit(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), "")
        self.c.setPlaceholderText("")
        self.layout.addWidget(self.c)
        t2 = QLabel(
            "Define d of the yield function Y=c*r/d*r by providing relevant reaction identifiers (each optionally followed by a weighting factor)")
        self.layout.addWidget(t2)
        self.d = CompleterLineEdit(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), "")
        self.d.setPlaceholderText("")
        self.d.setCompleter(completer)
        self.layout.addWidget(self.d)

        l3 = QHBoxLayout()
        self.button = QPushButton("Compute")
        self.cancel = QPushButton("Cancel")
        l3.addWidget(self.button)
        l3.addWidget(self.cancel)
        self.layout.addItem(l3)
        self.setLayout(self.layout)

        # Connecting the signal
        self.c.textChanged.connect(self.validate_dialog)
        self.d.textChanged.connect(self.validate_dialog)
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

        self.validate_dialog()

    def validate_dialog(self):

        valid_c = self.validate_c()
        valid_d = self.validate_d()
        if valid_c and valid_d:
            self.button.setEnabled(True)
        else:
            self.button.setEnabled(False)

    def validate_polynom(self, text: str):
        texts = text.split('+')
        valid = True
        for elem in texts:
            match = self.polynom_re.fullmatch(elem)
            if match == None:
                valid = False
            else:
                if match.groupdict()['reac_id'] not in self.appdata.project.cobra_py_model.reactions.list_attr("id"):
                    valid = False
        return valid

    def validate_c(self):

        palette = self.c.palette()
        role = self.c.foregroundRole()
        palette.setColor(role, Qt.black)
        self.c.setPalette(palette)

        text = self.c.text()
        valid = self.validate_polynom(text)
        if valid:
            self.c.setStyleSheet("background: white")
        else:
            self.c.setStyleSheet("background: #ff9999")
        return valid

    def validate_d(self):

        palette = self.d.palette()
        role = self.d.foregroundRole()
        palette.setColor(role, Qt.black)
        self.d.setPalette(palette)

        text = self.d.text()
        valid = self.validate_polynom(text)
        if valid:
            self.d.setStyleSheet("background: white")
        else:
            self.d.setStyleSheet("background: #ff9999")

        return valid

    def compute(self):

        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            # create CobraModel for matlab
            legacy.createCobraModel(self.appdata)

            a = self.eng.eval("load('cobra_model.mat')",
                              nargout=0)
            a = self.eng.eval("cnap = CNAcobra2cna(cbmodel);",
                              nargout=0)

            # get some data
            a = self.eng.eval("reac_id = cellstr(cnap.reacID)';",
                              nargout=0)
            reac_id = []
            if legacy.is_matlab_ready():
                reac_id = self.eng.workspace['reac_id']
            elif legacy.is_octave_ready():
                reac_id = self.eng.pull('reac_id')
                reac_id = reac_id.tolist()[0]
            else:
                print("Error: Neither matlab nor octave found")

            c = []
            c_elements = self.c.text().split('+')
            for elem in c_elements:
                match = self.polynom_re.fullmatch(elem)
                reaction = match.groupdict()['reac_id']
                factor = match.groupdict()['factor']
                c.append((factor, reaction))
            res = []
            idx = 0
            for r1 in reac_id:
                res.append(0)
                for (factor, r2) in c:
                    if r1 == r2:
                        if factor == "":
                            res[idx] = 1
                        else:
                            res[idx] = int(factor)
                        break
                idx = idx+1
            code = "c =" + str(res)+";"
            print(code)
            a = self.eng.eval(code, nargout=0)

            d = []
            d_elements = self.d.text().split('+')
            for elem in d_elements:
                match = self.polynom_re.fullmatch(elem)
                reaction = match.groupdict()['reac_id']
                factor = match.groupdict()['factor']
                d.append((factor, reaction))
            res = []
            idx = 0
            for r1 in reac_id:
                res.append(0)
                for (factor, r2) in d:
                    if r1 == r2:
                        if factor == "":
                            res[idx] = 1
                        else:
                            res[idx] = int(factor)
                        break
                idx = idx+1
            code = "d =" + str(res)+";"
            print(code)
            self.eng.eval(code, nargout=0)

            # res = []
            # idx = 0
            # for r in reac_id:
            #     if r in self.appdata.project.scen_values.keys():
            #         val = str(self.appdata.project.scen_values[r])
            #     else:
            #         val = "NaN"
            #     res.append(val)
            # code = "fixedFluxes =["
            # for e in res:
            #     code = code+e+","
            # code = code[0:-1]+"];"

            # print(code)
            self.eng.eval("fixedFluxes =[];")
            self.eng.eval("c_macro =[];")
            # solver: selects the LP solver
            # 0: GLPK (glpklp)
            # 1: Matlab Optimization Toolbox (linprog)
            # 2: CPLEX (cplexlp)
            # -1: (default) Either the solver CPLEX or GLPK or MATLAB (linprog) is used
            # (in this order), depending on availability.
            self.eng.eval("solver =1;")

            # verbose: controls the output printed to the command line
            # -1: suppress all output, even warnings
            #  0: no solver output, but warnings and information on final result will be shown
            #  1: as option '0' but with additional solver output
            #  (default: 0)
            self.eng.eval("verbose = 0;")
            if legacy.is_matlab_ready():
                try:
                    a = self.eng.eval(
                        "[maxyield,flux_vec,success, status]= CNAoptimizeYield(cnap, c, d, fixedFluxes, c_macro, solver, verbose);", nargout=0)
                    print(a)
                except Exception:
                    traceback.print_exception(*sys.exc_info())
                    QMessageBox.warning(self, 'Unknown exception occured!',
                                              'Please report the problem to:\n\nhttps://github.com/ARB-Lab/CNApy/issues')
                else:
                    success = self.eng.workspace['success']
                    status = self.eng.workspace['status']
                    maxyield = self.eng.workspace['maxyield']
                    flux_vec = self.eng.workspace['flux_vec']

                    if success == 0.0:
                        QMessageBox.warning(self, 'No Solution!',
                                            'No solution found! Maybe unbound.\nStatus:'+str(status))
                    else:
                        QMessageBox.warning(self, 'Solution!',
                                            'Maximum yield: '+str(maxyield))
                        # write results into comp_values
                        idx = 0
                        for r in reac_id:
                            val = flux_vec[idx][0]
                            self.appdata.project.comp_values[r] = (
                                float(val), float(val))
                            idx = idx+1
                        self.accept()

            elif legacy.is_octave_ready():
                a = self.eng.eval(
                    "[maxyield,flux_vec,success, status]= CNAoptimizeYield(cnap, c, d, fixedFluxes, c_macro, solver, verbose);", nargout=0)
                print(a)

                success = self.eng.pull('success')
                status = self.eng.pull('status')
                maxyield = self.eng.pull('maxyield')
                flux_vec = self.eng.pull('flux_vec')

                if success == 0.0:
                    QMessageBox.warning(self, 'No Solution!',
                                              'No solution found! Maybe unbound.\nStatus:'+str(status))
                else:
                    QMessageBox.warning(self, 'Solution!',
                                        'Maximum yield: '+str(maxyield))

                    # write results into comp_values
                    idx = 0
                    for r in reac_id:
                        val = flux_vec[idx][0]
                        self.appdata.project.comp_values[r] = (
                            float(val), float(val))
                        idx = idx+1
                    self.centralwidget.update()
                    self.accept()
