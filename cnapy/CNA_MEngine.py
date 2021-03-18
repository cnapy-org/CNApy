
try:
    import matlab.engine
    from matlab.engine import MatlabEngine, pythonengine

    class CNAMatlabEngine(MatlabEngine):
        def __init__(self):
            future = matlab.engine.matlabfuture.MatlabFuture(
                option="-nodesktop")
            super().__init__(matlab.engine.pythonengine.getMATLAB(future._future))

        def start_cna(self, cna_path):
            self.cd(cna_path)
            self.startcna(1, nargout=0)

        def get_reacID(self):
            self.eval("reac_id = cellstr(cnap.reacID);", nargout=0)
            reac_id = self.workspace['reac_id']
            return reac_id

        def is_cplex_matlab_ready(self):
            return self.eval('cnan.cplex_interface.matlab;')

        def is_cplex_java_ready(self):
            return self.eval('cnan.cplex_interface.java;')

        def try_cna(self, cna_path) -> bool:
            try:
                print("Try CNA ...")
                self.cd(cna_path)
                self.eval("startcna(1)", nargout=0)
                print("CNA seems working.")
                return True
            except:
                import io
                output = io.StringIO()
                import traceback
                traceback.print_exc(file=output)
                exstr = output.getvalue()
                print(exstr)
                print("CNA not availabe ... continue with CNA disabled.")
                return False
except ModuleNotFoundError:
    pass
