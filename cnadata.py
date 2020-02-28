import cobra


class CnaData:
    def __init__(self):
        self.cobra_py_model = cobra.Model()
        self.maps = [{}]
        self.values = {}
        self.high = 0.0
        self.low = 0.0
