import cobra


class PnaData:
    def __init__(self):
        self.cobra_py_model = cobra.Model()
        self.maps = [{}]
        self.values = {}
