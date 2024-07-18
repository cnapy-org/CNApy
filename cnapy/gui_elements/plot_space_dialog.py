"""The flux space plot dialog"""

from random import randint
from qtpy.QtCore import Qt
from qtpy.QtWidgets import (QDialog, QHBoxLayout, QLabel, QMessageBox, QGroupBox, QComboBox, QLayout,
                            QPushButton, QVBoxLayout, QFrame, QCheckBox,QLineEdit)
from cnapy.utils import QComplReceivLineEdit, QHSeperationLine
from straindesign import plot_flux_space
from straindesign.names import *

class PlotSpaceDialog(QDialog):
    """A dialog to create Flux space plots"""

    def __init__(self, appdata):
        QDialog.__init__(self)
        self.setWindowTitle("Plot phase plane/yield space")
        self.setMinimumWidth(500)

        self.appdata = appdata

        numr = len(self.appdata.project.cobra_py_model.reactions)
        self.r = ["" for _ in range(6)]
        if numr > 5:
            self.r = [self.appdata.project.cobra_py_model.reactions[randint(0,numr-1)].id for _ in self.r]
        else:
            self.r[0] = 'r_product_x'
            self.r[1] = 'r_substrate_x'
            self.r[2] = 'r_product_y'
            self.r[3] = 'r_substrate_y'
            self.r[4] = 'r_product_z'
            self.r[5] = 'r_substrate_z'

        self.layout = QVBoxLayout()
        self.layout.setAlignment(Qt.Alignment(Qt.AlignTop^Qt.AlignLeft))
        self.layout.setSizeConstraint(QLayout.SetFixedSize)
        text = QLabel('Specify the yield terms that should be used for the different axes.\n'+
                      'Keep in mind that exchange reactions are often defined in the direction of export.\n'+
                      'Consider changing signs.')
        self.layout.addWidget(text)
        self.third_axis = QCheckBox('3D plot')
        self.third_axis.clicked.connect(self.box_3d_clicked)
        self.layout.addWidget(self.third_axis)
        points_layout = QHBoxLayout()
        points_layout.setAlignment(Qt.AlignLeft)
        numpoints_text = QLabel('Number of datapoints:')
        self.numpoints = QLineEdit('20')
        self.numpoints.setMaximumWidth(50)
        points_layout.addWidget(numpoints_text)
        points_layout.addWidget(self.numpoints)
        self.layout.addLayout(points_layout)

        editor_layout = QHBoxLayout()
        # Define for horizontal axis
        x_groupbox = QGroupBox('x-axis')
        x_num_den_layout = QVBoxLayout()
        self.x_combobox = QComboBox()
        self.x_combobox.insertItem(0,'rate')
        self.x_combobox.insertItem(1,'yield')
        self.x_combobox.currentTextChanged.connect(self.x_combo_changed)
        x_num_den_layout.addWidget(self.x_combobox)
        self.x_numerator = QComplReceivLineEdit(self, self.appdata.project.reaction_ids, check=True)
        self.x_numerator.setPlaceholderText('flux rate or expression (e.g. 1.0 '+self.r[0]+')')
        self.x_denominator = QComplReceivLineEdit(self, self.appdata.project.reaction_ids, check=True)
        self.x_denominator.setPlaceholderText('denominator (e.g. 1.0 '+self.r[1]+')')
        x_num_den_layout.addWidget(self.x_numerator)
        self.x_denominator.setHidden(True)
        self.x_sep = QHSeperationLine()
        self.x_sep.setFrameShadow(QFrame.Plain)
        self.x_sep.setLineWidth(2)
        self.x_sep.setHidden(True)
        x_num_den_layout.addWidget(self.x_sep)
        x_num_den_layout.addWidget(self.x_denominator)
        x_num_den_layout.setAlignment(Qt.AlignTop)
        x_groupbox.setLayout(x_num_den_layout)
        x_groupbox.setMinimumWidth(230)
        editor_layout.addWidget(x_groupbox)
        # Define for vertical axis
        y_groupbox = QGroupBox('y-axis')
        y_num_den_layout = QVBoxLayout()
        self.y_combobox = QComboBox()
        self.y_combobox.insertItem(0,'rate')
        self.y_combobox.insertItem(1,'yield')
        self.y_combobox.currentTextChanged.connect(self.y_combo_changed)
        y_num_den_layout.addWidget(self.y_combobox)
        self.y_numerator = QComplReceivLineEdit(self, self.appdata.project.reaction_ids, check=True)
        self.y_numerator.setPlaceholderText('flux rate or expression (e.g. '+self.r[2]+')')
        self.y_denominator = QComplReceivLineEdit(self, self.appdata.project.reaction_ids, check=True)
        self.y_denominator.setPlaceholderText('denominator (e.g. '+self.r[3]+')')
        y_num_den_layout.addWidget(self.y_numerator)
        self.y_denominator.setHidden(True)
        self.y_sep = QHSeperationLine()
        self.y_sep.setFrameShadow(QFrame.Plain)
        self.y_sep.setLineWidth(2)
        self.y_sep.setHidden(True)
        y_num_den_layout.addWidget(self.y_sep)
        y_num_den_layout.addWidget(self.y_denominator)
        y_groupbox.setLayout(y_num_den_layout)
        y_groupbox.setMinimumWidth(230)
        y_num_den_layout.setAlignment(Qt.AlignTop)
        editor_layout.addWidget(y_groupbox)
        # Define for longitudinal axis
        self.z_groupbox = QGroupBox('z-axis')
        z_num_den_layout = QVBoxLayout()
        self.z_combobox = QComboBox()
        self.z_combobox.insertItem(0,'rate')
        self.z_combobox.insertItem(1,'yield')
        self.z_combobox.currentTextChanged.connect(self.z_combo_changed)
        z_num_den_layout.addWidget(self.z_combobox)
        self.z_numerator = QComplReceivLineEdit(self, self.appdata.project.reaction_ids, check=True)
        self.z_numerator.setPlaceholderText('flux rate or expression (e.g. '+self.r[4]+')')
        self.z_denominator = QComplReceivLineEdit(self, self.appdata.project.reaction_ids, check=True)
        self.z_denominator.setPlaceholderText('denominator (e.g. '+self.r[5]+')')
        z_num_den_layout.addWidget(self.z_numerator)
        self.z_denominator.setHidden(True)
        self.z_sep = QHSeperationLine()
        self.z_sep.setFrameShadow(QFrame.Plain)
        self.z_sep.setLineWidth(2)
        self.z_sep.setHidden(True)
        z_num_den_layout.addWidget(self.z_sep)
        z_num_den_layout.addWidget(self.z_denominator)
        self.z_groupbox.setLayout(z_num_den_layout)
        self.z_groupbox.setMinimumWidth(230)
        z_num_den_layout.setAlignment(Qt.AlignTop)
        self.z_groupbox.setHidden(True)
        editor_layout.addWidget(self.z_groupbox)
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
            if self.third_axis.isChecked():
                axes = [[] for _ in range(3)]
            else:
                axes = [[] for _ in range(2)]
            if self.x_combobox.currentText() == 'yield':
                axes[0] = (self.x_numerator.text(),self.x_denominator.text())
            else:
                axes[0] = (self.x_numerator.text())
            if self.y_combobox.currentText() == 'yield':
                axes[1] = (self.y_numerator.text(),self.y_denominator.text())
            else:
                axes[1] = (self.y_numerator.text())
            if len(axes) == 3:
                if self.z_combobox.currentText() == 'yield':
                    axes[2] = (self.z_numerator.text(),self.z_denominator.text())
                else:
                    axes[2] = (self.z_numerator.text())
            try:
                plot_flux_space(model,axes,points=int(self.numpoints.text()))
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Error in plot calculation",
                    "Plot space could not be calculated due to the following error:\n"
                    f"{e}"
                )
        self.appdata.window.centralWidget().show_bottom_of_console()
        self.setCursor(Qt.ArrowCursor)

    def box_3d_clicked(self):
        if self.third_axis.isChecked():
            self.z_groupbox.setHidden(False)
        else:
            self.z_groupbox.setHidden(True)
        self.adjustSize()

    def x_combo_changed(self):
        if self.x_combobox.currentText() == 'yield':
            self.x_numerator.setPlaceholderText('numerator (e.g. 1.0 '+self.r[0]+')')
            self.x_sep.setHidden(False)
            self.x_denominator.setHidden(False)
        else:
            self.x_numerator.setPlaceholderText('flux rate or expression (e.g. 1.0 '+self.r[0]+')')
            self.x_sep.setHidden(True)
            self.x_denominator.setHidden(True)
        self.adjustSize()

    def y_combo_changed(self):
        if self.y_combobox.currentText() == 'yield':
            self.y_numerator.setPlaceholderText('numerator (e.g. 1.0 '+self.r[2]+')')
            self.y_sep.setHidden(False)
            self.y_denominator.setHidden(False)
        else:
            self.y_numerator.setPlaceholderText('flux rate or expression (e.g. 1.0 '+self.r[2]+')')
            self.y_sep.setHidden(True)
            self.y_denominator.setHidden(True)
        self.adjustSize()

    def z_combo_changed(self):
        if self.z_combobox.currentText() == 'yield':
            self.z_numerator.setPlaceholderText('numerator (e.g. 1.0 '+self.r[4]+')')
            self.z_sep.setHidden(False)
            self.z_denominator.setHidden(False)
        else:
            self.z_numerator.setPlaceholderText('flux rate or expression (e.g. 1.0 '+self.r[4]+')')
            self.z_sep.setHidden(True)
            self.z_denominator.setHidden(True)
        self.adjustSize()
