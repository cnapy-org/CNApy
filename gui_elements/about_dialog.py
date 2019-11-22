 
from PySide2.QtWidgets import (QDialog, QPushButton, QVBoxLayout, QLabel)
from PySide2.QtCore import (Slot, Qt)

class AboutDialog(QDialog):
    def __init__(self):
        QDialog.__init__(self)

        self.button = QPushButton("Ok!")
        self.text = QLabel("Something something about PyNetAnalyzer!")
        self.text.setAlignment(Qt.AlignCenter)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.text)
        self.layout.addWidget(self.button)
        self.setLayout(self.layout)

        # Connecting the signal
        self.button.clicked.connect(self.reject)