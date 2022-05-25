"""The CPLEX configuration dialog"""
import os
import subprocess

from qtpy.QtWidgets import (QDialog, QFileDialog,
                            QLabel, QMessageBox, QPushButton,
                            QVBoxLayout)
from cnapy.appdata import AppData


class CplexConfigurationDialog(QDialog):
    """A dialog to set values in cnapy-config.txt"""

    def __init__(self, appdata: AppData):
        QDialog.__init__(self)
        self.setWindowTitle("Configure IBM CPLEX Full Version")
        self.appdata = appdata

        self.layout = QVBoxLayout()

        label = QLabel(
            "By default, right after CNApy's installation, you have only access to the IBM CPLEX Community Edition\n"
            "which can only handle up to 1000 variables simultaneously.\n"
            "In order to use the full version of IBM CPLEX, with no variable number limit, follow the next steps in the given order:\n"
            "1. (if not already done) Obtain an IBM CPLEX license and download it onto your computer.\n"
            "Note: CNApy only works with recent IBM CPLEX versions (not older than version 20.1.0)!\n"
            "2. (if not already done) Install IBM CPLEX by following the IBM CPLEX installer's instructions. Remember where you installed IBM CPLEX.\n"
            "3. Select the folder in which you've installed IBM CPLEX by pressing the following button:"
        )
        self.layout.addWidget(label)

        self.cplex_directory = QPushButton()
        self.cplex_directory.setText(
            "NOT SET YET! PLEASE SET THE PATH TO IBM CPLEX (see steps 1 to 3 above)."
        )
        self.layout.addWidget(self.cplex_directory)

        label = QLabel(
            "4. (only if step 3 was successful) Run the IBM CPLEX Python connection script by pressing the following button:"
        )
        self.python_run_button = QPushButton("Run Python connection script")
        self.layout.addWidget(label)
        self.layout.addWidget(self.python_run_button)

        label = QLabel(
            "5. (only if step 4 was successful) Set an environmental variable called PYTHONPATH to the following folder..."
        )
        self.layout.addWidget(label)

        self.environmental_variable_label = QLabel(
            "NOT SET YET! Please run the previous steps."
        )
        self.layout.addWidget(self.environmental_variable_label)

        label = QLabel(
            "...In order the set this environmental variable, you have to know which operating system runs on your computer.\n"
            "It might me e.g. Linux, Windows or MacOS. After you've found this out, perform one of the following steps:\n"
            "> Only if you use Windows: Press START in your task bar and open the settings (wheel). In the settings menu, write 'variable' in the search bar.\n"
            "Select 'edit environmental variables for this account' (or similar) and, in the newly opened window, click the 'New' button. Write 'PYTHONPATH' as the\n"
            "variable's name and write, as a value, the path given above in this step 5. Then, click 'OK' and again 'OK'.\n"
            "> Only if you use Linux or MacOS: In your console, run 'export PYTHONPATH=PATH' (without the quotation marks) where PATH has to be the path\n"
            "given under this step 5 above."
        )
        self.layout.addWidget(label)

        label = QLabel(
            "6. After you've finished all tasks, restart your computer and IBM CPLEX should be correctly configured for CNApy!"
        )
        self.layout.addWidget(label)

        self.close = QPushButton("Close")
        self.layout.addWidget(self.close)
        self.setLayout(self.layout)

        # Connect the signals
        self.cplex_directory.clicked.connect(self.choose_cplex_directory)
        self.python_run_button.clicked.connect(
            self.run_python_connection_script)
        self.close.clicked.connect(self.accept)

        self.has_set_existing_cplex_directory = False

    def folder_error(self):
        QMessageBox.warning(
            self,
            "Folder Error",
            "ERROR: The folder you chose in step 3 does not seem to exist! "
            "Please choose an existing folder in which you have installed IBM CPLEX (see steps 1-3).\n"
        )

    def choose_cplex_directory(self):
        dialog = QFileDialog(self)  # , directory=self.cplex_directory.text())
        directory: str = dialog.getExistingDirectory()
        if (not directory) or (len(directory) == 0) or (not os.path.exists(directory)):
            self.folder_error()
        else:
            directory = directory.replace("\\", "/")
            if not directory.endswith("/"):
                directory += "/"

            self.cplex_directory.setText(directory)
            self.has_set_existing_cplex_directory = True

    def run_python_connection_script(self):
        if not self.has_set_existing_cplex_directory:
            self.folder_error()
        else:
            try:
                QMessageBox.information(
                    self,
                    "Running",
                    "The script is going to run as you press 'OK'.\nPlease wait for an error or success message which appears\nafter the script running has finished."
                )
                has_run_error = subprocess.check_call(
                    'python "' + self.cplex_directory.text() + '" python/setup.py install'
                )  # The " are introduces in order to handle paths with blank spaces
            except subprocess.CalledProcessError:
                has_run_error = True
            if has_run_error:
                QMessageBox.warning(
                    self,
                    "Run Error",
                    "ERROR: IBM CPLEX's setup.py run failed! "
                    "Please check that you use a recent IBM CPLEX version. CNApy isn't compatible with older IBM CPLEX versions.\n"
                    "Additionally, please check that you have followed the previous steps 1 to 3."
                )
            else:
                QMessageBox.information(
                    self,
                    "Success",
                    "Success in running the Python connection script! Now, you can proceed with the next steps."
                )
                self.get_and_set_environmental_variable()

    def get_and_set_environmental_variable(self):
        base_path = self.cplex_directory.text() + "cplex/python/3.8/"

        folders_list = [
            base_path+folder for folder in os.listdir(base_path) if os.path.isdir(base_path+folder)
        ]

        if len(folders_list) > 1:
            folders_str = "You have to set the following multiple paths:\n"
        else:
            folders_str = ""
        folders_str += "\n".join(folders_list)

        self.environmental_variable_label.setText(folders_str)
