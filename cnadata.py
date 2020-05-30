import cobra
from dataclasses import dataclass
from PySide2.QtGui import QColor


class CnaData:
    def __init__(self):
        self.cobra_py_model = cobra.Model()
        self.maps = []
        self.scen_values = {}
        self.comp_values = {}
        self.modes = []
        self.high = 0.0
        self.low = 0.0

    def set_scen_values(self, scen_values):
        self.scen_values = scen_values

    def set_comp_values(self, comp_values):
        self.comp_values = comp_values

    def compute_color(self, value: float):
        (low, high) = self.high_and_low()
        if value > 0.0:
            if high == 0.0:
                h = 255
            else:
                h = value * \
                    255 / high
            return QColor.fromRgb(255-h, 255, 255-h)
        else:
            if low == 0.0:
                h = 255
            else:
                h = value * \
                    255 / low
            return QColor.fromRgb(255, 255 - h, 255 - h)

    def high_and_low(self):
        low = 0
        high = 0
        for key in self.scen_values.keys():
            if self.scen_values[key] < low:
                low = self.scen_values[key]
            if self.scen_values[key] > high:
                high = self.scen_values[key]
        for key in self.comp_values.keys():
            if self.comp_values[key] < low:
                low = self.comp_values[key]
            if self.comp_values[key] > high:
                high = self.comp_values[key]

        return (low, high)


def CnaMap(name):
    return {"name": name,
            "background": "cnapylogo.svg",
            "bg-size": 1,
            "zoom": 0,
            "pos": (0, 0),
            "boxes": {}
            }
