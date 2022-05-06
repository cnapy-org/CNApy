"""The yield space plot dialog"""

import matplotlib.pyplot as plt
from random import randint
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (QDialog, QHBoxLayout, QLabel, QGroupBox,
                            QPushButton, QVBoxLayout, QFrame)
import numpy
from cnapy.utils import QComplReceivLineEdit, QHSeperationLine
from straindesign import linexpr2dict, linexprdict2str, yopt
from straindesign.names import *

class YieldSpaceDialog(QDialog):
    """A dialog to create yield space plots"""

    def __init__(self, appdata):
        QDialog.__init__(self)
        self.setWindowTitle("Yield space plotting")

        self.appdata = appdata

        numr = len(self.appdata.project.cobra_py_model.reactions)
        self.reac_ids = self.appdata.project.cobra_py_model.reactions.list_attr("id")
        if numr > 2:
            r1 = self.appdata.project.cobra_py_model.reactions[randint(0,numr-1)].id
            r2 = self.appdata.project.cobra_py_model.reactions[randint(0,numr-1)].id
            r3 = self.appdata.project.cobra_py_model.reactions[randint(0,numr-1)].id
            r4 = self.appdata.project.cobra_py_model.reactions[randint(0,numr-1)].id
        else:
            r1 = 'r_product_horz'
            r2 = 'r_substrate_horz'
            r3 = 'r_product_vert'
            r4 = 'r_substrate_vert'

        self.layout = QVBoxLayout()
        text = QLabel('Specify the yield terms that should be used for the horizontal and vertical axis.\n'+
                      'Keep in mind that exchange reactions are often defined in the direction of export.\n'+
                      'Consider changing signs.')
        self.layout.addWidget(text)
        
        editor_layout = QHBoxLayout()
        # Define for horizontal axis
        horz_groupbox = QGroupBox('Horizontal axis')
        horz_num_den_layout = QVBoxLayout()
        self.horz_numerator = QComplReceivLineEdit(self,self.reac_ids,check=True)
        self.horz_numerator.setPlaceholderText('numerator (e.g. 1.0 '+r1+')')
        self.horz_denominator = QComplReceivLineEdit(self,self.reac_ids,check=True)
        self.horz_denominator.setPlaceholderText('denominator (e.g. 1.0 '+r2+')')
        horz_num_den_layout.addWidget(self.horz_numerator)
        sep = QHSeperationLine()
        sep.setFrameShadow(QFrame.Plain)
        sep.setLineWidth(3)
        horz_num_den_layout.addWidget(sep)
        horz_num_den_layout.addWidget(self.horz_denominator)
        horz_groupbox.setLayout(horz_num_den_layout)
        editor_layout.addWidget(horz_groupbox)
        # Define for vertical axis
        vert_groupbox = QGroupBox('Vertical axis')
        vert_num_den_layout = QVBoxLayout()
        self.vert_numerator = QComplReceivLineEdit(self,self.reac_ids,check=True)
        self.vert_numerator.setPlaceholderText('numerator (e.g. '+r3+')')
        self.vert_denominator = QComplReceivLineEdit(self,self.reac_ids,check=True)
        self.vert_denominator.setPlaceholderText('denominator (e.g. '+r4+')')
        vert_num_den_layout.addWidget(self.vert_numerator)
        sep = QHSeperationLine()
        sep.setFrameShadow(QFrame.Plain)
        sep.setLineWidth(3)
        vert_num_den_layout.addWidget(sep)
        vert_num_den_layout.addWidget(self.vert_denominator)
        vert_groupbox.setLayout(vert_num_den_layout)
        editor_layout.addWidget(vert_groupbox)
        self.layout.addItem(editor_layout)
        # buttons
        button_layout = QHBoxLayout()
        self.button = QPushButton("Plot")
        self.cancel = QPushButton("Close")
        button_layout.addWidget(self.button)
        button_layout.addWidget(self.cancel)
        self.layout.addItem(button_layout)
        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

    def compute(self):
        self.setCursor(Qt.BusyCursor)
        with self.appdata.project.cobra_py_model as model:
            self.appdata.project.load_scenario_into_model(model)
            horz_axis = '('+self.horz_numerator.text()+') / ('+self.horz_denominator.text()+')'
            vert_axis = '('+self.vert_numerator.text()+') / ('+self.vert_denominator.text()+')'
            horz_num = linexpr2dict(self.horz_numerator.text(),self.reac_ids)
            horz_den = linexpr2dict(self.horz_denominator.text(),self.reac_ids)
            vert_num = linexpr2dict(self.vert_numerator.text(),self.reac_ids)
            vert_den = linexpr2dict(self.vert_denominator.text(),self.reac_ids)
            # get outmost points
            sol_hmin = yopt(model,obj_num=horz_num,obj_den=horz_den,obj_sense='minimize')
            sol_hmax = yopt(model,obj_num=horz_num,obj_den=horz_den,obj_sense='maximize')
            sol_vmin = yopt(model,obj_num=vert_num,obj_den=vert_den,obj_sense='minimize')
            sol_vmax = yopt(model,obj_num=vert_num,obj_den=vert_den,obj_sense='maximize')
            hmin = min((0,sol_hmin.objective_value))
            hmax = max((0,sol_hmax.objective_value))
            vmin = min((0,sol_vmin.objective_value))
            vmax = max((0,sol_vmax.objective_value))
            # abort if any of the yields are unbounded or undefined
            unbnd = [i+1 for i,v in enumerate([sol_hmin,sol_hmax,sol_vmin,sol_vmax]) if v.status == UNBOUNDED]
            if any(unbnd):
                raise Exception('One of the specified yields is unbounded or undefined. Yield space cannot be generated.')
            # compute points
            points = 50
            vals = numpy.zeros((points, 3))
            vals[:, 0] = numpy.linspace(sol_hmin.objective_value, sol_hmax.objective_value, num=points)
            var = numpy.linspace(sol_hmin.objective_value, sol_hmax.objective_value, num=points)
            lb = numpy.full(points, numpy.nan)
            ub = numpy.full(points, numpy.nan)
            for i in range(points):
                constr = [{**horz_num, **{k:-v*vals[i, 0] for k,v in horz_den.items()}},'=',0]
                sol_vmin = yopt(model,constraints=constr,obj_num=vert_num,obj_den=vert_den,obj_sense='minimize')
                lb[i] = sol_vmin.objective_value
                sol_vmax = yopt(model,constraints=constr,obj_num=vert_num,obj_den=vert_den,obj_sense='maximize')
                ub[i] = sol_vmax.objective_value

            _fig, axes = plt.subplots()
            axes.set_xlabel(horz_axis)
            axes.set_ylabel(vert_axis)
            axes.set_xlim(hmin*1.05,hmax*1.05)
            axes.set_ylim(vmin*1.05,vmax*1.05)
            x = [v for v in var] + [v for v in reversed(var)]
            y = [v for v in lb] + [v for v in reversed(ub)]
            if lb[0] != ub[0]:
                x.extend([var[0], var[0]])
                y.extend([lb[0], ub[0]])

            plt.fill(x, y)
            plt.show()

        self.appdata.window.centralWidget().show_bottom_of_console()

        self.setCursor(Qt.ArrowCursor)
