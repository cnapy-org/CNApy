import io

import cobra

from cnapy.cnadata import CnaData

try:
    import matlab.engine
    eng = matlab.engine.start_matlab()

    out = io.StringIO()
    err = io.StringIO()
    print("Matlab engine found")
    me = True
except:
    print("Matlab engine not found")
    me = False


def createCobraModel(appdata):
    if me:
        a = eng.eval('cd("'+appdata.cna_path+'")')
        cobra.io.save_matlab_model(
            appdata.project.cobra_py_model, appdata.cna_path+"cobra_model.mat", varname="cbmodel")


def get_matlab_engine():
    return eng


def is_matlab_engine_ready():
    return me
