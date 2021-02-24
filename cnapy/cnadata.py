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
        self.octave_executable = "/usr/bin"
        self.matlab_path = "/"
        self.Scencolor = Qt.green
        self.Compcolor = QColor(170, 170, 255)
        self.SpecialColor1 = Qt.yellow
        self.SpecialColor2 = QColor(170, 255, 0)  # for bounds excluding 0
        self.Defaultcolor = Qt.gray
        self.abs_tol = 0.0001
        self.rounding = 3
        self.cna_path = "/"
        self.default_engine = "matlab"
        self.work_directory = "/"
        self.temp_dir = TemporaryDirectory()
        self.conf_path = os.path.join(appdirs.user_config_dir(
            "cnapy", roaming=True, appauthor=False), "cnapy-config.txt")


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
