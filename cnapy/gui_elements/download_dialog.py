"""The CNApy download examples files dialog"""
import os
import shutil
import urllib.request

import pkg_resources
from qtpy.QtWidgets import (
    QLabel, QDialog, QHBoxLayout, QPushButton,  QVBoxLayout)

from cnapy.appdata import AppData


class DownloadDialog(QDialog):
    """A dialog to create a CNApy-projects directory and download example files"""

    def __init__(self, appdata: AppData):
        QDialog.__init__(self)
        self.setWindowTitle("Create folder with example files?")

        self.appdata = appdata
        self.layout = QVBoxLayout()

        label_line = QVBoxLayout()
        label = QLabel(
            "CNApy has found no projects directory.")
        label_line.addWidget(label)
        label = QLabel(
            "Should CNApy create a projects directory and download examples files?")
        label_line.addWidget(label)
        self.layout.addItem(label_line)

        button_line = QHBoxLayout()
        self.download_btn = QPushButton("Yes, create directory")
        self.close = QPushButton("No ,skip")
        button_line.addWidget(self.download_btn)
        button_line.addWidget(self.close)
        self.layout.addItem(button_line)
        self.setLayout(self.layout)

        # Connecting the signal
        self.close.clicked.connect(self.accept)
        self.download_btn.clicked.connect(self.download)

    def download(self):
        work_directory = self.appdata.work_directory
        print("Create work directory:", work_directory)
        os.mkdir(work_directory)

        targets = ["ECC2.cna", "ECC2comp.cna", "SmallExample.cna",
                   "iJO1366.cna", "iJOcore.cna", "iML1515.cna", "iMLcore.cna"]
        for t in targets:
            target = os.path.join(work_directory, t)
            if not os.path.exists(target):
                print("Download:", target)
                url = 'https://github.com/cnapy-org/CNApy-projects/releases/download/0.0.3/'+t
                urllib.request.urlretrieve(url, target)

        scen_file = pkg_resources.resource_filename(
            'cnapy', 'data/Ecoli-glucose-standard.scen')
        target = os.path.join(
            work_directory, 'Ecoli-glucose-standard.scen')
        shutil.copyfile(scen_file, target)
        scen_file = pkg_resources.resource_filename(
            'cnapy', 'data/Ecoli-flux-analysis.scen')
        target = os.path.join(
            work_directory, 'Ecoli-flux-analysis.scen')
        shutil.copyfile(scen_file, target)

        self.accept()
