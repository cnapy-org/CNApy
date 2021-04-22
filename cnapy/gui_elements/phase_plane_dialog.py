"""The phase plane plot dialog"""

import matplotlib.pyplot as plt
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (QCompleter, QDialog, QHBoxLayout, QLabel,
                            QLineEdit, QPushButton, QVBoxLayout)
import numpy

from cnapy.core import load_values_into_model


class CompleterLineEdit(QLineEdit):
    '''# does new completion after COMMA ,'''

    def __init__(self, wordlist, *args):
        QLineEdit.__init__(self, *args)

        self.mycompleter = QCompleter(wordlist)
        self.mycompleter.setCaseSensitivity(Qt.CaseInsensitive)
        self.mycompleter.setWidget(self)
        self.textChanged.connect(self.text_changed)
        self.mycompleter.activated.connect(self.complete_text)

    def text_changed(self, text):
        all_text = text
        text = all_text[:self.cursorPosition()]
        prefix = text.split(',')[-1].strip()

        self.mycompleter.setCompletionPrefix(prefix)
        if prefix != '':
            self.mycompleter.complete()

    def complete_text(self, text):
        cursor_pos = self.cursorPosition()
        before_text = self.text()[:cursor_pos]
        after_text = self.text()[cursor_pos:]
        prefix_len = len(before_text.split(',')[-1].strip())
        self.setText(before_text[:cursor_pos - prefix_len] + text + after_text)
        self.setCursorPosition(cursor_pos - prefix_len + len(text))

    textChangedX = Signal(str)


class PhasePlaneDialog(QDialog):
    """A dialog to create phase plane plots"""

    def __init__(self, appdata):
        QDialog.__init__(self)
        self.setWindowTitle("Phase plane plotting")
        self.appdata = appdata

        completer = QCompleter(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), self)
        completer.setCaseSensitivity(Qt.CaseInsensitive)

        self.layout = QVBoxLayout()
        l1 = QHBoxLayout()
        t1 = QLabel("Reaction (x-axis):")
        l1.addWidget(t1)
        self.x_axis = CompleterLineEdit(
            self.appdata.project.cobra_py_model.reactions.list_attr("id"), "")
        self.x_axis.setPlaceholderText("Enter reaction Id")

        l1.addWidget(self.x_axis)
        l2 = QHBoxLayout()
        t2 = QLabel("Reaction (y-axis):")
        l2.addWidget(t2)
        self.y_axis = QLineEdit("")
        self.y_axis.setPlaceholderText("Enter reaction Id")
        self.y_axis.setCompleter(completer)
        l2.addWidget(self.y_axis)
        self.layout.addItem(l1)
        self.layout.addItem(l2)
        l3 = QHBoxLayout()
        self.button = QPushButton("Plot")
        self.cancel = QPushButton("Close")
        l3.addWidget(self.button)
        l3.addWidget(self.cancel)
        self.layout.addItem(l3)
        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

    def compute(self):
        with self.appdata.project.cobra_py_model as model:
            load_values_into_model(self.appdata.project.scen_values,  model)
            x_axis = self.x_axis.text()
            y_axis = self.y_axis.text()
            try:
                x_reac_idx = model.reactions.index(x_axis)
                y_reac_idx = model.reactions.index(y_axis)
            except KeyError:
                return
            points = 100
            with model as ppmodel:
                ppmodel.objective = ppmodel.reactions[x_reac_idx]
                ppmodel.objective.direction = 'min'
                x_lb = ppmodel.slim_optimize()
                ppmodel.objective.direction = 'max'
                x_ub = ppmodel.slim_optimize()
            result2 = numpy.zeros((points, 3))
            result2[:, 0] = numpy.linspace(x_lb, x_ub, num=points)
            var = numpy.linspace(x_lb, x_ub, num=points)
            lb = numpy.full(points, numpy.nan)
            ub = numpy.full(points, numpy.nan)
            with model as ppmodel:
                ppmodel.objective = ppmodel.reactions[y_reac_idx]
                for i in range(points):
                    # without second context the original reaction bounds are not restored (?)
                    with ppmodel as ppmodel2:
                        ppmodel2.reactions[x_reac_idx].lower_bound = result2[i, 0]
                        ppmodel2.reactions[x_reac_idx].upper_bound = result2[i, 0]
                        ppmodel2.objective.direction = 'min'
                        lb[i] = result2[i, 1] = ppmodel2.slim_optimize()
                        ppmodel2.objective.direction = 'max'
                        ub[i] = result2[i, 2] = ppmodel2.slim_optimize()

            _fig, axes = plt.subplots()
            axes.set_xlabel(model.reactions[x_reac_idx].id)
            axes.set_ylabel(model.reactions[y_reac_idx].id)
            x = [v for v in var] + [v for v in reversed(var)]
            y = [v for v in lb] + [v for v in reversed(ub)]
            if lb[0] != ub[0]:
                x.extend([var[0], var[0]])
                y.extend([lb[0], ub[0]])

            plt.plot(x, y)
            plt.show()

        (_, r) = self.appdata.window.centralWidget().splitter2.getRange(1)
        self.appdata.window.centralWidget().splitter2.moveSplitter(r*0.5, 1)
        self.appdata.window.centralWidget().scroll_down()
