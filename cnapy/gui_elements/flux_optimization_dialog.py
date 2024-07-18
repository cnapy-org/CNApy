"""The cnapy flux optimization dialog"""
from random import randint
from numpy import isinf
import re
from qtpy.QtCore import Qt, Slot
from qtpy.QtWidgets import (QDialog, QHBoxLayout, QLabel, QComboBox,
                            QMessageBox, QPushButton, QVBoxLayout)

from cnapy.appdata import AppData
from cnapy.gui_elements.central_widget import CentralWidget
from cnapy.utils import QComplReceivLineEdit
from straindesign import fba, linexpr2dict, linexprdict2str, avail_solvers
from straindesign.names import *

class FluxOptimizationDialog(QDialog):
    """A dialog to perform flux optimization"""

    def __init__(self, appdata: AppData, central_widget: CentralWidget):
        QDialog.__init__(self)
        self.setWindowTitle("Flux optimization")

        self.appdata = appdata
        self.central_widget = central_widget

        numr = len(self.appdata.project.cobra_py_model.reactions)
        self.reac_ids = self.appdata.project.reaction_ids.id_list
        if numr > 1:
            r1 = self.appdata.project.cobra_py_model.reactions[randint(0,numr-1)].id
        else:
            r1 = 'r_product'

        self.layout = QVBoxLayout()
        l = QLabel("Maximize (or minimize) a linear flux expression with reaction identifiers and \n"+ \
                   "(optionally) coefficients. Keep in mind that exchange reactions are often defined \n"+\
                   "in the direction of export. Consider changing coefficient signs.")
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
        flux_expr_layout = QVBoxLayout()
        self.expr = QComplReceivLineEdit(self, self.appdata.project.reaction_ids, check=True)
        self.expr.setPlaceholderText('flux expression (e.g. 1.0 '+r1+')')
        flux_expr_layout.addWidget(self.expr)
        editor_layout.addItem(flux_expr_layout)
        # close_bracket = QLabel(')')
        # font = close_bracket.font()
        # font.setPointSize(30)
        # close_bracket.setFont(font)
        # editor_layout.addWidget(close_bracket)
        self.layout.addItem(editor_layout)

        l3 = QHBoxLayout()
        self.button = QPushButton("Compute")
        self.cancel = QPushButton("Close")
        l3.addWidget(self.button)
        l3.addWidget(self.cancel)
        self.layout.addItem(l3)
        self.setLayout(self.layout)

        # Connecting the signal
        self.expr.textCorrect.connect(self.validate_dialog)
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

        self.validate_dialog()

    @Slot(bool)
    def validate_dialog(self,b=True):
        if self.expr.is_valid:
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
            sol = fba(model,
                       obj=self.expr.text(),
                       obj_sense=self.sense_combo.currentText())
            if sol.status == UNBOUNDED and isinf(sol.objective_value):
                self.set_boxes(sol)
                QMessageBox.warning(self, sense+' unbounded. ',
                                    'Flux expression "'+linexprdict2str(linexpr2dict(self.expr.text(),self.reac_ids))+\
                                    '" is unbounded. \nParts of the shown example flux distribution can be scaled indefinitely.',)
            elif sol.status == OPTIMAL:
                self.set_boxes(sol)
                QMessageBox.information(self, 'Solution',
                                    'Optimum ('+linexprdict2str(linexpr2dict(self.expr.text(),self.reac_ids))+\
                                    '): '+str(round(sol.objective_value,9)) + \
                                    '\nShowing optimal example flux distribution.')
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
