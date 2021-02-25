import configparser
import io
import os
import traceback

import appdirs
import cobra

from cnapy.cnadata import CnaData
from importlib import reload
import cnapy.CNA_MEngine

def try_matlab_engine():
    try:
        print("Try Matlab engine ...")
        reload(cnapy.CNA_MEngine)
        from cnapy.CNA_MEngine import CNAMatlabEngine
        meng = CNAMatlabEngine()
        print("Matlab engine available")
        return meng
    except:
        output = io.StringIO()
        traceback.print_exc(file=output)
        exstr = output.getvalue()
        print(exstr)
        print("Matlab engine not available")
        return None


def try_octave_engine(octave_executable: str):
    if os.path.isfile(octave_executable):
        os.environ['OCTAVE_EXECUTABLE'] = octave_executable
    try:
        print("Try Octave engine ...")
        from cnapy.octave_engine import CNAoctaveEngine
        oeng = CNAoctaveEngine()
        print("Octave engine available")
        return oeng
    except:
        # output = io.StringIO()
        # traceback.print_exc(file=output)
        # exstr = output.getvalue()
        # print(exstr)
        print("Octave engine not available")
        return None


def try_cna(eng, cna_path):
    if eng is None:
        print("Can't try CNA because no engine (matlab/octave) selected.")
        return False
    else:
        try:
            print("Try CNA ...")
            eng.cd(cna_path)
            eng.eval("startcna(1)", nargout=0)
            print("CNA seems working.")
            return True
        except:
            # output = io.StringIO()
            # traceback.print_exc(file=output)
            # exstr = output.getvalue()
            # print(exstr)
            print("CNA not working. Maybe check your CNA path!")
            return False
