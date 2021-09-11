import json
import numpy
import matplotlib.pyplot as plt

from qtpy.QtCore import Qt, Signal, QStringListModel
from qtpy.QtGui import QIcon
from qtpy.QtWidgets import (QFileDialog, QHBoxLayout, QLabel, QPushButton,
                            QVBoxLayout, QWidget, QCompleter, QLineEdit, QMessageBox, QToolButton)


import cnapy.resources
from cnapy.flux_vector_container import FluxVectorContainer


class ModeNavigator(QWidget):
    """A navigator widget"""

    def __init__(self, appdata):
        QWidget.__init__(self)
        self.appdata = appdata
        self.current = 0
        self.mode_type = 0 # EFM or some sort of flux vector
        self.scenario = {}
        self.setFixedHeight(70)
        self.layout = QVBoxLayout()
        self.layout.setContentsMargins(0, 0, 0, 0)

        self.save_button = QPushButton()
        self.save_button.setIcon(QIcon(":/icons/save.png"))
        self.save_button_connection = None

        self.clear_button = QPushButton()
        self.clear_button.setIcon(QIcon(":/icons/clear.png"))
        self.prev_button = QPushButton("<")
        self.next_button = QPushButton(">")
        self.label = QLabel()
        self.reaction_participation_button = QPushButton("Reaction participation")
        self.size_histogram_button = QPushButton("Size histogram")

        l1 = QHBoxLayout()
        self.title = QLabel("Mode Navigation")
        self.selector = QLineEdit()
        self.selector.setPlaceholderText("Select...")
        self.selector.setClearButtonEnabled(True)

        self.completion_list = QStringListModel()
        self.completer = CustomCompleter(self)
        self.completer.setModel(self.completion_list)
        self.completer.setCaseSensitivity(Qt.CaseInsensitive)
        self.selector.setCompleter(self.completer)

        l12 = QHBoxLayout()
        l12.setAlignment(Qt.AlignRight)
        l12.addWidget(self.save_button)
        l12.addWidget(self.clear_button)
        l1.addWidget(self.title)
        l1.addWidget(self.selector)
        l1.addLayout(l12)

        l2 = QHBoxLayout()
        l2.addWidget(self.prev_button)
        l2.addWidget(self.label)
        l2.addWidget(self.next_button)
        l2.addWidget(self.reaction_participation_button)
        l2.addWidget(self.size_histogram_button)

        self.layout.addLayout(l1)
        self.layout.addLayout(l2)
        self.setLayout(self.layout)

        self.prev_button.clicked.connect(self.prev)
        self.next_button.clicked.connect(self.next)
        self.clear_button.clicked.connect(self.clear)
        self.selector.returnPressed.connect(self.apply_selection)
        self.selector.findChild(QToolButton).triggered.connect(self.reset_selection) # findChild(QToolButton) retrieves the clear button
        self.size_histogram_button.clicked.connect(self.size_histogram)

    def update(self):
        txt = str(self.current + 1) + "/" + \
            str(len(self.appdata.project.modes))
        if self.num_selected < len(self.appdata.project.modes):
            txt = txt + " (" + str(self.num_selected) + " selected)"
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

    def save_mcs(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            directory=self.appdata.work_directory, filter="*.npz")[0]
        if not filename or len(filename) == 0:
            return
        self.appdata.project.modes.save(filename)

        # with open(filename, 'w') as fp:
        #     json.dump(self.appdata.project.modes, fp)

    def save_efm(self):
        dialog = QFileDialog(self)
        filename: str = dialog.getSaveFileName(
            directory=self.appdata.work_directory, filter="*.npz")[0]
        if not filename or len(filename) == 0:
            return
        self.appdata.project.modes.save(filename)

    def update_completion_list(self):
        reac_id = self.appdata.project.cobra_py_model.reactions.list_attr("id")
        self.completion_list.setStringList(reac_id+["!"+str(r) for r in reac_id])

    def set_to_mcs(self):
        self.mode_type = 1
        self.title.setText("MCS Navigation")
        if self.save_button_connection is not None:
            self.save_button.clicked.disconnect(self.save_button_connection)
        self.save_button_connection = self.save_button.clicked.connect(self.save_mcs)
        self.save_button.setToolTip("save minimal cut sets")
        self.clear_button.setToolTip("clear minimal cut sets")
        self.select_all()
        self.update_completion_list()

    def set_to_efm(self):
        self.mode_type = 0 # EFM or some sort of flux vector
        self.title.setText("Mode Navigation")
        if self.save_button_connection is not None:
            self.save_button.clicked.disconnect(self.save_button_connection)
        self.save_button_connection = self.save_button.clicked.connect(self.save_efm)
        self.save_button.setToolTip("save modes")
        self.clear_button.setToolTip("clear modes")
        self.select_all()
        self.update_completion_list()

    def clear(self):
        self.mode_type = 0 # EFM or some sort of flux vector
        self.appdata.project.modes.clear()
        self.appdata.recreate_scenario_from_history()
        self.hide()
        self.modeNavigatorClosed.emit()

    def display_mode(self):
        self.appdata.modes_coloring = True
        self.update()
        self.changedCurrentMode.emit(self.current)
        self.appdata.modes_coloring = False

    def prev(self):
        while True:
            if self.current == 0:
                self.current = len(self.appdata.project.modes)-1
            else:
                self.current -= 1
            if self.selection[self.current]:
                break
        self.display_mode()

    def next(self):
        while True:
            if self.current == len(self.appdata.project.modes)-1:
                self.current = 0
            else:
                self.current += 1
            if self.selection[self.current]:
                break
        self.display_mode()

    def select_all(self):
        self.selection = numpy.ones(len(self.appdata.project.modes), dtype=numpy.bool)
        self.num_selected = len(self.appdata.project.modes)
        self.selector.setText("")

    def reset_selection(self):
        self.selection[:] = True # select all
        self.num_selected = len(self.appdata.project.modes)
        self.update()

    def apply_selection(self):
        must_occur =  []
        must_not_occur = []
        selector_text = self.selector.text().strip()
        if len(selector_text) == 0:
            self.reset_selection()
        else:
            try:
                for r in map(str.strip, selector_text.split(',')):
                    if r[0] == "!":
                        must_not_occur.append(r[1:].lstrip())
                    else:
                        must_occur.append(r)
                self.select(must_occur=must_occur, must_not_occur=must_not_occur)
            except (ValueError, IndexError): # some ID was not found / an empty ID was encountered
                QMessageBox.critical(self, "Cannot apply selection", "Check the selection for mistakes.")
            if self.num_selected == 0:
                QMessageBox.information(self, "Selection not applied", "This selection is empty and was therefore not applied.")
                self.reset_selection()
            else:
                self.current = 0
                if self.selection[self.current]:
                    self.display_mode()
                else:
                    self.next()

    def select(self, must_occur=None, must_not_occur=None):
        self.selection[:] = True # reset selection
        if must_occur != None:
            for r in must_occur:
                r_idx = self.appdata.project.modes.reac_id.index(r)
                for i, selected in enumerate(self.selection):
                    if selected and self.appdata.project.modes.fv_mat[i, r_idx] == 0:
                        self.selection[i] = False
        if must_not_occur is not None:
            for r in must_not_occur:
                r_idx = self.appdata.project.modes.reac_id.index(r)
                for i, selected in enumerate(self.selection):
                    if selected and self.appdata.project.modes.fv_mat[i, r_idx] != 0:
                        self.selection[i] = False
        self.num_selected = numpy.sum(self.selection)

    def size_histogram(self):
        sizes = numpy.sum(self.appdata.project.modes.fv_mat[self.selection, :] != 0, axis=1)
        if isinstance(sizes, numpy.matrix): # numpy.sum returns a matrix with one row when fv_mat is scipy.sparse
            sizes = sizes.A1 # flatten into 1D array
        plt.hist(sizes, bins="auto")
        plt.show()

    def __del__(self):
        self.appdata.project.modes.clear() # for proper deallocation when it is a FluxVectorMemmap
    
    changedCurrentMode = Signal(int)
    modeNavigatorClosed = Signal()

class CustomCompleter(QCompleter):
    def __init__(self, parent=None):
        QCompleter.__init__(self, parent)

    def pathFromIndex(self, index): # overrides Qcompleter method
        path = QCompleter.pathFromIndex(self, index)
        lst = str(self.widget().text()).split(',')
        # print("pathFromIndex", lst)
        if len(lst) > 1:
            path = '%s, %s' % (','.join(lst[:-1]), path)
        return path

    def splitPath(self, path): # overrides Qcompleter method
        path = str(path.split(',')[-1]).lstrip(' ')
        # print("splitPath", path)
        return [path]
