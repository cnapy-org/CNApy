"""The CNApy download examples files dialog"""
import os
import urllib.request
from zipfile import ZipFile

from qtpy.QtWidgets import (
    QLabel, QDialog, QHBoxLayout, QPushButton,
    QVBoxLayout, QMessageBox,
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
            "Should CNApy download metabolic network example projects to your CNApy working directory?\n"
            "This requires an active internet connection.\n"
            "If a working directory error occurs, you can solve by setting a working directory under 'Config->Configure CNApy'.\n"
            "In this configuration dialog, you can also change CNApy's font size."
        )
        label_line.addWidget(label)
        self.layout.addItem(label_line)

        button_line = QHBoxLayout()
        self.download_btn = QPushButton("Yes, download main example projects")
        self.download_all_btn = QPushButton("Yes, download all available projects")
        self.close = QPushButton("No, do not download")
        button_line.addWidget(self.download_btn)
        button_line.addWidget(self.download_all_btn)
        button_line.addWidget(self.close)
        self.layout.addItem(button_line)
        self.setLayout(self.layout)

        # Connecting the signal
        self.close.clicked.connect(self.accept)
        self.download_btn.clicked.connect(self.download)
        self.download_all_btn.clicked.connect(lambda: self.download(download_all=True))

    def download(self, download_all=False):
        work_directory = self.appdata.work_directory
        if not os.path.exists(work_directory):
            print("Create uncreated work directory:", work_directory)
            os.mkdir(work_directory)

        if download_all:
            targets = ["all_cnapy_projects.zip"]
        else:
            targets = ["main_cnapy_projects.zip"]
        for t in targets:
            target = os.path.join(work_directory, t)
            if not os.path.exists(target):
                url = 'https://github.com/cnapy-org/CNApy-projects/releases/latest/download/' + t
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

        msgBox = QMessageBox()
        msgBox.setWindowTitle("Projects download complete")
        msgBox.setText(
            "Projects were downloaded successfully in the working directory."
        )
        msgBox.setIcon(QMessageBox.Information)
        msgBox.exec()
