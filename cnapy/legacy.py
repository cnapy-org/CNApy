import io
import os
import traceback

from importlib import reload
import cnapy.CNA_MEngine
import cnapy.octave_engine


def try_matlab_engine():
    try:
        print("Try Matlab engine ...")
        reload(cnapy.CNA_MEngine)
        from cnapy.CNA_MEngine import CNAMatlabEngine
        meng = CNAMatlabEngine()
        print("Matlab engine available.")
        return meng
    except ImportError:
        print("Matlab engine not available ... continue with Matlab disabled.")
        return None


def try_octave_engine(octave_executable: str):
    if os.path.isfile(octave_executable):
        os.environ['OCTAVE_EXECUTABLE'] = octave_executable
    try:
        print("Try Octave engine ...")
        reload(cnapy.octave_engine)
        from cnapy.octave_engine import CNAoctaveEngine
        oeng = CNAoctaveEngine()
        print("Octave engine available.")
        return oeng
    except ImportError:
        print("Octave engine not available ... continue with Octave disabled.")
        return None
    except TypeError:
        print("Octave engine not available ... continue with Octave disabled.")
        return None


def try_cna(eng, cna_path: str) -> bool:
    if eng is None:
        print("Can't try CNA because no engine (matlab/octave) selected.")
        return False

    return eng.try_cna(cna_path)


def read_cnapy_model(engine):
    engine.eval("load cobra_model.mat", nargout=0)
    engine.eval("cnap= CNAcobra2cna(cbmodel);", nargout=0)
