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
        self.rel_tol = 1e-9
        self.rounding = 3


class ProjectData:
    def __init__(self):
        self.cobra_py_model = cobra.Model()
        self.maps = []
        self.scen_values = {}
        self.clipboard = {}
        self.scenario_backup = {}
        self.comp_values = {}
        self.modes = []
        self.compute_color_type = 1


def CnaMap(name):
    return {"name": name,
            "background": "cnapylogo.svg",
            "bg-size": 1,
            "zoom": 0,
            "pos": (0, 0),
            "boxes": {}
            }
