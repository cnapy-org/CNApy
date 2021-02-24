import configparser
import io
import os
import traceback

import appdirs
import cobra

from cnapy.cnadata import CnaData

conf_path = os.path.join(appdirs.user_config_dir(
    "cnapy", roaming=True, appauthor=False), "cnapy-config.txt")

configParser = configparser.RawConfigParser()
configParser.read(conf_path)
try:
    cna_path = configParser.get('cnapy-config', 'cna_path')
except:
    pass

out = io.StringIO()
err = io.StringIO()
eng = None

try:
    from cnapy.CNA_MEngine import CNAMatlabEngine
    meng = CNAMatlabEngine()
    print("Matlab engine available")
    eng = meng
except:
    meng = None

try:
    from cnapy.ocatve_engine import CNAoctaveEngine
    oeng = CNAoctaveEngine()
    print("Octave engine available")
    eng = oeng
except:
    output = io.StringIO()
    traceback.print_exc(file=output)
    exstr = output.getvalue()
    print(exstr)
    oeng = None
    print("Octave engine not available")


def reset_engine():
    global eng
    if is_octave_set():
        oeng = CNAoctaveEngine()
        eng = oeng
    elif is_matlab_set():
        meng = CNAMatlabEngine()
        eng = meng


def restart_cna(cna_path):
    reset_engine()
    try:
        eng.cd(cna_path)
        eng.eval("startcna(1)", nargout=0)
        print("CNA path found. CNA seems working.")
        return True
    except:
        output = io.StringIO()
        traceback.print_exc(file=output)
        exstr = output.getvalue()
        print(exstr)
        print("CNA not found. Check your CNA path!")
        return False


def createCobraModel(appdata: CnaData):
    if eng is not None:  # matlab or octave:
        cobra.io.save_matlab_model(
            appdata.project.cobra_py_model, os.path.join(appdata.cna_path+"/cobra_model.mat"), varname="cbmodel")


def get_matlab_engine():
    return eng


def is_matlab_ready():
    return meng is not None


def is_octave_ready():
    try:
        from cnapy.CNA_MEngine import CNAoctaveEngine
        oeng = CNAoctaveEngine()
    except:
        oeng = None

    return oeng is not None


def is_matlab_set():
    return str(type(eng)) == "<class 'cnapy.CNA_MEngine.CNAMatlabEngine'>"


def is_octave_set():
    return str(type(eng)) == "<class 'cnapy.CNA_MEngine.CNAoctaveEngine'>"


def use_matlab():
    """
    switch to Matlab
    """
    global eng
    if meng is not None:
        eng = meng
        print("Using Matlab engine")


def use_octave():
    """
    switch to Octave
    """
    global eng
    if oeng is not None:
        eng = oeng
        print("Using Octave engine")
