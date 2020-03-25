
from PySide2.QtGui import QIcon, QColor, QPalette
from PySide2.QtCore import Qt
from PySide2.QtWidgets import (QLineEdit, QTextEdit, QLabel,
                               QHBoxLayout, QVBoxLayout,
                               QTreeWidget, QSizePolicy,
                               QTreeWidgetItem, QWidget, QPushButton, QMessageBox, QComboBox)
from PySide2.QtCore import Signal

class ModeNavigator(QWidget):
    """A navigator widget""" 

    def __init__(self, appdata):
        QWidget.__init__(self)
        self.appdata = appdata
        self.current = 0

        self.prev_button = QPushButton("<")
        self.next_button = QPushButton(">")
        self.label = QLabel()

        
        self.layout = QHBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)
        # l.setAlignment(Qt.AlignRight)
        # l.addWidget(self.add_button)
        self.layout.addWidget(self.prev_button)
        self.layout.addWidget(self.label)
        self.layout.addWidget(self.next_button)
        self.setLayout(self.layout)

        self.prev_button.clicked.connect(self.prev)
        self.next_button.clicked.connect(self.next)

        self.update()

    def update(self):
        self.label.setText(str(self.current + 1) + "/" + str(len(self.appdata.modes)))

    def prev(self):
        if self.current == 0:
            self.current = len(self.appdata.modes)-1
        else:
            self.current -= 1
        
        values = self.appdata.modes[self.current].copy()
        self.appdata.set_scen(values)
        self.update()
        self.changedCurrentMode.emit(self.current)

    def next(self):
        if self.current == len(self.appdata.modes)-1:
            self.current = 0
        else:
            self.current += 1

        values = self.appdata.modes[self.current].copy()
        self.appdata.set_scen(values)
        self.update()
        self.changedCurrentMode.emit(self.current)
        
    changedCurrentMode = Signal(int)