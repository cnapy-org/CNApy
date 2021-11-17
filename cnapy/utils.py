''' CNApy utilities '''
from qtpy.QtCore import QObject, Qt, Signal, Slot, QTimer
from qtpy.QtWidgets import QMessageBox


def show_unknown_error_box(exstr):
    msgBox = QMessageBox()
    msgBox.setWindowTitle("Unknown Error!")
    msgBox.setTextFormat(Qt.RichText)

    msgBox.setText("<p>"+exstr+"</p><p><b> Please report the problem to:</b></p>\
    <p><a href='https://github.com/cnapy-org/CNApy/issues'>https://github.com/cnapy-org/CNApy/issues</a></p>")
    msgBox.setIcon(QMessageBox.Warning)
    msgBox.exec()


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

    @Slot()
    def finish(self):
        self.timer.stop()
        if self.hasPendingEmission:
            self.emit_triggered()

    triggered = Signal()
    timeoutChanged = Signal(int)
    timerTypeChanged = Signal(Qt.TimerType)
