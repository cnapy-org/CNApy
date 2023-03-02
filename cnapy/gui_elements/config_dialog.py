"""The cnapy configuration dialog"""
import os
from pathlib import Path

from qtpy.QtGui import QDoubleValidator, QIntValidator, QPalette
from qtpy.QtWidgets import (QColorDialog, QDialog, QFileDialog,
                            QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                            QVBoxLayout, QCheckBox)
from cnapy.appdata import AppData


class ConfigDialog(QDialog):
    """A dialog to set values in cnapy-config.txt"""

    def __init__(self, main_window, first_start: bool):
        QDialog.__init__(self)
        self.setWindowTitle("Configure CNApy")
        self.main_window = main_window
        self.appdata: AppData = main_window.appdata

        self.layout = QVBoxLayout()

        fs = QHBoxLayout()
        label = QLabel("Font size:")
        fs.addWidget(label)
        self.font_size = QLineEdit()
        self.font_size.setFixedWidth(100)
        self.font_size.setText(str(self.appdata.font_size))
        fs.addWidget(self.font_size)
        self.layout.addItem(fs)

        bw = QHBoxLayout()
        label = QLabel("Box width:")
        bw.addWidget(label)

        self.box_width = QLineEdit()
        self.box_width.setFixedWidth(100)
        self.box_width.setText(str(self.appdata.box_width))
        bw.addWidget(self.box_width)
        self.layout.addItem(bw)

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
            "Special Color 2 used for non equal flux bounds that exclude 0: ")
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

        h = QHBoxLayout()
        self.use_results_cache = QCheckBox("Cache results (e.g. FVA) in ")
        self.use_results_cache.setChecked(self.appdata.use_results_cache)
        h.addWidget(self.use_results_cache)
        self.results_cache_directory = QPushButton()
        self.results_cache_directory.setText(str(self.appdata.results_cache_dir))
        h.addWidget(self.results_cache_directory)
        self.layout.addItem(h)

        l2 = QHBoxLayout()
        self.button = QPushButton("Apply Changes")
        l2.addWidget(self.button)

        self.close = QPushButton("Close")
        l2.addWidget(self.close)
        self.close.clicked.connect(self.accept)

        self.layout.addItem(l2)
        self.setLayout(self.layout)

        # Connecting the signal
        self.work_directory.clicked.connect(self.choose_work_directory)
        self.scen_color_btn.clicked.connect(self.choose_scen_color)
        self.comp_color_btn.clicked.connect(self.choose_comp_color)
        self.spec1_color_btn.clicked.connect(self.choose_spec1_color)
        self.spec2_color_btn.clicked.connect(self.choose_spec2_color)
        self.default_color_btn.clicked.connect(self.choose_default_color)
        self.results_cache_directory.clicked.connect(self.choose_results_cache_directory)
        self.button.clicked.connect(self.apply)

        if first_start:
            self.apply()
            self.accept()

    def choose_work_directory(self):
        dialog = QFileDialog(self, directory=self.work_directory.text())
        directory: str = dialog.getExistingDirectory()
        if not directory or len(directory) == 0 or not os.path.exists(directory):
            return
        self.work_directory.setText(directory)

    def choose_results_cache_directory(self):
        dialog = QFileDialog(self, directory=self.results_cache_directory.text())
        directory: Path = Path(dialog.getExistingDirectory())
        if not directory.exists():
            return
        self.results_cache_directory.setText(str(directory))

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
        new_fontsize = float(self.font_size.text())
        if new_fontsize != self.appdata.font_size:
            self.appdata.font_size = new_fontsize
            self.main_window.setStyleSheet("*{font-size: "+str(new_fontsize)+"pt;}")
            QMessageBox.information(
                self,
                "Restart for full font size change effect",
                "Please restart CNApy. This will also apply your font size change "
                "on all of CNApy's subwindows."
            )

        self.appdata.box_width = int(self.box_width.text())

        self.appdata.work_directory = self.work_directory.text()
        self.appdata.last_scen_directory = self.work_directory.text()

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

        self.appdata.box_width = int(self.box_width.text())
        self.appdata.rounding = int(self.rounding.text())
        self.appdata.abs_tol = float(self.abs_tol.text())
        self.appdata.results_cache_dir = Path(self.results_cache_directory.text())
        if not self.appdata.results_cache_dir.exists():
            self.use_results_cache.setChecked(False)
        self.appdata.use_results_cache = self.use_results_cache.isChecked()

        self.appdata.save_cnapy_config()

        self.appdata.window.centralWidget().update()
