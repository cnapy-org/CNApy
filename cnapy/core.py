"""UI independent computations"""

from typing import Dict, Tuple

import cobra
import numpy
from cobra.util.array import create_stoichiometric_matrix
from cobra.flux_analysis import flux_variability_analysis

import efmtool_link.efmtool4cobra as efmtool4cobra
import efmtool_link.efmtool_extern as efmtool_extern
from cnapy.flux_vector_container import FluxVectorMemmap


def efm_computation(model: cobra.Model, scen_values: Dict[str, Tuple[float, float]], constraints: bool):
    stdf = create_stoichiometric_matrix(
        model, array_type='DataFrame')
    reversible, irrev_backwards_idx = efmtool4cobra.get_reversibility(
        model)
    if len(irrev_backwards_idx) > 0:
        irrev_back = numpy.zeros(len(reversible), dtype=numpy.bool)
        irrev_back[irrev_backwards_idx] = True
    scenario = {}
    if constraints:
        for r in scen_values.keys():
            (vl, vu) = scen_values[r]
            if vl == vu and vl == 0:
                r_idx = stdf.columns.get_loc(r)
                reversible = numpy.delete(reversible, r_idx)
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
    if work_dir is None:
        ems = None
    else:
        ems = FluxVectorMemmap('efms.bin', reac_id,
                               containing_temp_dir=work_dir)
        if len(irrev_backwards_idx) > 0:
            ems.fv_mat[:, irrev_backwards_idx] *= -1

    return (ems, scenario)


def fva_computation(model: cobra.Model, scen_values, fraction_of_optimum=0.0):
    ''' throws cobra.exceptions.Infeasible:'''
    load_values_into_model(scen_values,  model)
    for r in model.reactions:
        r.objective_coefficient = 0

    solution = flux_variability_analysis(
        model, fraction_of_optimum=fraction_of_optimum)

    return solution


def load_values_into_model(values: Dict[str, Tuple[float, float]], model: cobra.Model):
    ''' load the values into the model'''
    for x in values:
        try:
            y = model.reactions.get_by_id(x)
        except KeyError:
            print('reaction', x, 'not found!')
        else:
            (vl, vu) = values[x]
            y.lower_bound = vl
            y.upper_bound = vu
