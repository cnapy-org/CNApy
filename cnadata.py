import cobra
from dataclasses import dataclass


class CnaData:
    def __init__(self):
        self.cobra_py_model = cobra.Model()
        self.maps = []
        self.values = {}
        self.high = 0.0
        self.low = 0.0


def CnaMap(name):
    return {"name": name,
            "boxes": {},
            "background": "cnapylogo.svg"
            }
