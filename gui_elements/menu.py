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

# External modules
import os
import sys
import tkinter
import webbrowser
# Internal modules
from gui_elements.subwindow_about import SubwindowAbout


class Menu(tkinter.Menu):
    """
    """
    def __init__(self, parent):
        """
        """
        super().__init__()
        self.parent = parent

        # "File" cascade.
        menu_file = tkinter.Menu(self)
        menu_file["tearoff"] = 0
        menu_file.add_command(label="New project...", command=self._file_new_project)
        menu_file.add_command(label="Save project", command=self._file_save_project)
        menu_file.add_command(label="Save project as...", command=self._file_save_project_as)
        menu_file.add_command(label="Open project", command=self._file_open_project)
        menu_file.add_command(label="End", command=self._file_end)
        self.add_cascade(label="File", menu=menu_file)

        # "Edit" cascade.
        menu_edit = tkinter.Menu(self)
        menu_edit["tearoff"] = 0
        menu_edit.add_command(label="Network composer...", command=self._edit_network_composer)
        self.add_cascade(label="Edit", menu=menu_edit)

        # "Find" cascade.
        menu_find = tkinter.Menu(self)
        menu_find["tearoff"] = 0
        menu_find.add_command(label="Find reaction...", command=self._find_reaction)
        self.add_cascade(label="Find", menu=menu_find)

        # "Analysis" cascade.
        menu_analysis = tkinter.Menu(self)
        menu_analysis["tearoff"] = 0
        menu_analysis.add_command(label="Flux Balance Analysis (FBA)", command=self._analysis_fba)
        menu_analysis.add_command(label="Flux Variability Analysis (FVA)", command=self._analysis_fva)
        self.add_cascade(label="Analysis", menu=menu_analysis)

        # "Help" cascade.
        menu_help = tkinter.Menu(self)
        menu_help["tearoff"] = 0
        menu_help.add_command(label="Manual (in web browser)",
                              command=self._help_manual)
        menu_help.add_command(label="About PyNetAnalyzer...",
                              command=self._help_about)
        self.add_cascade(label="Help", menu=menu_help)

    def _analysis_fba(self):
        """
        """
        pass

    def _analysis_fva(self):
        """
        """
        pass

    def _edit_network_composer(self):
        """
        """
        pass

    def _file_new_project(self):
        """
        """
        pass

    def _file_save_project(self):
        """
        """
        pass

    def _file_save_project_as(self):
        """
        """
        pass

    def _file_open_project(self):
        """
        """
        pass

    def _file_end(self):
        """Closes PyNetAnalyzer. Returns 0."""
        sys.exit(0)

    def _find_reaction(self):
        """
        """
        pass

    def _help_about(self):
        """
        """
        info = "PyNetAnalyzer Alpha (c) PSB & ST 2019\n"
        license_filepath = standardize_folder(os.getcwd()) + "LICENSE.md"
        SubwindowAbout(title="About PyNetAnalyzer...", info=info,
                       license_filepath=license_filepath)

    def _help_manual(self):
        """Opens PyNetAnalyzer's manual with the standard browser."""
        webbrowser.open(standardize_folder(os.getcwd()) + "/docs/manual.html")
