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
meng = None
oeng = None


def try_matlab_engine():
    global meng
    try:
        print("Try Matlab engine ...")
        from cnapy.CNA_MEngine import CNAMatlabEngine
        meng = CNAMatlabEngine()
        print("Matlab engine available")
    except:
        meng = None
        print("Matlab engine not available")


def try_octave_engine():
    global oeng
    global eng
    try:
        print("Try Octave engine ...")
        from cnapy.octave_engine import CNAoctaveEngine
        oeng = CNAoctaveEngine()
        print("Octave engine available")
    except:
        # output = io.StringIO()
        # traceback.print_exc(file=output)
        # exstr = output.getvalue()
        # print(exstr)
        oeng = None
        print("Octave engine not available")


def reset_engine():
    global eng
    if is_octave_set():
        try_octave_engine()
        if oeng is not None:
            eng = oeng
    elif is_matlab_set():
        try_matlab_engine()
        if meng is not None:
            eng = meng


def try_cna(cna_path):
    # reset_engine()
    if eng is None:
        print("Can't try CNA because no engine (matlab/octave) selected.")
    else:
        try:
            print("Try CNA ...")
            eng.cd(cna_path)
            eng.eval("startcna(1)", nargout=0)
            print("CNA seems working.")
            return True
        except:
            output = io.StringIO()
            traceback.print_exc(file=output)
            exstr = output.getvalue()
            print(exstr)
            print("CNA not working. Maybe check your CNA path!")
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
        print("Using Matlab engine!")


def use_octave():
    """
    switch to Octave
    """
    global eng
    if oeng is not None:
        eng = oeng
        print("Using Octave engine!")
