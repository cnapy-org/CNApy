import tempfile
import os
import re
from platform import system
from pkg_resources import VersionConflict

try:
    if system() == "Linux":
        octave_version = re.search(r'(?<=version).*?(?=\n|$|\.)',os.popen("octave -v").read())
        octave_version = int(octave_version.group(0))
        if octave_version <= 4:
            raise VersionConflict()
    
    from oct2py import Oct2Py # calls Oct2Py() in __init__ which creates a temporary directory that is not deleted
    from oct2py.utils import Oct2PyError

    class CNAoctaveEngine(Oct2Py):
        def __init__(self):
            self.temp_dir_obj = tempfile.TemporaryDirectory() # for automatic cleanup
            Oct2Py.__init__(self, temp_dir=self.temp_dir_obj.name)

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

        def try_cna(self, cna_path) -> bool:
            try:
                print("Try CNA ...")
                self.cd(cna_path)
                self.eval("startcna(1)", nargout=0)
                print("CNA seems working.")
                return True
            except Oct2PyError:
                print("CNA not availabe ... continue with CNA disabled.")
                return False

except: #(VersionConflict, OSError, EOFError):
    pass
