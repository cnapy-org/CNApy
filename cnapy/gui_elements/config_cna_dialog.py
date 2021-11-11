"""The cnapy configuration dialog"""
import os
from tempfile import TemporaryDirectory

from qtpy.QtCore import Qt, QSize
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (QComboBox, QDialog, QFileDialog,
                            QHBoxLayout, QLabel, QPushButton, QVBoxLayout)
from cnapy.appdata import AppData
from cnapy.legacy import try_cna, try_matlab_engine, try_octave_engine


class ConfigCNADialog(QDialog):
    """A dialog to set values in cnapy-config.txt"""

    def __init__(self, appdata: AppData):
        QDialog.__init__(self)
        self.setWindowTitle("Configure CNA bridge")

        cross_icon = QIcon(":/icons/cross.png")
        cross = cross_icon.pixmap(QSize(32, 32))

        self.appdata = appdata
        self.oeng = appdata.octave_engine
        self.meng = appdata.matlab_engine
        self.layout = QVBoxLayout()
        self.cna_ok = False

        descr = QLabel(
            "Some functionalities in CNApy need a working CNA installation. " \
            "To use CNA you need either Matlab >= R2019 or Octave >= 5.\n" \
            "Below you can choose a Matlab directory or the Octave executable. "\
            "Only if one of the engines is green your CNA directory can be validated.")
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
            "Choose Matlab folder")
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
            "Choose Octave octave-cli(.exe)")
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

        h9 = QHBoxLayout()
        label = QLabel("Selected engine:")
        h9.addWidget(label)
        label2 = QLabel("")
        label2.setFixedWidth(30)
        h9.addWidget(label2)
        self.selected_engine = QComboBox()
        self.selected_engine.addItem("None")
        h9.addWidget(self.selected_engine)
        label2 = QLabel("")
        label2.setMinimumWidth(200)
        h9.addWidget(label2)
        self.layout.addItem(h9)

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

        l2 = QHBoxLayout()
        self.button = QPushButton("Apply Changes")
        self.close = QPushButton("Close")
        l2.addWidget(self.button)
        l2.addWidget(self.close)
        self.layout.addItem(l2)
        self.setLayout(self.layout)

        # Connecting the signal
        self.choose_ml_path_btn.clicked.connect(self.choose_ml_path)
        self.choose_oc_exe_btn.clicked.connect(self.choose_oc_exe)
        self.choose_cna_path_btn.clicked.connect(self.choose_cna_path)
        self.selected_engine.currentTextChanged.connect(self.update)
        self.close.clicked.connect(self.accept)
        self.button.clicked.connect(self.apply)

        self.check_all()

        if self.meng is not None:
            self.selected_engine.insertItem(1, "Matlab")
            if self.appdata.selected_engine == "matlab":
                self.selected_engine.setCurrentIndex(1)
        if self.oeng is not None:
            self.selected_engine.insertItem(1, "Octave")
            if self.appdata.selected_engine == "octave":
                self.selected_engine.setCurrentIndex(1)

        self.update()

    def update(self):
        cross_icon = QIcon(":/icons/cross.png")
        cross = cross_icon.pixmap(QSize(32, 32))
        check_icon = QIcon(":/icons/check.png")
        check = check_icon.pixmap(QSize(32, 32))

        selected_engine = self.selected_engine.currentText()

        if selected_engine == "None":
            qmark_icon = QIcon(":/icons/qmark.png")
            qmark = qmark_icon.pixmap(QSize(32, 32))
            self.cna_label.setPixmap(qmark)
        else:
            if self.appdata.cna_ok:
                self.cna_label.setPixmap(check)
            else:
                self.cna_label.setPixmap(cross)
        if self.oeng is not None:
            # disable button if octave is already working
            self.oc_label.setPixmap(check)
        else:
            self.oc_label.setPixmap(cross)

        if self.meng is not None:
            self.ml_label.setPixmap(check)
        else:
            self.ml_label.setPixmap(cross)

        self.selected_engine.currentTextChanged.disconnect(self.update)
        self.selected_engine.clear()
        self.selected_engine.addItem("None")
        if self.meng is not None:
            self.selected_engine.addItem("Matlab")
        if self.oeng is not None:
            self.selected_engine.addItem("Octave")

        if selected_engine is "None":
            self.selected_engine.setCurrentIndex(0)
        if selected_engine == "Matlab":
            self.selected_engine.setCurrentIndex(1)
        if selected_engine == "Octave":
            if self.selected_engine.count() == 2:
                self.selected_engine.setCurrentIndex(1)
            elif self.selected_engine.count() == 3:
                self.selected_engine.setCurrentIndex(2)

        self.selected_engine.currentTextChanged.connect(self.update)

    def choose_ml_path(self):
        dialog = QFileDialog(self, directory=self.matlab_path.text())
        dialog.setFileMode(QFileDialog.DirectoryOnly)
        directory: str = dialog.getExistingDirectory()
        if not directory or len(directory) == 0 or not os.path.exists(directory):
            return

        self.choose_ml_path_btn.setEnabled(False)
        self.matlab_path.setText(directory)
        self.try_install_matlab_engine(directory)
        self.check_matlab()
        self.choose_ml_path_btn.setEnabled(True)
        self.update()

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

        self.choose_oc_exe_btn.setEnabled(False)
        self.check_octave()
        self.choose_oc_exe_btn.setEnabled(True)
        self.update()

    def check_all(self):
        self.check_octave()
        self.check_matlab()
        self.check_cna()

    def check_octave(self):
        if self.oeng is None:
            self.oeng = try_octave_engine(self.oc_exe.text())

    def check_matlab(self):
        # only recheck matlab if necessary
        if self.meng is None:
            self.meng = try_matlab_engine()

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
        self.update()

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
        if self.oeng is not None:
            self.appdata.cna_ok = try_cna(self.oeng, self.cna_path.text())
        elif self.meng is not None:
            self.appdata.cna_ok = try_cna(self.meng, self.cna_path.text())

    def apply(self):
        self.appdata.matlab_path = self.matlab_path.text()
        self.appdata.octave_executable = self.oc_exe.text()
        self.appdata.cna_path = self.cna_path.text()
        self.appdata.matlab_engine = self.meng
        self.appdata.octave_engine = self.oeng

        if self.selected_engine.currentText() == "None":
            self.appdata.selected_engine = "None"
        elif self.selected_engine.currentText() == "Matlab":
            self.appdata.selected_engine = "matlab"
        elif self.selected_engine.currentText() == "Octave":
            self.appdata.selected_engine = "octave"

        self.appdata.select_engine()

        self.appdata.window.disable_enable_dependent_actions()

        self.appdata.save_cnapy_config()
        self.accept()
