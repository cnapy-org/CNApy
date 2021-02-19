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
    print('Matlab engine not available.')

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
except:
    print('Octave is not available.')


def run_tests():
    cna_path = 'E:\gwdg_owncloud\CNAgit\CellNetAnalyzer'
    m = CNAMatlabEngine()
    m.start_cna(cna_path)
    read_cnapy_model(m)
    a = m.get_reacID()
    o = CNAoctaveEngine()
    o.start_cna(cna_path)
    read_cnapy_model(o)
    b = o.get_reacID()
    # advanced stuff
    ptr = o.get_pointer('cnap')
    o.CNAcomputeEFM(ptr)

    # m.eval('x=SimpleClass()', nargout=0)
    # x= m.workspace['x']
    # m.foo(x, nargout= 0)

    # o.eval('x=SimpleClass()', nargout=0)
    # x= o.workspace['x']
    # #o.foo(x, nargout= 0) foo is not recognized as function

    # not needed in octave, has pointers to structs
    cnap = m.eval('CNA_MFNetwork(cnap);')
    ems = m.CNAcomputeEFM(cnap)

    o.eval('cnap_MFNetwork= CNA_MFNetwork(cnap);')
    cnap = o.get_pointer('cnap_MFNetwork')
    ems = o.CNAcomputeEFM(cnap)
