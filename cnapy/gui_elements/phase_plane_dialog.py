"""The cnapy phase plane plot dialog"""
from qtpy.QtCore import Qt, Signal
from qtpy.QtWidgets import (QCompleter, QDialog, QHBoxLayout, QLabel,
                            QLineEdit, QPushButton, QVBoxLayout)


class CompleterLineEdit(QLineEdit):
    # does new completion after COMMA ,

    def __init__(self, wordlist, *args):
        QLineEdit.__init__(self, *args)

        self.mycompleter = QCompleter(wordlist)
        self.mycompleter.setCaseSensitivity(Qt.CaseInsensitive)
        self.mycompleter.setWidget(self)
        self.textChanged.connect(self.text_changed)
        self.mycompleter.activated.connect(self.complete_text)

    def text_changed(self, text):
        # print("hey text changed")
        all_text = text
        text = all_text[:self.cursorPosition()]
        prefix = text.split(',')[-1].strip()
        # print('prefix', prefix)

        self.mycompleter.setCompletionPrefix(prefix)
        # print('CC', self.mycompleter.currentCompletion())
        # if prefix != '' and prefix != self.mycompleter.currentCompletion():
        if prefix != '':
            self.mycompleter.complete()

    def complete_text(self, text):
        # print("hey complete text", text)
        cursor_pos = self.cursorPosition()
        before_text = self.text()[:cursor_pos]
        # print('before_text', before_text)
        after_text = self.text()[cursor_pos:]
        # print('after_text', after_text)
        prefix_len = len(before_text.split(',')[-1].strip())
        self.setText(before_text[:cursor_pos - prefix_len] + text + after_text)
        self.setCursorPosition(cursor_pos - prefix_len + len(text))

    textChanged = Signal(str)


class PhasePlaneDialog(QDialog):
    """A dialog to perform arithmetics with the clipboard"""

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
        self.button = QPushButton("Compute")
        self.cancel = QPushButton("Cancel")
        l3.addWidget(self.button)
        l3.addWidget(self.cancel)
        self.layout.addItem(l3)
        self.setLayout(self.layout)

        # Connecting the signal
        self.cancel.clicked.connect(self.reject)
        self.button.clicked.connect(self.compute)

    def compute(self):
        with self.appdata.project.cobra_py_model as model:
            from cameo import phenotypic_phase_plane
            self.appdata.project.load_scenario_into_model(model)
            x_axis = self.x_axis.text()
            y_axis = self.y_axis.text()
            result = phenotypic_phase_plane(model,
                                            variables=[
                                                model.reactions.get_by_id(x_axis)],
                                            objective=model.reactions.get_by_id(
                                                y_axis),
                                            points=10)
            print(result)
            result.plot()

        self.accept()
