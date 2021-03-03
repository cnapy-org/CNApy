import io
import os


def read_cnapy_model(engine):
    engine.eval("load cobra_model.mat", nargout=0)
    engine.eval("cnap= CNAcobra2cna(cbmodel);", nargout=0)


try:
    import matlab.engine
    from matlab.engine import MatlabEngine, pythonengine

    class CNAMatlabEngine(MatlabEngine):
        def __init__(self):
            future = matlab.engine.matlabfuture.MatlabFuture(
                option="-nodesktop")
            super().__init__(matlab.engine.pythonengine.getMATLAB(future._future))

        def start_cna(self, cna_path):
            cwd = os.getcwd()
            os.chdir(cna_path)
            future = matlab.engine.matlabfuture.MatlabFuture(
                option="-nodesktop")
            super().__init__(matlab.engine.pythonengine.getMATLAB(future._future))
            os.chdir(cwd)
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

except:
    pass
