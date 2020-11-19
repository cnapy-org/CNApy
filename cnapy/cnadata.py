from typing import Dict, Tuple

import cobra
from qtpy.QtCore import Qt
from qtpy.QtGui import QColor


class CnaData:

    def __init__(self):
        self.project = ProjectData()
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
    return {"name": name,
            "background": "cnapy/data/cnapylogo.svg",
            "bg-size": 1,
            "zoom": 0,
            "pos": (0, 0),
            "boxes": {}
            }
