#!/usr/bin/env python3
#
# Copyright 2019 PSB & ST
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
""""""

import sys
import random
from PySide2.QtWidgets import (QMainWindow, QAction, QApplication, QLabel, QPushButton,
                               QVBoxLayout, QWidget)
from PySide2.QtCore import Slot, Qt

# # Internal modules
from gui_elements.about_dialog import AboutDialog

class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.setWindowTitle("PyNetAnalyzer")

        # Menu
        self.menu = self.menuBar()
        self.file_menu = self.menu.addMenu("File")

        new_project_action= QAction("New project...", self)
        self.file_menu.addAction(new_project_action)

        open_project_action= QAction("Open project...", self)
        self.file_menu.addAction(open_project_action)
        open_project_action.triggered.connect(self.open_project)

        save_project_action= QAction("Save project...", self)
        self.file_menu.addAction(save_project_action)

        save_as_project_action= QAction("Save project as...", self)
        self.file_menu.addAction(save_as_project_action)

        exit_action = QAction("Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        self.file_menu.addAction(exit_action)
        exit_action.triggered.connect(self.exit_app)

        self.edit_menu = self.menu.addMenu("Edit")
        network_compose_action= QAction("Network composer...", self)
        self.edit_menu.addAction(network_compose_action)

        self.find_menu = self.menu.addMenu("Find")
        find_reaction_action= QAction("Find reaction...", self)
        self.find_menu.addAction(find_reaction_action)

        self.analysis_menu = self.menu.addMenu("Analysis")
        fba_action= QAction("Flux Balance Analysis (FBA)...", self)
        self.analysis_menu.addAction(fba_action)
        fva_action= QAction("Flux Variability Analysis (FVA)...", self)
        self.analysis_menu.addAction(fva_action)

        self.help_menu = self.menu.addMenu("Help")
        about_action= QAction("About PyNetAnalyzer...", self)
        self.help_menu.addAction(about_action)
        about_action.triggered.connect(self.show_about)


    @Slot()
    def exit_app(self, checked):
        QApplication.quit()

    @Slot()
    def show_about(self, checked):
        dialog = AboutDialog()
        dialog.exec_()

    @Slot()
    def open_project(self, checked):
        print("hello")
        pass
        # filename = filedialog.askopenfilename(initialdir = os.getcwd(),title = "Select file",filetypes = (("model files","*.xml"),("all files","*.*")))
        # doc = readSBMLFromFile(filename)
        # # if doc.getNumErrors() > 0:
        # #     messagebox.showerror("Error", "could not read "+filename )

        # self.parent.data.sbml = doc
        # self.parent.print_data()


if __name__ == "__main__":
    # Qt Application
    app = QApplication(sys.argv)

    window = MainWindow()
    window.resize(800, 600)
    window.show()

    # Execute application
    sys.exit(app.exec_())


class PyNetAnalyzer(QWidget):
    def __init__(self):
        QWidget.__init__(self)

        self.hello = ["Hallo Welt", "你好，世界", "Hei maailma",
            "Hola Mundo", "Привет мир"]

        self.button = QPushButton("Click me!")
        self.text = QLabel("Hello World")
        self.text.setAlignment(Qt.AlignCenter)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.text)
        self.layout.addWidget(self.button)
        self.setLayout(self.layout)

        # Connecting the signal
        self.button.clicked.connect(self.magic)
 
    @Slot()
    def magic(self):
        self.text.setText(random.choice(self.hello))

# if __name__ == "__main__":
#     app = QApplication(sys.argv)

#     widget = PyNetAnalyzer()
#     widget.resize(800, 600)
#     widget.show()

#     sys.exit(app.exec_())

# # External modules
# import sys
# import tkinter
# import tkinter.ttk

# from tkinter import Listbox
# # Internal modules
# from gui_elements.menu import Menu


# class PyNetAnalyzer(tkinter.Tk):
#     """Main window class.
#     """
#     def __init__(self):
#         # Startup the window.
#         super().__init__()
#         self.title("PyNetAnalyzer Alpha")

#         self.data = Data()

#         # Add menu submodule.
#         menu = Menu(self)
#         self["menu"] = menu

#         self.reaclist = Listbox(self)
#         for item in ["one", "two", "three", "four"]:
#             self.reaclist.insert("end", item)
#         self.reaclist.pack(side="left")

#         self.speclist = Listbox(self)
#         for item in ["one", "two", "three", "four"]:
#             self.speclist.insert("end", item)
#         self.speclist.pack(side="right")

#         # Start window
#         self.mainloop()

#     def print_data(self):
#         print (self.data.sbml)


# class Data:
#     sbml = None
#     reactions = []
#     species = []


# def main():
#     """Starts PyNetAnalyzer."""
#     PyNetAnalyzer()
#     return 0


# # Check if PyNetAnalyzer is already running in the same session.
# if __name__ == '__main__':
#     sys.exit(main())
