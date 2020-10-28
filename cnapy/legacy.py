import io
import os
import cobra
import oct2py

from cnapy.cnadata import CnaData

out = io.StringIO()
err = io.StringIO()
try:
    import matlab.engine
    eng = matlab.engine.start_matlab()
    print("Matlab engine found")
    matlab = True
except:
    print("Matlab engine not found")
    eng = oct2py.Oct2Py()
    matlab = False
    try:
        eng = oct2py.Oct2Py()
        print("Octave engine found")
        octave = True
    except:
        print("Octave engine not found")
        octave = False


def createCobraModel(appdata: CnaData):
    if matlab or octave:
        a = eng.eval('cd("' + appdata.cna_path + '")')
        print(a)
        cobra.io.save_matlab_model(
            appdata.project.cobra_py_model, os.path.join(appdata.cna_path+"/cobra_model.mat"), varname="cbmodel")


def get_matlab_engine():
    return eng


def is_matlab_ready():
    return matlab


def is_octave_ready():
    return octave
