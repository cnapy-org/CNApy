"""The cnapy configuration dialog"""
from PySide2.QtWidgets import (QFileDialog, QLabel, QButtonGroup, QComboBox, QDialog, QHBoxLayout,
                               QLineEdit, QPushButton, QRadioButton,
                               QVBoxLayout)

from cnapy.cnadata import CnaData


class ConfigDialog(QDialog):
    """A dialog to set values in cnapy-config.txt"""

    def __init__(self, appdata: CnaData):
        QDialog.__init__(self)
        self.appdata = appdata
        self.layout = QVBoxLayout()
        h1 = QHBoxLayout()
        self.l1 = QLabel("CNA path")
        h1.addWidget(self.l1)

        self.cna_path = QLineEdit()
        self.cna_path.setMinimumWidth(800)
        self.cna_path.setText(self.appdata.cna_path)
        h1.addWidget(self.cna_path)
        #  = configParser.get(            'cnapy-config', 'cna_path')

        self.choose_button = QPushButton("Choose Directory")
        h1.addWidget(self.choose_button)

        self.layout.addItem(h1)

        l2 = QHBoxLayout()
        self.button = QPushButton("Apply Changes")
        self.cancel = QPushButton("Cancel")
        l2.addWidget(self.button)
        l2.addWidget(self.cancel)
        self.layout.addItem(l2)
        self.setLayout(self.layout)

        # Connecting the signal
        self.choose_button.clicked.connect(self.choose)
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.apply)

    def choose(self):
        dialog = QFileDialog(self)
        # dialog.setFileMode(QFileDialog.Directory)
        dialog.setFileMode(QFileDialog.DirectoryOnly)
        directory: str = dialog.getExistingDirectory()
        self.cna_path.setText(directory)
        pass

    def apply(self):

        self.appdata.cna_path = self.cna_path.text()

        import configparser
        configFilePath = r'cnapy-config.txt'
        parser = configparser.ConfigParser()
        parser.add_section('cnapy-config')
        parser.set('cnapy-config', 'cna_path', self.appdata.cna_path)
        fp = open(configFilePath, 'w')
        parser.write(fp)
        fp.close()

        self.accept()
