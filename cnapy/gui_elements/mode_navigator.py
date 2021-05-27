from qtpy.QtCore import Qt, Signal
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                            QWidget)

from cnapy.flux_vector_container import FluxVectorContainer


class ModeNavigator(QWidget):
    """A navigator widget"""

    def __init__(self, appdata):
        QWidget.__init__(self)
        self.appdata = appdata
        self.current = 0
        self.scenario = {}
        self.setFixedHeight(70)
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.clear_button = QPushButton()
        self.clear_button.setIcon(QIcon(":/icons/clear.png"))
        self.clear_button.setToolTip("clear modes")
        self.prev_button = QPushButton("<")
        self.next_button = QPushButton(">")
        self.label = QLabel()

        l1 = QHBoxLayout()
        self.title = QLabel("Mode Navigation")

        l12 = QHBoxLayout()
        l12.setAlignment(Qt.AlignRight)
        l12.addWidget(self.clear_button)
        l1.addWidget(self.title)
        l1.addLayout(l12)

        l2 = QHBoxLayout()
        l2.addWidget(self.prev_button)
        l2.addWidget(self.label)
        l2.addWidget(self.next_button)

        self.layout.addLayout(l1)
        self.layout.addLayout(l2)
        self.setLayout(self.layout)

        self.prev_button.clicked.connect(self.prev)
        self.next_button.clicked.connect(self.next)
        self.clear_button.clicked.connect(self.clear)

    def update(self):
        txt = str(self.current + 1) + "/" + \
            str(len(self.appdata.project.modes))
        if isinstance(self.appdata.project.modes, FluxVectorContainer):
            if self.appdata.project.modes.irreversible.shape != ():
                if self.appdata.project.modes.irreversible[self.current]:
                    txt = txt + " irreversible"
                else:
                    txt = txt + " reversible"
            if self.appdata.project.modes.unbounded.shape != ():
                if self.appdata.project.modes.unbounded[self.current]:
                    txt = txt + " unbounded"
                else:
                    txt = txt + " bounded"
        self.label.setText(txt)

    def clear(self):
        self.appdata.project.modes.clear()
        self.appdata.recreate_scenario_from_history()
        self.hide()
        self.modeNavigatorClosed.emit()

    def prev(self):
        if self.current == 0:
            self.current = len(self.appdata.project.modes)-1
        else:
            self.current -= 1

        self.appdata.modes_coloring = True
        self.update()
        self.changedCurrentMode.emit(self.current)
        self.appdata.modes_coloring = False

    def next(self):
        if self.current == len(self.appdata.project.modes)-1:
            self.current = 0
        else:
            self.current += 1

        self.appdata.modes_coloring = True
        self.update()
        self.changedCurrentMode.emit(self.current)
        self.appdata.modes_coloring = False

    changedCurrentMode = Signal(int)
    modeNavigatorClosed = Signal()
