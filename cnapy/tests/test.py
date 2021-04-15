import cnapy.core
from cnapy.cnadata import CnaData


def test_efm_computation():
    appdata = CnaData()
    cnapy.core.efm_computation(appdata, True)
