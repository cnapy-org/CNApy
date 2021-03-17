"""The cnapy configuration dialog"""
import configparser
import io
import os
import traceback
from tempfile import TemporaryDirectory

import appdirs
from qtpy.QtCore import QSize
from qtpy.QtGui import QDoubleValidator, QIcon, QIntValidator, QPalette
from qtpy.QtWidgets import (QColorDialog, QComboBox, QDialog, QFileDialog,
                            QHBoxLayout, QLabel, QLineEdit, QPushButton,
                            QVBoxLayout)
import cnapy.resources
from cnapy.cnadata import CnaData
from cnapy.legacy import try_cna, try_matlab_engine, try_octave_engine


class ConfigDialog(QDialog):
    """A dialog to set values in cnapy-config.txt"""

    def __init__(self, appdata: CnaData):
        cross_icon = QIcon(":/icons/cross.png")
        cross = cross_icon.pixmap(QSize(32, 32))

        QDialog.__init__(self)
        self.setWindowTitle("Configure CNApy")

        self.appdata = appdata
        self.oeng = appdata.octave_engine
        self.meng = appdata.matlab_engine
        self.layout = QVBoxLayout()

        descr = QLabel("\
            Some functionalities in CNApy need a working CNA installation.\n \
            To use CNA you need either Matlab >= R2019 or Octave >= 5 .\n \
            Below you can choose a Matlab directory or the Octave executable.\n \
            Only if one of the engines is green your CNA directory can be validated.")
        self.layout.addWidget(descr)
        ml = QHBoxLayout()
        label = QLabel("Matlab")
        label.setFixedWidth(100)
        ml.addWidget(label)
        self.ml_label = QLabel()
        self.ml_label.setPixmap(cross)
        self.ml_label.setFixedWidth(100)
        ml.addWidget(self.ml_label)
        self.choose_ml_path_btn = QPushButton(
            "Choose path to Matlab engine")
        self.choose_ml_path_btn.setFixedWidth(300)
        ml.addWidget(self.choose_ml_path_btn)
        label2 = QLabel("")
        label2.setFixedWidth(30)
        ml.addWidget(label2)
        self.matlab_path = QLabel()
        self.matlab_path.setMinimumWidth(200)
        self.matlab_path.setText(self.appdata.matlab_path)
        ml.addWidget(self.matlab_path)

        self.layout.addItem(ml)

        oc = QHBoxLayout()
        label = QLabel("Octave")
        label.setFixedWidth(100)
        oc.addWidget(label)
        self.oc_label = QLabel()
        self.oc_label.setPixmap(cross)
        self.oc_label.setFixedWidth(100)
        oc.addWidget(self.oc_label)

        self.choose_oc_exe_btn = QPushButton(
            "Choose Octave executable")
        self.choose_oc_exe_btn.setFixedWidth(300)
        oc.addWidget(self.choose_oc_exe_btn)

        label2 = QLabel("")
        label2.setFixedWidth(30)
        oc.addWidget(label2)

        self.oc_exe = QLabel()
        self.oc_exe.setText(self.appdata.octave_executable)
        self.oc_exe.setMinimumWidth(200)
        oc.addWidget(self.oc_exe)

        self.layout.addItem(oc)

        cna_l = QHBoxLayout()
        label = QLabel("CNA")
        label.setFixedWidth(100)
        cna_l.addWidget(label)
        self.cna_label = QLabel()
        self.cna_label.setPixmap(cross)
        self.cna_label.setFixedWidth(100)
        cna_l.addWidget(self.cna_label)
        self.choose_cna_path_btn = QPushButton("Choose CNA directory")
        self.choose_cna_path_btn.setFixedWidth(300)
        cna_l.addWidget(self.choose_cna_path_btn)
        label2 = QLabel("")
        label2.setFixedWidth(30)
        cna_l.addWidget(label2)

        self.cna_path = QLabel()
        self.cna_path.setMinimumWidth(200)
        self.cna_path.setText(self.appdata.cna_path)
        cna_l.addWidget(self.cna_path)
        self.layout.addItem(cna_l)

        h9 = QHBoxLayout()
        label = QLabel("Selected engine:")
        h9.addWidget(label)
        self.selected_engine = QComboBox()
        h9.addWidget(self.selected_engine)
        self.layout.addItem(h9)

        h2 = QHBoxLayout()
        label = QLabel("Default color for values in a scenario:")
        h2.addWidget(label)
        self.scen_color_btn = QPushButton()
        self.scen_color_btn.setFixedWidth(100)
        palette = self.scen_color_btn.palette()
        palette.setColor(QPalette.Button, self.appdata.scen_color)
        self.scen_color_btn.setPalette(palette)
        h2.addWidget(self.scen_color_btn)
        self.layout.addItem(h2)

        h3 = QHBoxLayout()
        label = QLabel(
            "Default color for computed values not part of the scenario:")
        h3.addWidget(label)
        self.comp_color_btn = QPushButton()
        self.comp_color_btn.setFixedWidth(100)
        palette = self.comp_color_btn.palette()
        palette.setColor(QPalette.Button, self.appdata.comp_color)
        self.comp_color_btn.setPalette(palette)
        h3.addWidget(self.comp_color_btn)
        self.layout.addItem(h3)

        h4 = QHBoxLayout()
        label = QLabel(
            "Special Color used for non equal flux bounds:")
        h4.addWidget(label)
        self.spec1_color_btn = QPushButton()
        self.spec1_color_btn.setFixedWidth(100)
        palette = self.spec1_color_btn.palette()
        palette.setColor(QPalette.Button, self.appdata.special_color_1)
        self.spec1_color_btn.setPalette(palette)
        h4.addWidget(self.spec1_color_btn)
        self.layout.addItem(h4)

        h5 = QHBoxLayout()
        label = QLabel(
            "Special Color 2 used for non equal flux bounds that exclude 0:")
        h5.addWidget(label)
        self.spec2_color_btn = QPushButton()
        self.spec2_color_btn.setFixedWidth(100)
        palette = self.spec2_color_btn.palette()
        palette.setColor(QPalette.Button, self.appdata.special_color_2)
        self.spec2_color_btn.setPalette(palette)
        h5.addWidget(self.spec2_color_btn)
        self.layout.addItem(h5)

        h6 = QHBoxLayout()
        label = QLabel(
            "Color used for empty reaction boxes:")
        h6.addWidget(label)
        self.default_color_btn = QPushButton()
        self.default_color_btn.setFixedWidth(100)
        palette = self.default_color_btn.palette()
        palette.setColor(QPalette.Button, self.appdata.default_color)
        self.default_color_btn.setPalette(palette)
        h6.addWidget(self.default_color_btn)
        self.layout.addItem(h6)

        h = QHBoxLayout()
        label = QLabel("Work directory:")
        h.addWidget(label)
        self.work_directory = QPushButton()
        self.work_directory.setText(self.appdata.work_directory)
        h.addWidget(self.work_directory)
        self.layout.addItem(h)

        h7 = QHBoxLayout()
        label = QLabel(
            "Shown number of digits after the decimal point:")
        h7.addWidget(label)
        self.rounding = QLineEdit()
        self.rounding.setFixedWidth(100)
        self.rounding.setText(str(self.appdata.rounding))
        validator = QIntValidator(0, 20, self)
        self.rounding.setValidator(validator)
        h7.addWidget(self.rounding)
        self.layout.addItem(h7)

        h8 = QHBoxLayout()
        label = QLabel(
            "Absolute tolerance used to compare float values in the UI:")
        h8.addWidget(label)
        self.abs_tol = QLineEdit()
        self.abs_tol.setFixedWidth(100)
        self.abs_tol.setText(str(self.appdata.abs_tol))
        validator = QDoubleValidator(self)
        validator.setTop(1)
        self.abs_tol.setValidator(validator)
        h8.addWidget(self.abs_tol)
        self.layout.addItem(h8)

        l2 = QHBoxLayout()
        self.button = QPushButton("Apply Changes")
        self.cancel = QPushButton("Close")
        l2.addWidget(self.button)
        l2.addWidget(self.cancel)
        self.layout.addItem(l2)
        self.setLayout(self.layout)

        # Connecting the signal
        self.choose_ml_path_btn.clicked.connect(self.choose_ml_path)
        self.choose_oc_exe_btn.clicked.connect(self.choose_oc_exe)
        self.choose_cna_path_btn.clicked.connect(self.choose_cna_path)
        self.work_directory.clicked.connect(self.choose_work_directory)
        self.scen_color_btn.clicked.connect(self.choose_scen_color)
        self.comp_color_btn.clicked.connect(self.choose_comp_color)
        self.spec1_color_btn.clicked.connect(self.choose_spec1_color)
        self.spec2_color_btn.clicked.connect(self.choose_spec2_color)
        self.default_color_btn.clicked.connect(self.choose_default_color)
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.apply)

        self.check_all()

    def choose_ml_path(self):
        dialog = QFileDialog(self, directory=self.matlab_path.text())
        dialog.setFileMode(QFileDialog.DirectoryOnly)
        directory: str = dialog.getExistingDirectory()
        if not directory or len(directory) == 0 or not os.path.exists(directory):
            return

        self.matlab_path.setText(directory)
        self.try_install_matlab_engine(directory)
        self.check_matlab()

    def try_install_matlab_engine(self, directory: str):
        try:
            path = os.path.join(directory, 'extern/engines/python')
            cwd = os.getcwd()
            os.chdir(path)
            temp_dir = TemporaryDirectory()
            os.system("python setup.py build --build-base=" +
                      temp_dir.name+' install')
            os.chdir(cwd)
        except FileNotFoundError:
            # no Matlab engine found
            pass

    def choose_oc_exe(self):

        dialog = QFileDialog(self, directory=self.oc_exe.text())
        filename: str = dialog.getOpenFileName(directory=os.getcwd())[0]
        if not filename or len(filename) == 0 or not os.path.exists(filename):
            return

        self.oc_exe.setText(filename)
        if os.path.isfile(filename):
            os.environ['OCTAVE_EXECUTABLE'] = filename
        self.check_octave()

    def check_all(self):
        self.check_octave()
        self.check_matlab()
        self.check_cna()

        self.selected_engine.clear()

        self.selected_engine.addItem("None")
        if self.meng is not None:
            self.selected_engine.addItem("Matlab")
        if self.oeng is not None:
            self.selected_engine.addItem("Octave")

        if self.appdata.selected_engine is None:
            self.selected_engine.setCurrentIndex(0)
        if self.appdata.selected_engine == "matlab":
            self.selected_engine.setCurrentIndex(1)
        if self.appdata.selected_engine == "octave":
            if self.selected_engine.count() == 2:
                self.selected_engine.setCurrentIndex(1)
            elif self.selected_engine.count() == 3:
                self.selected_engine.setCurrentIndex(2)

    def check_octave(self):
        cross_icon = QIcon(":/icons/cross.png")
        cross = cross_icon.pixmap(QSize(32, 32))
        check_icon = QIcon(":/icons/check.png")
        check = check_icon.pixmap(QSize(32, 32))
        self.oeng = try_octave_engine(self.oc_exe.text())
        if self.oeng is not None:
            # disable button if octave is already working
            self.choose_oc_exe_btn.setEnabled(False)
            self.oc_label.setPixmap(check)
        else:
            self.oc_label.setPixmap(cross)

    def check_matlab(self):
        cross_icon = QIcon(":/icons/cross.png")
        cross = cross_icon.pixmap(QSize(32, 32))
        check_icon = QIcon(":/icons/check.png")
        check = check_icon.pixmap(QSize(32, 32))
        # only recheck matlab if necessary
        if self.meng is None:
            self.meng = try_matlab_engine()
        if self.meng is not None:
            # disable button if matlab is already working
            self.choose_ml_path_btn.setEnabled(False)
            self.ml_label.setPixmap(check)
        else:
            self.ml_label.setPixmap(cross)

    def choose_cna_path(self):
        dialog = QFileDialog(self, directory=self.cna_path.text())
        dialog.setFileMode(QFileDialog.DirectoryOnly)
        directory: str = dialog.getExistingDirectory()
        if not directory or len(directory) == 0 or not os.path.exists(directory):
            return

        self.cna_path.setText(directory)
        self.update()
        self.reset_engine()
        self.check_cna()

    def choose_work_directory(self):
        dialog = QFileDialog(self, directory=self.work_directory.text())
        directory: str = dialog.getExistingDirectory()
        if not directory or len(directory) == 0 or not os.path.exists(directory):
            return
        self.work_directory.setText(directory)

    def reset_engine(self):
        # This resets the engines
        if self.oeng is None:
            self.meng = try_matlab_engine()
        else:
            self.oeng = try_octave_engine(self.oc_exe.text())

    def check_cna(self):
        cross_icon = QIcon(":/icons/cross.png")
        cross = cross_icon.pixmap(QSize(32, 32))
        check_icon = QIcon(":/icons/check.png")
        check = check_icon.pixmap(QSize(32, 32))
        qmark_icon = QIcon(":/icons/qmark.png")
        qmark = qmark_icon.pixmap(QSize(32, 32))
        if self.oeng is not None:
            if try_cna(self.oeng, self.cna_path.text()):
                self.cna_label.setPixmap(check)
            else:
                self.cna_label.setPixmap(cross)
        elif self.meng is not None:
            if try_cna(self.meng, self.cna_path.text()):
                self.cna_label.setPixmap(check)
            else:
                self.cna_label.setPixmap(cross)
        else:
            self.cna_label.setPixmap(qmark)

    def choose_scen_color(self):
        palette = self.scen_color_btn.palette()
        initial = palette.color(QPalette.Button)

        dialog = QColorDialog(self)
        color: str = dialog.getColor(initial)
        if color.isValid():
            palette.setColor(QPalette.Button, color)
            self.scen_color_btn.setPalette(palette)

    def choose_comp_color(self):
        palette = self.comp_color_btn.palette()
        initial = palette.color(QPalette.Button)

        dialog = QColorDialog(self)
        color: str = dialog.getColor(initial)
        if color.isValid():
            palette.setColor(QPalette.Button, color)
            self.comp_color_btn.setPalette(palette)

    def choose_spec1_color(self):
        palette = self.spec1_color_btn.palette()
        initial = palette.color(QPalette.Button)

        dialog = QColorDialog(self)
        color: str = dialog.getColor(initial)
        if color.isValid():
            palette.setColor(QPalette.Button, color)
            self.spec1_color_btn.setPalette(palette)

    def choose_spec2_color(self):
        palette = self.spec2_color_btn.palette()
        initial = palette.color(QPalette.Button)

        dialog = QColorDialog(self)
        color: str = dialog.getColor(initial)
        if color.isValid():
            palette.setColor(QPalette.Button, color)
            self.spec2_color_btn.setPalette(palette)

    def choose_default_color(self):
        palette = self.default_color_btn.palette()
        initial = palette.color(QPalette.Button)

        dialog = QColorDialog(self)
        color: str = dialog.getColor(initial)
        if color.isValid():
            palette.setColor(QPalette.Button, color)
            self.default_color_btn.setPalette(palette)

    def apply(self):
        self.appdata.matlab_path = self.matlab_path.text()
        self.appdata.octave_executable = self.oc_exe.text()
        self.appdata.cna_path = self.cna_path.text()
        self.appdata.matlab_engine = self.meng
        self.appdata.octave_engine = self.oeng

        if self.selected_engine.currentText() == "None":
            self.appdata.selected_engine = None
        elif self.selected_engine.currentText() == "Matlab":
            self.appdata.selected_engine = "matlab"
        elif self.selected_engine.currentText() == "Octave":
            self.appdata.selected_engine = "octave"

        self.appdata.select_engine()

        self.appdata.window.disable_enable_dependent_actions()

        self.appdata.work_directory = self.work_directory.text()

        palette = self.scen_color_btn.palette()
        self.appdata.scen_color = palette.color(QPalette.Button)

        palette = self.comp_color_btn.palette()
        self.appdata.comp_color = palette.color(QPalette.Button)

        palette = self.spec1_color_btn.palette()
        self.appdata.special_color_1 = palette.color(QPalette.Button)

        palette = self.spec2_color_btn.palette()
        self.appdata.special_color_2 = palette.color(QPalette.Button)

        palette = self.default_color_btn.palette()
        self.appdata.default_color = palette.color(QPalette.Button)

        self.appdata.rounding = int(self.rounding.text())
        self.appdata.abs_tol = float(self.abs_tol.text())

        parser = configparser.ConfigParser()
        parser.add_section('cnapy-config')
        parser.set('cnapy-config', 'version', self.appdata.version)
        parser.set('cnapy-config', 'matlab_path', self.appdata.matlab_path)
        parser.set('cnapy-config', 'OCTAVE_EXECUTABLE',
                   self.appdata.octave_executable)
        parser.set('cnapy-config', 'work_directory',
                   self.appdata.work_directory)
        parser.set('cnapy-config', 'cna_path', self.appdata.cna_path)
        parser.set('cnapy-config', 'scen_color',
                   str(self.appdata.scen_color.rgb()))
        parser.set('cnapy-config', 'comp_color',
                   str(self.appdata.comp_color.rgb()))
        parser.set('cnapy-config', 'spec1_color',
                   str(self.appdata.special_color_1.rgb()))
        parser.set('cnapy-config', 'spec2_color',
                   str(self.appdata.special_color_2.rgb()))
        parser.set('cnapy-config', 'default_color',
                   str(self.appdata.default_color.rgb()))
        parser.set('cnapy-config', 'rounding',
                   str(self.appdata.rounding))
        parser.set('cnapy-config', 'abs_tol',
                   str(self.appdata.abs_tol))
        parser.set('cnapy-config', 'selected_engine',
                   str(self.appdata.selected_engine))

        try:
            fp = open(self.appdata.conf_path, "w")
        except:

            os.makedirs(appdirs.user_config_dir(
                "cnapy", roaming=True, appauthor=False))
            fp = open(self.appdata.conf_path, "w")

        parser.write(fp)
        fp.close()

        self.accept()
