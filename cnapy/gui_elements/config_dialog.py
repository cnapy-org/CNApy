"""The cnapy configuration dialog"""
import os

import cnapy.legacy as legacy
import pkg_resources
from cnapy.cnadata import CnaData
from cnapy.legacy import is_matlab_ready, is_octave_ready, restart_cna
from qtpy.QtCore import QSize
from qtpy.QtGui import QDoubleValidator, QIcon, QIntValidator, QPalette
from qtpy.QtWidgets import (QColorDialog, QComboBox, QDialog, QFileDialog,
                            QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                            QPushButton, QVBoxLayout)

cross_svg = pkg_resources.resource_filename('cnapy', 'data/cross.svg')
cross_icon = QIcon(cross_svg)

check_svg = pkg_resources.resource_filename('cnapy', 'data/check.svg')
check_icon = QIcon(check_svg)


class ConfigDialog(QDialog):
    """A dialog to set values in cnapy-config.txt"""

    def __init__(self, appdata: CnaData):
        cross = cross_icon.pixmap(QSize(32, 32))
        check = check_icon.pixmap(QSize(32, 32))

        QDialog.__init__(self)
        self.appdata = appdata
        self.layout = QVBoxLayout()

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
            "Choose path to octave executable")
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

        h2 = QHBoxLayout()
        label = QLabel("Default color for values in a scenario:")
        h2.addWidget(label)
        self.scen_color_btn = QPushButton()
        self.scen_color_btn.setFixedWidth(100)
        palette = self.scen_color_btn.palette()
        palette.setColor(QPalette.Button, self.appdata.Scencolor)
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
        palette.setColor(QPalette.Button, self.appdata.Compcolor)
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
        palette.setColor(QPalette.Button, self.appdata.SpecialColor1)
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
        palette.setColor(QPalette.Button, self.appdata.SpecialColor2)
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
        palette.setColor(QPalette.Button, self.appdata.Defaultcolor)
        self.default_color_btn.setPalette(palette)
        h6.addWidget(self.default_color_btn)
        self.layout.addItem(h6)

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

        h9 = QHBoxLayout()
        label = QLabel("Matlab/Octave engine:")
        h9.addWidget(label)
        self.default_engine = QComboBox()
        self.default_engine.insertItem(1, "Matlab")
        self.default_engine.insertItem(2, "Octave")
        if self.appdata.default_engine == "octave":
            self.default_engine.setCurrentIndex(1)
        else:
            self.default_engine.setCurrentIndex(0)
        h9.addWidget(self.default_engine)
        self.layout.addItem(h9)

        l2 = QHBoxLayout()
        self.button = QPushButton("Apply Changes")
        self.cancel = QPushButton("Cancel")
        l2.addWidget(self.button)
        l2.addWidget(self.cancel)
        self.layout.addItem(l2)
        self.setLayout(self.layout)

        # Connecting the signal
        self.choose_ml_path_btn.clicked.connect(self.choose_ml_path)
        self.choose_oc_exe_btn.clicked.connect(self.choose_oc_exe)
        self.choose_cna_path_btn.clicked.connect(self.choose_cna_path)
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
        self.matlab_path.setText(directory)
        pass

    def choose_oc_exe(self):
        dialog = QFileDialog(self, directory=self.oc_exe.text())
        dialog.setFileMode(QFileDialog.DirectoryOnly)
        directory: str = dialog.getExistingDirectory()
        self.oc_exe.setText(directory)

        if os.path.isfile(directory):
            os.environ['OCTAVE_EXECUTABLE'] = directory

        self.check_octave()

    def check_all(self):
        self.check_octave()
        self.check_cna()

    def check_octave(self):
        cross = cross_icon.pixmap(QSize(32, 32))
        check = check_icon.pixmap(QSize(32, 32))
        if is_octave_ready():
            self.oc_label.setPixmap(check)
        else:
            self.oc_label.setPixmap(cross)

    def check_matlab(self):
        cross = cross_icon.pixmap(QSize(32, 32))
        check = check_icon.pixmap(QSize(32, 32))
        if is_matlab_ready():
            self.ml_label.setPixmap(check)
        else:
            self.ml_label.setPixmap(cross)

    def choose_cna_path(self):
        dialog = QFileDialog(self, directory=self.cna_path.text())
        dialog.setFileMode(QFileDialog.DirectoryOnly)
        directory: str = dialog.getExistingDirectory()
        self.cna_path.setText(directory)
        self.check_cna()
        pass

    def check_cna(self):
        cross = cross_icon.pixmap(QSize(32, 32))
        check = check_icon.pixmap(QSize(32, 32))
        if restart_cna(self.cna_path.text()):
            self.cna_label.setPixmap(check)
        else:
            self.cna_label.setPixmap(cross)

    def choose_scen_color(self):
        dialog = QColorDialog(self)
        color: str = dialog.getColor()

        palette = self.scen_color_btn.palette()
        palette.setColor(QPalette.Button, color)
        self.scen_color_btn.setPalette(palette)
        pass

    def choose_comp_color(self):
        dialog = QColorDialog(self)
        color: str = dialog.getColor()

        palette = self.comp_color_btn.palette()
        palette.setColor(QPalette.Button, color)
        self.comp_color_btn.setPalette(palette)
        pass

    def choose_spec1_color(self):
        dialog = QColorDialog(self)
        color: str = dialog.getColor()

        palette = self.spec1_color_btn.palette()
        palette.setColor(QPalette.Button, color)
        self.spec1_color_btn.setPalette(palette)
        pass

    def choose_spec2_color(self):
        dialog = QColorDialog(self)
        color: str = dialog.getColor()

        palette = self.spec2_color_btn.palette()
        palette.setColor(QPalette.Button, color)
        self.spec2_color_btn.setPalette(palette)
        pass

    def choose_default_color(self):
        dialog = QColorDialog(self)
        color: str = dialog.getColor()

        palette = self.default_color_btn.palette()
        palette.setColor(QPalette.Button, color)
        self.default_color_btn.setPalette(palette)
        pass

    def apply(self):
        self.appdata.matlab_path = self.matlab_path.text()
        self.appdata.octave_executable = self.oc_exe.text()
        self.appdata.cna_path = self.cna_path.text()
        if is_matlab_ready() or is_octave_ready():
            if restart_cna(self.appdata.cna_path):
                self.appdata.window.efm_action.setEnabled(True)
                self.appdata.window.mcs_action.setEnabled(True)
            else:
                self.appdata.window.efm_action.setEnabled(False)
                self.appdata.window.mcs_action.setEnabled(False)

        palette = self.scen_color_btn.palette()
        self.appdata.Scencolor = palette.color(QPalette.Button)

        palette = self.comp_color_btn.palette()
        self.appdata.Compcolor = palette.color(QPalette.Button)

        palette = self.spec1_color_btn.palette()
        self.appdata.SpecialColor1 = palette.color(QPalette.Button)

        palette = self.spec2_color_btn.palette()
        self.appdata.SpecialColor2 = palette.color(QPalette.Button)

        palette = self.default_color_btn.palette()
        self.appdata.Defaultcolor = palette.color(QPalette.Button)

        self.appdata.rounding = int(self.rounding.text())
        self.appdata.abs_tol = float(self.abs_tol.text())

        if self.default_engine.currentIndex() == 0:
            if is_matlab_ready():
                self.appdata.default_engine = "matlab"
                legacy.use_matlab()
            else:
                QMessageBox.information(
                    self, 'MATLAB engine not found!', 'See instructions for installing the matlab python engine!')
        elif self.default_engine.currentIndex() == 1:
            if is_octave_ready():
                self.appdata.default_engine = "octave"
                legacy.use_octave()
            else:
                QMessageBox.information(
                    self, 'Octave engine not found!', 'Install Octave version 5.0 or higher!')

        self.appdata.first_run = False
        import configparser
        parser = configparser.ConfigParser()
        parser.add_section('cnapy-config')
        parser.set('cnapy-config', 'first_run', '0')
        parser.set('cnapy-config', 'matlab_path', self.appdata.matlab_path)
        parser.set('cnapy-config', 'OCTAVE_EXECUTABLE',
                   self.appdata.octave_executable)
        parser.set('cnapy-config', 'cna_path', self.appdata.cna_path)
        parser.set('cnapy-config', 'scen_color',
                   str(self.appdata.Scencolor.rgb()))
        parser.set('cnapy-config', 'comp_color',
                   str(self.appdata.Compcolor.rgb()))
        parser.set('cnapy-config', 'spec1_color',
                   str(self.appdata.SpecialColor1.rgb()))
        parser.set('cnapy-config', 'spec2_color',
                   str(self.appdata.SpecialColor2.rgb()))
        parser.set('cnapy-config', 'default_color',
                   str(self.appdata.Defaultcolor.rgb()))
        parser.set('cnapy-config', 'rounding',
                   str(self.appdata.rounding))
        parser.set('cnapy-config', 'abs_tol',
                   str(self.appdata.abs_tol))
        parser.set('cnapy-config', 'default_engine',
                   str(self.appdata.default_engine))

        try:
            fp = open(self.appdata.conf_path, "w")
        except:
            import os

            import appdirs
            os.makedirs(appdirs.user_config_dir(
                "cnapy", roaming=True, appauthor=False))
            fp = open(self.appdata.conf_path, "w")

        parser.write(fp)
        fp.close()

        self.accept()
