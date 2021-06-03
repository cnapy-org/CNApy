"""The cnapy about dialog"""
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout
from cnapy.appdata import AppData


class AboutDialog(QDialog):
    """An about dialog"""

    def __init__(self, appdata: AppData):
        QDialog.__init__(self)

        self.setWindowTitle("About CNApy")
        self.button = QPushButton("Close")
        self.text = QLabel(
            "Version: {version}\
            \n\nCNApy is an integrated environment for metabolic model analysis.\
            \nFor more information visit us at:".format(version=appdata.version))

        self.text.setAlignment(Qt.AlignCenter)

        self.url = QLabel(
            "<a href=\"https://github.com/cnapy-org/CNApy\"> https://github.com/cnapy-org/CNApy </a>")
        self.url.setOpenExternalLinks(True)
        self.url.setAlignment(Qt.AlignCenter)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.text)
        self.layout.addWidget(self.url)
        self.layout.addWidget(self.button)
        self.setLayout(self.layout)

        # Connecting the signal
        self.button.clicked.connect(self.reject)
