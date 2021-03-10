
try:
    from oct2py import Oct2Py

    class CNAoctaveEngine(Oct2Py):
        def __init__(self):
            Oct2Py.__init__(self)

        def start_cna(self, cna_path):
            self.cd(cna_path)
            self.startcna(1)

        def get_reacID(self):
            self.eval("reac_id = cellstr(cnap.reacID);")
            reac_id = self.pull('reac_id')
            reac_id = reac_id.tolist()
            return reac_id

        def is_cplex_matlab_ready(self):
            return self.eval('cnan.cplex_interface.matlab;')

        def is_cplex_java_ready(self):
            return self.eval('cnan.cplex_interface.java;')

except ModuleNotFoundError:
    pass
