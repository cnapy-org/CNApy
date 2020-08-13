from typing import Dict, Tuple
import cobra
from PySide2.QtCore import Qt
from PySide2.QtGui import QColor


class CnaData:

    def __init__(self):
        self.project = ProjectData()
        self.Scencolor = Qt.green
        self.Compcolor = QColor(170, 170, 255)
        self.SpecialColor = Qt.yellow
        self.Defaultcolor = Qt.gray
        self.rel_tol = 1e-7
        self.rounding = 3


class ProjectData:
    def __init__(self):
        self.cobra_py_model = cobra.Model()
        self.maps = []
        self.scen_values: Dict[str, Tuple[float, float]] = {}
        self.clipboard: Dict[str, Tuple[float, float]] = {}
        self.scenario_backup: Dict[str, Tuple[float, float]] = {}
        self.comp_values: Dict[str, Tuple[float, float]] = {}
        self.modes: Dict[str, Tuple[float, float]] = []
        self.compute_color_type = 1


def CnaMap(name):
    return {"name": name,
            "background": "cnapylogo.svg",
            "bg-size": 1,
            "zoom": 0,
            "pos": (0, 0),
            "boxes": {}
            }
