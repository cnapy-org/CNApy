"""UI independent computations"""

import efmtool_link.efmtool4cobra as efmtool4cobra
import efmtool_link.efmtool_extern as efmtool_extern
import numpy
from cobra.util.array import create_stoichiometric_matrix

from cnapy.cnadata import CnaData


def efm_computation(appdata: CnaData, constraints: bool):
    stdf = create_stoichiometric_matrix(
        appdata.project.cobra_py_model, array_type='DataFrame')
    reversible, irrev_backwards_idx = efmtool4cobra.get_reversibility(
        appdata.project.cobra_py_model)
    if len(irrev_backwards_idx) > 0:
        irrev_back = numpy.zeros(len(reversible), dtype=numpy.bool)
        irrev_back[irrev_backwards_idx] = True
    scenario = {}
    if constraints:
        for r in appdata.project.scen_values.keys():
            (vl, vu) = appdata.project.scen_values[r]
            if vl == vu and vl == 0:
                r_idx = stdf.columns.get_loc(r)
                del reversible[r_idx]
                # delete the column with this reaction id from the data frame
                del stdf[r]
                if len(irrev_backwards_idx) > 0:
                    irrev_back = numpy.delete(irrev_back, r_idx)
                scenario[r] = (0, 0)
    if len(irrev_backwards_idx) > 0:
        irrev_backwards_idx = numpy.where(irrev_back)[0]
        stdf.values[:, irrev_backwards_idx] *= -1
    work_dir = efmtool_extern.calculate_flux_modes(
        stdf.values, reversible, return_work_dir_only=True)
    reac_id = stdf.columns.tolist()

    return (work_dir, reac_id, scenario, irrev_backwards_idx)
