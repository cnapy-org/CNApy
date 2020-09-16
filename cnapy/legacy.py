import io

import cobra

from cnapy.cnadata import CnaData
from cnapy.gui_elements.efm_dialog import EFMDialog

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


def matlab_CNAcomputeEFM(appdata: CnaData, centralwidget):

    if me:
        model = appdata.project.cobra_py_model
        dialog = EFMDialog(appdata, centralwidget, eng, out, err)
        dialog.exec_()
    else:
        print("matlab_CNAcomputeEFM() needs MATLAB: No Matlab installed")
