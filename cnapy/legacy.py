import io
import os

import cobra

from cnapy.cnadata import CnaData

out = io.StringIO()
err = io.StringIO()
matlab = False
octave = False
try:
    import matlab.engine
    eng = matlab.engine.start_matlab()
    print("Matlab engine found")
    matlab = True
except:
    print("Matlab engine not found")
    try:
        import oct2py
        eng = oct2py.Oct2Py()
        print("Octave engine found")
        octave = True
    except:
        print("Octave engine not found")


def restart_cna(cna_path):
    try:
        a = eng.eval('cd("' + cna_path + '")')
        print(a)
        a = eng.eval("startcna(1)", nargout=0)
        print(a)
        return True
    except:
        print("CNA not found. Check your CNA path!")
        return False


def createCobraModel(appdata: CnaData):
    if matlab or octave:
        cobra.io.save_matlab_model(
            appdata.project.cobra_py_model, os.path.join(appdata.cna_path+"/cobra_model.mat"), varname="cbmodel")


def get_matlab_engine():
    return eng


def is_matlab_ready():
    return matlab


def is_octave_ready():
    return octave
