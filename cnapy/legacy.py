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
    meng = CNAMatlabEngine(cna_path)
    print("CNA Matlab engine available")
    eng = meng
except:
    meng = None
    print("CNA Matlab engine not working")

try:
    from cnapy.CNA_MEngine import CNAoctaveEngine
    oeng = CNAoctaveEngine(cna_path)
    print("CNA octave engine available")
    eng = oeng
except:
    oeng = None
    print("CNA octave engine not working")


def restart_cna(cna_path):
    try:
        print(cna_path)
        a = eng.cd(cna_path)
        print(a)
        a = eng.eval("startcna(1)", nargout=0)
        print(a)
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
    return oeng is not None

def is_matlab_set():
    return isinstance(eng, CNAMatlabEngine)


def is_octave_set():
    return isinstance(eng, CNAoctaveEngine)


def use_matlab():
    """
    switch to Matlab
    """
    global eng
    if meng is not None:
        eng = meng
        print("use matlab engine")

def use_octave():
    """
    switch to Octave
    """
    global eng
    if oeng is not None:
        eng = oeng
        print("use octave engine")
