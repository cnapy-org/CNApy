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
        self.compute_color_type = 1

    def set_scen_values(self, scen_values):
        self.scen_values = scen_values

    def set_comp_values(self, comp_values):
        self.comp_values = comp_values

    def compute_color(self, value: float):
        if self.compute_color_type == 1:
            return self.compute_color_heat(value)
        elif self.compute_color_type == 2:
            return self.compute_color_onoff2(value)
        elif self.compute_color_type == 3:
            return self.compute_color_range(value)
        else:
            return QColor.fromRgb(255, 255, 255)

    def compute_color_range(self, value):

        (low, high) = self.high_and_low_range()
        if not isinstance(value, float):
            (min, max) = value
            value = min + (max - min) / 2

        if value > 0.0:
            if high == 0.0:
                h = 255
            else:
                h = value * 255 / high
            return QColor.fromRgb(255-h, 255, 255-h)
        else:
            if low == 0.0:
                h = 255
            else:
                h = value * 255 / low
            return QColor.fromRgb(255, 255 - h, 255 - h)

        return QColor.fromRgb(170, 170, 20)

    def high_and_low_range(self):
        low = 0.0
        high = 0.0
        for key in self.scen_values.keys():
            if isinstance(self.scen_values[key], float):
                if self.scen_values[key] < low:
                    low = self.scen_values[key]
                if self.scen_values[key] > high:
                    high = self.scen_values[key]
            else:
                (min, max) = self.scen_values[key]
                if min < low:
                    low = min
                if max > high:
                    high = max

        for key in self.comp_values.keys():
            if isinstance(self.comp_values[key], float):
                if self.comp_values[key] < low:
                    low = self.comp_values[key]
                if self.comp_values[key] > high:
                    high = self.comp_values[key]
            else:
                (min, max) = self.comp_values[key]
                if min < low:
                    low = min
                if max > high:
                    high = max

        return (low, high)

    def compute_color_heat(self, value: float):
        (low, high) = self.high_and_low()
        if value > 0.0:
            if high == 0.0:
                h = 255
            else:
                h = value * 255 / high
            return QColor.fromRgb(255-h, 255, 255-h)
        else:
            if low == 0.0:
                h = 255
            else:
                h = value * 255 / low
            return QColor.fromRgb(255, 255 - h, 255 - h)

    def compute_color_onoff(self, value: float):
        if value != 0.0:
            return QColor.fromRgb(0, 255, 0)
        else:
            return QColor.fromRgb(255, 0, 0)

    def compute_color_onoff2(self, value: float):
        (low, high) = self.high_and_low()
        high = max(abs(low), high)
        if value != 0.0:
            h = abs(value) * 255 / high
            return QColor.fromRgb(255-h, 255, 255-h)
        else:
            return QColor.fromRgb(255, 0, 0)

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
