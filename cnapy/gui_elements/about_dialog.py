"""The cnapy about dialog"""
from qtpy.QtCore import Qt
from qtpy.QtWidgets import QDialog, QLabel, QPushButton, QVBoxLayout


class AboutDialog(QDialog):
    """An about dialog"""

    def __init__(self):
        QDialog.__init__(self)

        self.button = QPushButton("Ok!")
        self.text = QLabel(
            "An integrated environment for metabolic model analysis.")
        self.text.setAlignment(Qt.AlignCenter)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.text)
        self.layout.addWidget(self.button)
        self.setLayout(self.layout)

        # Connecting the signal
        self.button.clicked.connect(self.reject)
