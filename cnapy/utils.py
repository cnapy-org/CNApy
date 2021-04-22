''' CNApy utilities '''
from qtpy.QtCore import QObject, Qt, Signal, Slot, QTimer


def turn_red(item):
    palette = item.palette()
    role = item.foregroundRole()
    palette.setColor(role, Qt.black)
    item.setPalette(palette)

    item.setStyleSheet("background: #ff9999")


def turn_white(item):
    palette = item.palette()
    role = item.foregroundRole()
    palette.setColor(role, Qt.black)
    item.setPalette(palette)

    item.setStyleSheet("background: white")


class SignalThrottler(QObject):
    def __init__(self, interval):
        QObject.__init__(self)
        self.timer = QTimer()
        self.timer.setInterval(interval)
        self.hasPendingEmission = False
        self.timer.timeout.connect(self.maybeEmitTriggered)

    def maybeEmitTriggered(self):
        if self.hasPendingEmission:
            self.emit_triggered()

    @Slot()
    def throttle(self):
        self.hasPendingEmission = True

        if not self.timer.isActive():
            self.timer.start()

    def emit_triggered(self):
        self.hasPendingEmission = False
        self.triggered.emit()

    triggered = Signal()
    timeoutChanged = Signal(int)
    timerTypeChanged = Signal(Qt.TimerType)
