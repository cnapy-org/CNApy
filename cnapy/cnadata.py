"""The application data"""
import os
import pathlib
from tempfile import TemporaryDirectory
from typing import Dict, Tuple

import appdirs
import cobra
import pkg_resources
from qtpy.QtCore import Qt, QThreadPool
from qtpy.QtGui import QColor


class CnaData:
    ''' The application data '''

    def __init__(self):

        self.threadpool = QThreadPool()
        print("Multithreading with maximum %d threads" %
              self.threadpool.maxThreadCount())

        self.version = "cnapy-dev-0.1"
        self.format_version = 1
        self.unsaved = False
        self.project = ProjectData()
        self.octave_executable = ""
        self.matlab_path = ""
        self.engine = None
        self.matlab_engine = None
        self.octave_engine = None
        self.modes_coloring = False
        self.scen_color = QColor(255, 170, 255)
        self.comp_color = QColor(170, 170, 255)
        self.special_color_1 = Qt.yellow
        self.special_color_2 = QColor(170, 255, 0)  # for bounds excluding 0
        self.default_color = Qt.gray
        self.abs_tol = 0.0001
        self.rounding = 3
        self.cna_path = ""
        self.selected_engine = None
        self.work_directory = str(os.path.join(
            pathlib.Path.home(), "CNApy-projects"))
        self.temp_dir = TemporaryDirectory()
        self.conf_path = os.path.join(appdirs.user_config_dir(
            "cnapy", roaming=True, appauthor=False), "cnapy-config.txt")
        self.cobrapy_conf_path = os.path.join(appdirs.user_config_dir(
            "cnapy", roaming=True, appauthor=False), "cobrapy-config.txt")
        self.scenario_past = []
        self.scenario_future = []

    def scen_values_set(self, reaction: str, values: (float, float)):
        self.project.scen_values[reaction] = values
        self.scenario_past.append(("set", reaction, values))
        self.scenario_future.clear()

    def scen_values_pop(self, reaction: str):
        self.project.scen_values.pop(reaction, None)
        self.scenario_past.append(("pop", reaction, 0))
        self.scenario_future.clear()

    def scen_values_clear(self):
        self.project.scen_values.clear()
        self.scenario_past.append(("clear", "all", 0))
        self.scenario_future.clear()

    def recreate_scenario_from_history(self):
        self.project.scen_values = {}
        for (tag, reaction, values) in self.scenario_past:
            if tag == "set":
                self.project.scen_values[reaction] = values
            elif tag == "pop":
                self.project.scen_values.pop(reaction, None)
            elif tag == "clear":
                self.project.scen_values.clear()

    def create_cobra_model(self):
        if self.engine is not None:  # matlab or octave:
            cobra.io.save_matlab_model(
                self.project.cobra_py_model, os.path.join(self.cna_path+"/cobra_model.mat"), varname="cbmodel")
        else:
            print("Could not create a CobraModel because no engine is selected")

    def is_matlab_ready(self):
        return self.matlab_engine is not None

    def is_octave_ready(self):
        return self.octave_engine is not None

    def is_matlab_set(self):
        return str(type(self.engine)) == "<class 'cnapy.CNA_MEngine.CNAMatlabEngine'>"

    def is_octave_set(self):
        return str(type(self.engine)) == "<class 'cnapy.CNA_MEngine.CNAoctaveEngine'>"

    def select_engine(self):
        """
        select Engine
        """
        if self.selected_engine == "matlab":
            if self.matlab_engine is not None:
                self.engine = self.matlab_engine
                print("Using Matlab engine!")
            else:
                self.selected_engine = None
                print("No engine selected!")
        elif self.selected_engine == "octave":
            if self.octave_engine is not None:
                self.engine = self.octave_engine
                print("Using Octave engine!")
            else:
                self.selected_engine = None
                print("No engine selected!")
        else:
            print("No engine selected!")


class ProjectData:
    ''' The cnapy project data '''

    def __init__(self):
        self.name = "Unnamed project"
        self.cobra_py_model = cobra.Model()
        self.maps = {}
        self.scen_values: Dict[str, Tuple[float, float]] = {}
        self.clipboard: Dict[str, Tuple[float, float]] = {}
        self.comp_values: Dict[str, Tuple[float, float]] = {}
        self.modes: Dict[str, Tuple[float, float]] = []
        self.meta_data = {}


def CnaMap(name):
    background_svg = pkg_resources.resource_filename(
        'cnapy', 'data/cnapylogo.svg')
    return {"name": name,
            "background": background_svg,
            "bg-size": 1,
            "zoom": 0,
            "pos": (0, 0),
            "boxes": {}
            }
