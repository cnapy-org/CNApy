''' Tests '''
import cobra

import cnapy.core


def test_efm_computation():
    model = cobra.Model()
    scen_values = {}
    cnapy.core.efm_computation(model, scen_values, True)
