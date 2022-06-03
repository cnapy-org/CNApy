"""The CNApy download examples files dialog"""
import os
import urllib.request
from zipfile import ZipFile

from qtpy.QtWidgets import (
    QLabel, QDialog, QHBoxLayout, QPushButton,  QVBoxLayout
)

from cnapy.appdata import AppData


class DownloadDialog(QDialog):
    """A dialog to create a CNApy-projects directory and download example files"""

    def __init__(self, appdata: AppData):
        QDialog.__init__(self)
        self.setWindowTitle("Create folder with example projects?")

        self.appdata = appdata
        self.layout = QVBoxLayout()

        label_line = QVBoxLayout()
        label = QLabel(
            "CNApy could not find a projects directory.")
        label_line.addWidget(label)
        label = QLabel(
            "Should CNApy create a projects directory and download example projects?")
        label_line.addWidget(label)
        self.layout.addItem(label_line)

        button_line = QHBoxLayout()
        self.download_btn = QPushButton("Yes, create directory")
        self.close = QPushButton("No, skip")
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

        targets = ["all_cnapy_projects.zip"]
        for t in targets:
            target = os.path.join(work_directory, t)
            if not os.path.exists(target):
                url = 'https://github.com/cnapy-org/CNApy-projects/releases/download/0.0.5/' + t
                print("Downloading", url, "to", target, "...")
                urllib.request.urlretrieve(url, target)
                print("Done!")

                zip_path = os.path.join(work_directory, t)
                print("Extracting", zip_path, "...")
                with ZipFile(zip_path, 'r') as zip_file:
                    zip_file.extractall(path=work_directory)
                print("Done!")
                os.remove(zip_path)

        self.accept()
