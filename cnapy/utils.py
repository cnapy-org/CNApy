''' CNApy utilities '''
import io
import sys
import traceback

import cobra
from qtpy.QtCore import QObject, QRunnable, Qt, Signal, Slot
from qtpy.QtWidgets import QMessageBox


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


class WorkerSignals(QObject):
    '''
    Defines the signals available from a running worker thread.

    Supported signals are:

    finished
        No data

    error
        tuple (exctype, value, traceback.format_exc() )

    result
        object data returned from processing, anything

    '''
    finished = Signal()  # QtCore.Signal
    error = Signal(tuple)
    result = Signal(object)


class Worker(QRunnable):
    '''
    Worker thread
    '''

    def __init__(self, fn, *args, **kwargs):
        super(Worker, self).__init__()
        # Store constructor arguments (re-used for processing)
        self.fn = fn
        self.args = args
        self.kwargs = kwargs
        self.signals = WorkerSignals()

    @Slot()
    def run(self):
        '''
        Initialise the runner function with passed args, kwargs.
        '''
        # Retrieve args/kwargs here; and fire processing using them
        try:
            result = self.fn(
                *self.args, **self.kwargs
            )
        except cobra.exceptions.Infeasible:
            QMessageBox.information(
                self, 'No solution', 'The scenario is infeasible')
        except:
            output = io.StringIO()
            traceback.print_exc(file=output)
            exstr = output.getvalue()
            print(exstr)
            QMessageBox.warning(self, 'Unknown exception occured!',
                                exstr+'\nPlease report the problem to:\n\
                                        \nhttps://github.com/cnapy-org/CNApy/issues')

            traceback.print_exc()
            exctype, value = sys.exc_info()[:2]
            self.signals.error.emit((exctype, value, traceback.format_exc()))
        else:
            # Return the result of the processing
            self.signals.result.emit(result)
        finally:
            self.signals.finished.emit()  # Done
