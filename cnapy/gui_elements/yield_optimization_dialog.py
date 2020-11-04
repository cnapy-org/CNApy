"""The cnapy yield optimization dialog"""

import sys
import traceback

import matplotlib.pyplot as plt
import pandas
from matplotlib.pyplot import scatter
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (QCompleter, QDialog, QHBoxLayout, QLabel,
                            QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

import cnapy.legacy as legacy
from cnapy.cnadata import CnaData
from cnapy.legacy import get_matlab_engine


class CompleterLineEdit(QLineEdit):
    # does new completion after COMMA ,

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
        prefix = text.split(',')[-1].strip()

        self.mycompleter.setCompletionPrefix(prefix)
        if prefix != '':
            self.mycompleter.complete()

    def complete_text(self, text):
        cursor_pos = self.cursorPosition()
        before_text = self.text()[:cursor_pos]
        after_text = self.text()[cursor_pos:]
        prefix_len = len(before_text.split(',')[-1].strip())
        self.setText(before_text[:cursor_pos - prefix_len] + text + after_text)
        self.setCursorPosition(cursor_pos - prefix_len + len(text))

    textChanged = Signal(str)


class YieldOptimizationDialog(QDialog):
    """A dialog to perform yield optimization"""

    def __init__(self, appdata):
        QDialog.__init__(self)
        self.setWindowTitle("Yield optimization")
        self.appdata = appdata
        self.eng = get_matlab_engine()

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
        self.d = QLineEdit("")
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
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

    def compute(self):

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
# rem=answer{1,1};
# if (isempty(rem))
#     msgbox('No reaction defined for vector c!');
#     return;
# end
        c_elements = self.c.text().split(",")
        print(c_elements)
        for c_element in c_elements:
            (reacid, factor) = c_element.split(" ")
            print((reacid, factor))
        code = "c=zeros(1,cnap.numr); \
                zw=[]; \
                numopt=0; \
                while 1 \
                    [pnr rem2]=strtok(rem); \
                    if (isempty(pnr)) \
                        break; \
                    end \
                    if(numopt==1) \
                        zw3=str2num(pnr); \
                        if(~isempty(zw3)) \
                            c(zw2)=zw3; \
                            rem=rem2; \
                        end \
                        numopt=0; \
                    else \
                        zw2=mfindstr(cnap.reacID,pnr); \
                        if(zw2==0) \
                            msgbox(['Could not find reaction identifier ''',pnr,''' .']); \
                            return; \
                        else \
                            c(zw2)=1; \
                            numopt=1; \
                        end \
                        rem=rem2; \
                    end \
                end"

        a = self.eng.eval(code, nargout=0)
        if legacy.is_matlab_ready():
            try:
                a = self.eng.eval(
                    "[maxyield,flux_vec,success, status]= CNAoptimizeYield(cnap, c, d, constraints, c_macro, takelp,0);", nargout=0)
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

                self.accept()
        elif legacy.is_octave_ready():
            a = self.eng.eval(
                "[maxyield,flux_vec,success, status]= CNAoptimizeYield(cnap, c, d, constraints, c_macro, takelp,0);", nargout=0)
            print(a)

            success = self.eng.pull('success')
            status = self.eng.pull('status')
            maxyield = self.eng.pull('maxyield')
            flux_vec = self.eng.pull('flux_vec')

            self.accept()
