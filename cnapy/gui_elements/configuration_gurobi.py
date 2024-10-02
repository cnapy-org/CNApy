"""The Gurobi configuration dialog"""
import os
import subprocess
import sys
import platform

from qtpy.QtWidgets import (QDialog, QFileDialog,
                            QLabel, QMessageBox, QPushButton,
                            QVBoxLayout)
from cnapy.appdata import AppData


class GurobiConfigurationDialog(QDialog):
    """A dialog to set values in cnapy-config.txt"""

    def __init__(self, appdata: AppData):
        QDialog.__init__(self)
        self.setWindowTitle("Configure Gurobi Full Version")
        self.appdata = appdata

        self.layout = QVBoxLayout()

        label = QLabel(
            "By default, right after CNApy's installation, you have only access to the Gurobi Community Edition\n"
            "which can only handle up to 1000 variables simultaneously.\n"
            "In order to use the full version of Gurobi, with no variable number limit, follow the next steps in the given order:\n"
            "1. (only if not already done and only necessary if you encounter problems with the following steps despite the installation tips in step 3)\n"
            "Restart CNApy with administrator privileges as follows:\n"
            " i) Close this session of CNApy\n"
            " ii) Find out your operating system by looking at the next line:\n"
            f" {platform.system()}\n"
            " iii) Depending on your operating system:\n"
            "     >Only if you use Windows: If you used CNApy's bat installer: Right click on RUN_CNApy.bat or the CNApy desktop icon\n"
            "       or the CNApy entry in the start menu's program list and select 'Run as adminstrator'.\n"
            "       If you didn't use CNApy's .bat installer but Python or conda/mamba, start your Windows console or Powershell with administrator rights\n"
            "       and startup CNApy."
            "     >Only if you use Linux or MacOS (MacOS may be called Darwin): The most common way is by using the 'sudo' command. If you used the\n"
            "      CNApy sh installer, you can start CNApy with administrator rights through 'sudo run_cnapy.sh'. If you didn't use CNApy's .bat installer\n"
            "      but Python or conda/mamba, run your usual CNApy command with 'sudo' in front of it.\n"
            " NOTE: It may be possible that you're not allowed to get administrator rights on your computer. If this is the case, contact your system's administrator to resolve the problem.\n"
            "2. (if not already done) Obtain an Gurobi license and download Gurobi itself onto your computer.\n"
            "    NOTE: CNApy only works with recent Gurobi versions (not older than version 20.1.0)!\n"
            "3. (if not already done) Install Gurobi by following the Gurobi installer's instructions. Remember where you installed Gurobi.\n"
            "   If given and possible, try to install gurobi only for the 'local user' (or similar). By doing this, you might avoid the need for\n"
            "   administrator rights.\n"
            "4. Select the folder in which you've installed Gurobi by pressing the following button:"
        )
        self.layout.addWidget(label)

        self.gurobi_directory = QPushButton()
        self.gurobi_directory.setText(
            "NOT SET YET! PLEASE SET THE PATH TO THE GUROBI MAIN FOLDER (see steps 1 to 3 above)."
        )
        self.layout.addWidget(self.gurobi_directory)

        label = QLabel(
            "5. (only if step 3 was successful) Run the Gurobi Python connection script by pressing the following button:"
        )
        self.python_run_button = QPushButton("Run Python connection script")
        self.layout.addWidget(label)
        self.layout.addWidget(self.python_run_button)

        label = QLabel(
            "6. After you've finished all previous steps 1 to 5, restart your computer and Gurobi should be correctly configured for CNApy!"
        )
        self.layout.addWidget(label)

        self.close = QPushButton("Close")
        self.layout.addWidget(self.close)
        self.setLayout(self.layout)

        # Connect the signals
        self.gurobi_directory.clicked.connect(self.choose_gurobi_directory)
        self.python_run_button.clicked.connect(
            self.run_python_connection_script)
        self.close.clicked.connect(self.accept)

        self.has_set_existing_gurobi_directory = False

    def folder_error(self):
        QMessageBox.warning(
            self,
            "Folder Error",
            "ERROR: The folder you chose in step 3 does not seem to exist! "
            "Please choose an existing folder in which you have installed Gurobi (see steps 1-3).\n"
        )

    def choose_gurobi_directory(self):
        dialog = QFileDialog(self)  # , directory=self.gurobi_directory.text())
        directory: str = dialog.getExistingDirectory()
        if (not directory) or (len(directory) == 0) or (not os.path.exists(directory)):
            self.folder_error()
        else:
            directory = directory.replace("\\", "/")
            if not directory.endswith("/"):
                directory += "/"

            self.gurobi_directory.setText(directory)
            self.has_set_existing_gurobi_directory = True

    def run_python_connection_script(self):
        if not self.has_set_existing_gurobi_directory:
            self.folder_error()
        else:
            try:
                QMessageBox.information(
                    self,
                    "Running",
                    "The script is going to run as you press 'OK'.\nPlease wait for an error or success message which appears\nafter the script running has finished."
                )
                python_exe_path = sys.executable
                python_dir = os.path.dirname(python_exe_path)
                python_exe_name = os.path.split(python_exe_path)[-1]
                command = f'cd "{python_dir}" && {python_exe_name} "{self.gurobi_directory.text()}setup.py" install'
                has_run_error = subprocess.check_call(
                    command,
                    shell=True
                )  # The " are introduces in order to handle paths with blank spaces
            except subprocess.CalledProcessError:
                has_run_error = True
            if has_run_error:
                QMessageBox.warning(
                    self,
                    "Run Error",
                    "ERROR: Gurobi's setup.py run failed! "
                    "Please check that you use a recent Gurobi version. CNApy isn't compatible with older Gurobi versions.\n"
                    "Additionally, please check that you have followed the previous steps 1 to 3.\n"
                    "If this error keeps going even though you've checked the previous error,\n"
                    "try to run CNApy with administrator rights."
                )
            else:
                QMessageBox.information(
                    self,
                    "Success",
                    "Success in running the Python connection script! Now, you can proceed with the next steps."
                )
                self.get_and_set_environmental_variable()
