import cobra
import io
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


def legacy_function(model):
    if me:
        createCobraModel(model)
        print(".")
        a = eng.eval("startcna(1)", nargout=0, stdout=out, stderr=err)
        print(".")
        a = eng.eval("load('cobra_model.mat')",
                     nargout=0, stdout=out, stderr=err)
        print(".")
        a = eng.eval("cnap =CNAcobra2cna(cbmodel);",
                     nargout=0, stdout=out, stderr=err)
        print(".")
        a = eng.eval(
            "[ems, irrev_ems, ems_idx] = CNAcomputeEFM(cnap);", nargout=0, stdout=out, stderr=err)
        ems = eng.workspace['ems']
        print(ems)
        print("ems length:", str(len(ems)))
    return
