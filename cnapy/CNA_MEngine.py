import io
#from abc import ABC, abstractmethod

import os
#os.environ['OCTAVE_EXECUTABLE']= 'E:\octave\Octave-5.2.0\mingw64\\bin\octave-cli.exe'


class CNA_Methods:  # (ABC):
    """
    convenience methods for cnapy
    """
    # def __init__(self):
    #     self.cplex_matlab_working= None;
    #     self.cplex_java_working= None;

    def read_cnapy_model(self):
        self.eval("load cobra_model.mat", nargout=0)
        self.eval("cnap= CNAcobra2cna(cbmodel);", nargout=0)

    # def cplex_matlab_working(self):
    #     return self.which('Cplex') != ''

    # def check_cplex_interfaces(self):
    #     self.cplex_matlab_working= self.eval('cnan.cplex_interface.matlab;');
    #     self.cplex_java_working= self.eval('cnan.cplex_interface.java;');


try:
    import matlab.engine
    from matlab.engine import MatlabEngine, pythonengine

    # class MyMatlabEngine(MatlabEngine):
    #     def __init__(self, matlab):
    #         super.__init__(self, matlab)

    #     def __setattr__(self, kw, value):
    #         print('my __setattr__')
    #         print(kw)
    #         if kw not in ['cplex_matlab_working', 'cplex_java_working']:
    #             print("raise AttributeError(pythonengine.getMessage('AttrCannotBeAddedToM'))")
    #         else:
    #             self.__dict__[kw] = value

    class CNAMatlabEngine(CNA_Methods, MatlabEngine):
        def __init__(self, cna_path):
            # CNA_Methods.__init__(self)
            # have go to via MatlabFuture because the MatlabEngine constructor requires a Matlab handle
            cwd = os.getcwd()
            os.chdir(cna_path)
            future = matlab.engine.matlabfuture.MatlabFuture(
                option="-nodesktop")
            super().__init__(matlab.engine.pythonengine.getMATLAB(future._future))
            os.chdir(cwd)
            self.cd(cna_path)
            self.startcna(1, nargout=0)
            # self.check_cplex_interfaces()

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

    class CNAoctaveEngine(CNA_Methods, Oct2Py):
        def __init__(self, cna_path):
            # CNA_Methods.__init__(self)
            Oct2Py.__init__(self)
            self.cd(cna_path)
            self.startcna(1)
            # self.check_cplex_interfaces()
            self.cplex_matlab_ready = self.eval('cnan.cplex_interface.matlab;')
            self.cplex_java_ready = self.eval('cnan.cplex_interface.java;')

        def get_reacID(self):
            self.eval("reac_id = cellstr(cnap.reacID);")
            reac_id = self.pull('reac_id')
            reac_id = reac_id.tolist()
            return reac_id

        def is_cplex_matlab_ready(self):
            return self.cplex_matlab_ready

        def is_cplex_java_ready(self):
            return self.cplex_java_ready

except:
    print('Octave is not available.')


def run_tests():
    cna_path = 'E:\gwdg_owncloud\CNAgit\CellNetAnalyzer'
    m = CNAMatlabEngine(cna_path)
    m.read_cnapy_model()
    a = m.get_reacID()
    o = CNAoctaveEngine(cna_path)
    o.read_cnapy_model()
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
