import os
from tempfile import TemporaryDirectory
from typing import Dict, Tuple

import appdirs
import cobra
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor


class CnaData:

    def __init__(self):
        self.first_run = 1
        self.unsaved = False
        self.project = ProjectData()
        self.octave_executable = ""
        self.matlab_path = ""
        self.engine = None
        self.matlab_engine = None
        self.octave_engine = None
        self.Scencolor = Qt.green
        self.Compcolor = QColor(170, 170, 255)
        self.SpecialColor1 = Qt.yellow
        self.SpecialColor2 = QColor(170, 255, 0)  # for bounds excluding 0
        self.Defaultcolor = Qt.gray
        self.abs_tol = 0.0001
        self.rounding = 3
        self.cna_path = ""
        self.default_engine = "matlab"
        self.work_directory = ""
        self.temp_dir = TemporaryDirectory()
        self.conf_path = os.path.join(appdirs.user_config_dir(
            "cnapy", roaming=True, appauthor=False), "cnapy-config.txt")

    def createCobraModel(self):
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

    def use_matlab(self):
        """
        switch to Matlab
        """
        if self.matlab_engine is not None:
            self.engine = self.matlab_engine
            print("Using Matlab engine!")

    def use_octave(self):
        """
        switch to Octave
        """
        if self.octave_engine is not None:
            self.engine = self.octave_engine
            print("Using Octave engine!")


class ProjectData:
    def __init__(self):
        self.name = "Unnamed project"
        self.cobra_py_model = cobra.Model()
        self.maps = {}
        self.scen_values: Dict[str, Tuple[float, float]] = {}
        self.clipboard: Dict[str, Tuple[float, float]] = {}
        self.scenario_backup: Dict[str, Tuple[float, float]] = {}
        self.comp_values: Dict[str, Tuple[float, float]] = {}
        self.modes: Dict[str, Tuple[float, float]] = []
        self.compute_color_type = 1

    def load_scenario_into_model(self, model):
        for x in self.scen_values:
            try:
                y = model.reactions.get_by_id(x)
            except:
                print('reaction', x, 'not found!')
            else:
                (vl, vu) = self.scen_values[x]
                y.lower_bound = vl
                y.upper_bound = vu


def CnaMap(name):
    import pkg_resources
    background_svg = pkg_resources.resource_filename(
        'cnapy', 'data/cnapylogo.svg')
    return {"name": name,
            "background": background_svg,
            "bg-size": 1,
            "zoom": 0,
            "pos": (0, 0),
            "boxes": {}
            }
