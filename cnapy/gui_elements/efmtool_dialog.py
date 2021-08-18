"""The cnapy elementary flux modes calculator dialog"""
from qtpy.QtCore import Qt, QThread, Signal, Slot
from qtpy.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QMessageBox,
                            QPushButton, QVBoxLayout, QTextEdit)

import cnapy.core
from cnapy.appdata import AppData


class EFMtoolDialog(QDialog):
    """A dialog to set up EFM calculation"""

    def __init__(self, appdata: AppData, central_widget):
        QDialog.__init__(self)
        self.setWindowTitle("Elementary Flux Mode Computation")

        self.appdata = appdata
        self.central_widget = central_widget

        self.layout = QVBoxLayout()

        l1 = QHBoxLayout()
        self.constraints = QCheckBox("consider 0 in current scenario as off")
        self.constraints.setCheckState(Qt.Checked)
        l1.addWidget(self.constraints)
        self.layout.addItem(l1)

        self.text_field = QTextEdit("*** EFMtool output ***")
        self.text_field.setReadOnly(True)
        self.layout.addWidget(self.text_field)

        lx = QHBoxLayout()
        self.button = QPushButton("Compute")
        self.cancel = QPushButton("Close")
        lx.addWidget(self.button)
        lx.addWidget(self.cancel)
        self.layout.addItem(lx)

        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

    def compute(self):
        self.setCursor(Qt.BusyCursor)
        self.efm_computation = EFMComputationThread(self.appdata.project.cobra_py_model, self.appdata.project.scen_values,
                                                    self.constraints.checkState() == Qt.Checked)
        self.button.setText("Abort computation")
        self.button.clicked.disconnect(self.compute)
        self.button.clicked.connect(self.efm_computation.activate_abort)
        self.rejected.connect(self.efm_computation.activate_abort) # for the X button of the window frame
        self.cancel.hide()
        self.efm_computation.send_progress_text.connect(self.receive_progress_text)
        self.efm_computation.finished_computation.connect(self.conclude_computation)
        self.efm_computation.start()

    def conclude_computation(self):
        self.setCursor(Qt.ArrowCursor)
        if self.efm_computation.abort:
            self.accept()
        else:
            if self.efm_computation.ems is None:
                # in this case the progress window should still be left open and the cancel button reappear
                self.button.hide()
                self.cancel.show()
                QMessageBox.information(self, 'No modes',
                                        'An error occured and modes have not been calculated.')
            else:
                self.accept()
                if len(self.efm_computation.ems) == 0:
                    QMessageBox.information(self, 'No modes',
                                            'No elementary modes exist.')
                else:
                    self.appdata.project.modes = self.efm_computation.ems
                    self.central_widget.mode_navigator.current = 0
                    self.central_widget.mode_navigator.scenario = self.efm_computation.scenario
                    self.central_widget.mode_navigator.set_to_efm()
                    self.central_widget.update_mode()

    @Slot(str)
    def receive_progress_text(self, text):
        self.text_field.append(text)
        # self.central_widget.console._append_plain_text(text) # causes some kind of deadlock?!?

class EFMComputationThread(QThread):
    def __init__(self, model, scen_values, constraints):
        super().__init__()
        self.model = model
        self.scen_values = scen_values
        self.constraints = constraints
        self.abort = False
        self.ems = None
        self.scenario = None

    def do_abort(self):
        return self.abort

    def activate_abort(self):
        self.abort = True

    def run(self):
        (self.ems, self.scenario) = cnapy.core.efm_computation(self.model, self.scen_values, self.constraints,
                                        print_progress_function=self.print_progress_function, abort_callback=self.do_abort)
        self.finished_computation.emit()

    def print_progress_function(self, text):
        print(text)
        self.send_progress_text.emit(text)

    # the output from efmtool needs to be passed as a signal because all Qt widgets must
    # run on the main thread and their methods cannot be safely called from other threads
    send_progress_text = Signal(str)
    finished_computation = Signal()
