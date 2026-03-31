"""The CPLEX configuration dialog"""
import os
import subprocess
import sys
import platform
from qtpy.QtWidgets import (QDialog, QFileDialog,
                            QLabel, QMessageBox, QPushButton,
                            QVBoxLayout)
from cnapy.appdata import AppData

class CplexNewConfigurationDialog(QDialog):
    """A dialog to set values in cnapy-config.txt"""

    def __init__(self, appdata: AppData):
        QDialog.__init__(self)
        self.setWindowTitle("Configure IBM CPLEX Full Version (up to CPLEX version 22.1.1)")
        self.appdata = appdata

        self.layout = QVBoxLayout()

        label = QLabel(
            "NOTE: This CPLEX configuration assistant is for IBM CPLEX versions >=22.1.2; for older versions, use the other assistant in CNApy's 'Config' menu\n\n"
            "By default, right after CNApy's installation, you have only access to the IBM CPLEX Community Edition which can only handle small problems.\n"
            "In order to use the full version of IBM CPLEX, with no variable number limit, follow the next steps in the given order:\n"
            "1. (only necessary if you encounter problems with the following steps despite the installation tips in step 3)\n"
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
            "2. (if not already done) Obtain an IBM CPLEX license and download IBM CPLEX itself onto your computer.\n"
            "3. (if not already done) Install IBM CPLEX by following the IBM CPLEX installer's instructions. Remember where you installed CPLEX.\n"
            "4. Select the folder in which you've installed IBM CPLEX by pressing the following button:"
        )
        self.layout.addWidget(label)

        self.cplex_directory = QPushButton()
        self.cplex_directory.setText(
            "NOT SET YET! PLEASE SET THE PATH TO THE IBM CPLEX MAIN FOLDER (see steps 1 to 4 above)."
        )
        self.layout.addWidget(self.cplex_directory)

        label = QLabel(
            "5. (only if step 3 and 4 were successful) Run the IBM CPLEX Python connection script by pressing the following button:"
        )
        self.python_run_button = QPushButton("Run Python connection script")
        self.layout.addWidget(label)
        self.layout.addWidget(self.python_run_button)

        label = QLabel(
            "6. After you've finished all previous steps 1 to 5, restart CNApy and IBM CPLEX should be correctly configured :D"
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
        dialog = QFileDialog(self)
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
            has_run_error = False
            try:
                result = subprocess.run(
                    ["docplex", "config", "--upgrade", self.cplex_directory.text()],
                    check=True,
                    capture_output=True,
                    text=True
                )
                print("Success:", result.stdout)
            except subprocess.CalledProcessError as e:
                print(f"Command failed with return code {e.returncode}")
                print(f"stdout: {e.stdout}")
                print(f"stderr: {e.stderr}")
                has_run_error = True
            if has_run_error:
                QMessageBox.warning(
                    self,
                    "Run Error",
                    f"ERROR: The command docplex config --upgrade {self.cplex_directory.text()} run failed! "
                    f"Error message on stdout: {e.stdout}"
                    f"Error message on stderr: {e.stderr}"
                    "Please check that you use an IBM CPLEX version >= 22.1.2. For older CPLEX versions, use CNApy's other IBM CPLEX connection script.\n"
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
