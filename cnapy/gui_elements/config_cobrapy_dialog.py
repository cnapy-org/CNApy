"""The COBRApy configuration dialog"""
import configparser
import io
import os
import traceback
from tempfile import TemporaryDirectory

import appdirs
from qtpy.QtCore import QSize
from qtpy.QtGui import QDoubleValidator, QIntValidator
from qtpy.QtWidgets import (QMessageBox, QComboBox, QDialog, QFileDialog,
                            QHBoxLayout, QLabel, QLineEdit, QPushButton,
                            QVBoxLayout)
import cnapy.resources
from cnapy.cnadata import CnaData
# from optlang.util import list_available_solvers
from cobra.util.solver import interface_to_str, solvers
from cobra import Configuration
from multiprocessing import cpu_count

class ConfigCobrapyDialog(QDialog):
    """A dialog to set values in cobrapy-config.txt"""

    def __init__(self, appdata: CnaData):
        QDialog.__init__(self)
        self.setWindowTitle("Configure COBRApy")

        self.appdata = appdata
        self.layout = QVBoxLayout()

        # allow MILP solvers only?
        # avail_solvers = [s for s, t in list_available_solvers().items() if t and s != 'SCIPY'] # currently all upper case strings; SCIPY currently not even usable for FBA
        # avail_solvers_lower_case = list(map(str.lower, avail_solvers)) # for use with interface_to_str which gives lower case
        avail_solvers = list(set(solvers.keys()) - {'scipy'}) # SCIPY currently not even usable for FBA

        h2 = QHBoxLayout()
        label = QLabel("Default solver:\n(set when loading a model)")
        h2.addWidget(label)
        self.default_solver = QComboBox()
        self.default_solver.addItems(avail_solvers)
        # self.default_solver.setCurrentIndex(avail_solvers_lower_case.index(interface_to_str(Configuration().solver)))
        self.default_solver.setCurrentIndex(avail_solvers.index(interface_to_str(Configuration().solver)))
        h2.addWidget(self.default_solver)
        self.layout.addItem(h2)

        h9 = QHBoxLayout()
        label = QLabel("Solver for current model:")
        h9.addWidget(label)
        self.current_solver = QComboBox()
        self.current_solver.addItems(avail_solvers)
        # self.current_solver.setCurrentIndex(avail_solvers_lower_case.index(interface_to_str(appdata.project.cobra_py_model.problem)))
        self.current_solver.setCurrentIndex(avail_solvers.index(interface_to_str(appdata.project.cobra_py_model.problem)))
        h9.addWidget(self.current_solver)
        self.layout.addItem(h9)

        h7 = QHBoxLayout()
        label = QLabel(
            "Number of processes for multiprocessing (e.g. FVA):")
        h7.addWidget(label)
        self.num_processes = QLineEdit()
        self.num_processes.setFixedWidth(100)
        self.num_processes.setText(str(Configuration().processes))
        validator = QIntValidator(1, cpu_count(), self)
        self.num_processes.setValidator(validator)
        h7.addWidget(self.num_processes)
        self.layout.addItem(h7)

        h8 = QHBoxLayout()
        label = QLabel(
            "Default tolerance:\n(set when loading a model)")
        h8.addWidget(label)
        self.default_tolerance = QLineEdit()
        self.default_tolerance.setFixedWidth(100)
        self.default_tolerance.setText(str(Configuration().tolerance))
        validator = QDoubleValidator(self)
        validator.setBottom(1e-9) # probably a reasonable consensus value
        self.default_tolerance.setValidator(validator)
        h8.addWidget(self.default_tolerance)
        self.layout.addItem(h8)

        h10 = QHBoxLayout()
        label = QLabel(
            "Tolerance for current model:")
        h10.addWidget(label)
        self.current_tolerance = QLineEdit()
        self.current_tolerance.setFixedWidth(100)
        self.current_tolerance.setText(str(self.appdata.project.cobra_py_model.tolerance))
        validator = QDoubleValidator(self)
        validator.setBottom(0)
        self.current_tolerance.setValidator(validator)
        h10.addWidget(self.current_tolerance)
        self.layout.addItem(h10)

        l2 = QHBoxLayout()
        self.button = QPushButton("Apply Changes")
        self.cancel = QPushButton("Close")
        l2.addWidget(self.button)
        l2.addWidget(self.cancel)
        self.layout.addItem(l2)
        self.setLayout(self.layout)

        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.apply)


    def apply(self):
        # self.appdata.project.cobra_py_model.solver = str.lower(self.current_solver.currentText())
        Configuration().solver = self.default_solver.currentText()
        Configuration().processes = int(self.num_processes.text())
        try:
            val = float(self.default_tolerance.text())
            if 1e-9 <= val <= 0.1:
                Configuration().tolerance = val
            else:
                raise
        except:
            QMessageBox.critical(self, "Cannot set default tolerance", "Choose a value between 0.1 and 1e-9 as default tolerance.")
            return
        try:
            self.appdata.project.cobra_py_model.solver = self.current_solver.currentText()
            self.appdata.project.cobra_py_model.tolerance = float(self.current_tolerance.text())
        except:
            QMessageBox.critical(self, "Cannot set current solver/tolerance", "Check that the current tolerance is appropriate for the selected solver.")
            return

        parser = configparser.ConfigParser()
        parser.add_section('cobrapy-config')
        parser.set('cobrapy-config', 'solver', interface_to_str(Configuration().solver))
        parser.set('cobrapy-config', 'processes', str(Configuration().processes))
        parser.set('cobrapy-config', 'tolerance', str(Configuration().tolerance))
        
        try:
            fp = open(self.appdata.cobrapy_conf_path, "w")
        except FileNotFoundError:
            os.makedirs(appdirs.user_config_dir(
                "cnapy", roaming=True, appauthor=False))
            fp = open(self.appdata.cobrapy_conf_path, "w")

        parser.write(fp)
        fp.close()

        self.accept()
