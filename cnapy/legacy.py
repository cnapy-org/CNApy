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


CNA_PATH = "/scratch/CellNetAnalyzer/"


def createCobraModel(model):
    if me:
        a = eng.eval('cd("'+CNA_PATH+'")')
        cobra.io.save_matlab_model(
            model, CNA_PATH+"cobra_model.mat", varname="cbmodel")


def matlab_CNAcomputeEFM(appdata: CnaData):

    if me:
        model = appdata.project.cobra_py_model
        dialog = EFMDialog(appdata, eng, out, err)
        dialog.exec_()

        # createCobraModel(model)
        # print(".")
        # a = eng.eval("startcna(1)", nargout=0, stdout=out, stderr=err)
        # print(".")
        # a = eng.eval("load('cobra_model.mat')",
        #              nargout=0, stdout=out, stderr=err)
        # print(".")
        # a = eng.eval("cnap = CNAcobra2cna(cbmodel);",
        #              nargout=0, stdout=out, stderr=err)
        # print(".")
        # a = eng.eval(
        #     "[ems, irrev_ems, ems_idx] = CNAcomputeEFM(cnap);", nargout=0, stdout=out, stderr=err)
        # ems = eng.workspace['ems']
        # idx = eng.workspace['ems_idx']
        # a = eng.eval("reac_id = cellstr(cnap.reacID).';",
        #              nargout=0, stdout=out, stderr=err)
        # reac_id = eng.workspace['reac_id']

        # # turn vectors into maps
        # for mode in ems:
        #     count_ccc = 0
        #     omode = {}
        #     for e in mode:
        #         idx2 = int(idx[0][count_ccc])-1
        #         reaction = reac_id[idx2]
        #         print("element: ", count_ccc, idx2, reaction, e)
        #         count_ccc += 1
        #         omode[reaction] = e
        #     oems.append(omode)
    else:
        print("matlab_CNAcomputeEFM() needs MATLAB: No Matlab installed")
