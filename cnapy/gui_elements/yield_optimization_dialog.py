"""The cnapy yield optimization dialog"""
from random import randint
from numpy import isnan, isinf
import re
from qtpy.QtCore import Qt, Signal, Slot
from qtpy.QtWidgets import (QDialog, QHBoxLayout, QLabel, QComboBox,
                            QMessageBox, QPushButton, QVBoxLayout, QFrame)

from cnapy.appdata import AppData
from cnapy.gui_elements.central_widget import CentralWidget
from cnapy.utils import QComplReceivLineEdit, QHSeperationLine
from straindesign import yopt, linexpr2dict, linexprdict2str, avail_solvers
from straindesign.names import *

class YieldOptimizationDialog(QDialog):
    """A dialog to perform yield optimization"""

    def __init__(self, appdata: AppData, central_widget: CentralWidget):
        QDialog.__init__(self)
        self.setWindowTitle("Yield optimization")

        self.appdata = appdata
        self.central_widget = central_widget

        numr = len(self.appdata.project.cobra_py_model.reactions)
        self.reac_ids = self.appdata.project.reaction_ids.id_list
        if numr > 2:
            r1 = self.appdata.project.cobra_py_model.reactions[randint(0,numr-1)].id
            r2 = self.appdata.project.cobra_py_model.reactions[randint(0,numr-1)].id
        else:
            r1 = 'r_product'
            r2 = 'r_substrate'

        self.layout = QVBoxLayout()
        l = QLabel("Maximize (or minimize) a yield function. \n"+ \
                   "Numerator and denominator are specified as linear expressions \n"+ \
                   "with reaction identifiers and (optionally) coefficients.\n"+\
                   "Keep in mind that exchange reactions are often defined in the direction of export.\n"+
                   "Consider changing signs.")
        self.layout.addWidget(l)
        editor_layout = QHBoxLayout()
        self.sense_combo = QComboBox()
        self.sense_combo.insertItems(0,['maximize', 'minimize'])
        self.sense_combo.setMinimumWidth(120)
        editor_layout.addWidget(self.sense_combo)
        open_bracket = QLabel(' ') # QLabel('(')
        font = open_bracket.font()
        font.setPointSize(30)
        open_bracket.setFont(font)
        editor_layout.addWidget(open_bracket)
        num_den_layout = QVBoxLayout()
        self.numerator = QComplReceivLineEdit(self, self.appdata.project.reaction_ids, check=True)
        self.numerator.setPlaceholderText('numerator (e.g. 1.0 '+r1+')')
        self.denominator = QComplReceivLineEdit(self, self.appdata.project.reaction_ids, check=True)
        self.denominator.setPlaceholderText('denominator (e.g. 1.0 '+r2+')')
        num_den_layout.addWidget(self.numerator)
        sep = QHSeperationLine()
        sep.setFrameShadow(QFrame.Plain)
        sep.setLineWidth(2)
        num_den_layout.addWidget(sep)
        num_den_layout.addWidget(self.denominator)
        editor_layout.addItem(num_den_layout)
        self.layout.addItem(editor_layout)

        l3 = QHBoxLayout()
        self.button = QPushButton("Compute")
        self.cancel = QPushButton("Close")
        l3.addWidget(self.button)
        l3.addWidget(self.cancel)
        self.layout.addItem(l3)
        self.setLayout(self.layout)

        # Connecting the signal
        self.numerator.textCorrect.connect(self.validate_dialog)
        self.denominator.textCorrect.connect(self.validate_dialog)
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

        self.validate_dialog()

    @Slot(bool)
    def validate_dialog(self,b=True):
        if self.numerator.is_valid and self.denominator.is_valid:
            self.button.setEnabled(True)
        else:
            self.button.setEnabled(False)

    def compute(self):
        self.setCursor(Qt.BusyCursor)
        if self.sense_combo.currentText() == 'maximize':
            sense = 'Maximum'
        else:
            sense = 'Minimum'
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            solver = re.search('('+'|'.join(avail_solvers)+')',model.solver.interface.__name__)
            if solver is not None:
                solver = solver[0]
            sol = yopt(model,
                       obj_num=self.numerator.text(),
                       obj_den=self.denominator.text(),
                       obj_sense=self.sense_combo.currentText(),
                       solver=solver)
            if sol.status == UNBOUNDED and isinf(sol.objective_value):
                self.set_boxes(sol)
                QMessageBox.warning(self, sense+' yield is unbounded. ',
                                    'Yield unbounded. \n'+\
                                    'Parts of the shown example flux distribution can be scaled indefinitely. The numerator "'+\
                                     linexprdict2str(linexpr2dict(self.numerator.text(),self.reac_ids))+'" is unbounded.',)
            elif sol.status == UNBOUNDED and isnan(sol.objective_value):
                self.set_boxes(sol)
                QMessageBox.warning(self, sense+' yield is undefined. ',
                                    'Yield undefined. \n'+\
                                    'The denominator "'+\
                                     linexprdict2str(linexpr2dict(self.denominator.text(),self.reac_ids))+\
                                    '" can take the value 0, as shown in the example flux distibution.',)
            elif sol.status == OPTIMAL:
                self.set_boxes(sol)
                if sol.scalable:
                    txt_scalable = '\nThe shown example flux distribution can be scaled indefinitely.'
                else:
                    txt_scalable = ''
                QMessageBox.information(self, 'Solution',
                                    'Maximum yield ('+linexprdict2str(linexpr2dict(self.numerator.text(),self.reac_ids))+\
                                    ') / ('+linexprdict2str(linexpr2dict(self.denominator.text(),self.reac_ids))+\
                                    '): '+str(round(sol.objective_value,9)) + \
                                    '\nShowing yield-optimal example flux distribution.' + txt_scalable)
            else:
                QMessageBox.warning(self, 'Problem infeasible.',
                                    'The scenario seems to be infeasible.',)
                return
        self.setCursor(Qt.ArrowCursor)
        self.accept()

    def set_boxes(self,sol):
        # write results into comp_values
        idx = 0
        for r in self.reac_ids:
            self.appdata.project.comp_values[r] = (
                float(sol.fluxes[r]), float(sol.fluxes[r]))
            idx = idx+1
        self.appdata.project.comp_values_type = 0
        self.central_widget.update()