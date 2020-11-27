import configparser
import io
import os

import cobra

from cnapy.cnadata import CnaData

configParser = configparser.RawConfigParser()
configFilePath = r'cnapy-config.txt'
configParser.read(configFilePath)
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
        print("CNA not found. Check your CNA path!")
        return False


def createCobraModel(appdata: CnaData):
    if eng is not None:  # matlab or octave:
        cobra.io.save_matlab_model(
            appdata.project.cobra_py_model, os.path.join(appdata.cna_path+"/cobra_model.mat"), varname="cbmodel")


def get_matlab_engine():
    return eng


def is_matlab_ready():
    return meng is not None and isinstance(eng, CNAMatlabEngine)


def is_octave_ready():
    return oeng is not None and isinstance(eng, CNAoctaveEngine)


def use_matlab():
    global eng
    if meng is not None:
        eng = meng


def use_octave():
    global eng
    if oeng is not None:
        eng = oeng


"""
for use in console to switch between octave/Matlab
from cnapy.legacy import use_matlab, use_octave, get_matlab_engine
"""
