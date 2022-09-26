"""The cnapy about dialog"""
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout
from cnapy.appdata import AppData


class AboutDialog(QDialog):
    """An about dialog"""

    def __init__(self, appdata: AppData):
        QDialog.__init__(self)

        self.setWindowTitle("About CNApy")

        self.text1 = QLabel(
            "Version: {version}\
            \n\nCNApy is an integrated environment for metabolic modeling.\
            \nFor more information visit us at:".format(version=appdata.version))
        self.text1.setAlignment(Qt.AlignCenter)

        self.url1 = QLabel(
            "<a href=\"https://github.com/cnapy-org/CNApy\"> https://github.com/cnapy-org/CNApy </a>")
        self.url1.setOpenExternalLinks(True)
        self.url1.setAlignment(Qt.AlignCenter)

        self.text2 = QLabel(
            "<br>If you use CNApy in your scientific work, please consider to cite CNApy's publication:<br>"
            "Thiele et al. (2022). CNApy: a CellNetAnalyzer GUI in Python for analyzing and designing metabolic networks. "
            "<i>Bioinformatics</i> 38, 1467-1469:"
        )
        self.text2.setAlignment(Qt.AlignCenter)

        self.url2 = QLabel(
            "<a href=\"https://doi.org/10.1093/bioinformatics/btab828\"> https://doi.org/10.1093/bioinformatics/btab828 </a>")
        self.url2.setOpenExternalLinks(True)
        self.url2.setAlignment(Qt.AlignCenter)


        self.button = QPushButton("Close")

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.text1)
        self.layout.addWidget(self.url1)
        self.layout.addWidget(self.text2)
        self.layout.addWidget(self.url2)
        self.layout.addWidget(self.button)
        self.setLayout(self.layout)

        # Connecting the signal
        self.button.clicked.connect(self.reject)
