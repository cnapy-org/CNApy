import cobra
from dataclasses import dataclass


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
        (self.low, self.high) = high_and_low(0, 0, scen_values)
        self.scen_values = scen_values
        (self.low, self.high) = high_and_low(
            self.low, self.high, self.comp_values)

    def set_comp_values(self, comp_values):
        (self.low, self.high) = high_and_low(0, 0, comp_values)
        self.comp_values = comp_values
        (self.low, self.high) = high_and_low(
            self.low, self.high, self.scen_values)


def high_and_low(low, high, values):
    low = low
    high = high
    for key in values.keys():
        if values[key] < low:
            low = values[key]
        if values[key] > high:
            high = values[key]

    return (low, high)


def CnaMap(name):
    return {"name": name,
            "background": "cnapylogo.svg",
            "bg-size": 1,
            "zoom": 0,
            "pos": (0, 0),
            "boxes": {}
            }
