"""UI independent computations"""

from typing import Dict, Tuple

import numpy
import cobra
from cobra.util.array import create_stoichiometric_matrix
from optlang.symbolics import Zero

import efmtool_link.efmtool4cobra as efmtool4cobra
import efmtool_link.efmtool_extern as efmtool_extern
from cnapy.flux_vector_container import FluxVectorMemmap, FluxVectorContainer


def efm_computation(model: cobra.Model, scen_values: Dict[str, Tuple[float, float]], constraints: bool,
                    print_progress_function=print, abort_callback=None):
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
        stdf.values, reversible, return_work_dir_only=True, print_progress_function=print_progress_function, abort_callback=abort_callback)
    reac_id = stdf.columns.tolist()
    if work_dir is None:
        ems = None
    else:
        ems = FluxVectorMemmap('efms.bin', reac_id,
                               containing_temp_dir=work_dir)
        del work_dir  # lose this reference to the temporary directory to facilitate garbage collection
        is_irrev_efm = numpy.any(ems.fv_mat[:, reversible == 0], axis=1)
        rev_emfs_idx = numpy.nonzero(is_irrev_efm == False)[0]
        # reversible modes come in forward/backward pairs; delete one from each pair
        if len(rev_emfs_idx) > 0:
            del_idx = rev_emfs_idx[numpy.unique(
                ems.fv_mat[rev_emfs_idx, :] != 0., axis=0, return_index=True)[1]]
            is_irrev_efm = numpy.delete(is_irrev_efm, del_idx)
            ems = FluxVectorContainer(numpy.delete(
                ems.fv_mat, del_idx, axis=0), reac_id=ems.reac_id, irreversible=is_irrev_efm)
        else:
            ems.irreversible = is_irrev_efm
        if len(irrev_backwards_idx) > 0:
            ems.fv_mat[:, irrev_backwards_idx] *= -1

    return (ems, scenario)


class QPnotSupportedException(Exception):
    pass


def make_scenario_feasible(cobra_model: cobra.Model, scen_values: Dict[str, Tuple[float, float]], use_QP: bool = False,
                           default_weight: float = 1.0, abs_flux_weights: bool = False, weights_key: str = None):
    # default_weight must be a number > 0
    with cobra_model as model:
        model.objective = model.problem.Objective(Zero, direction='min')
        reactions_in_objective = []
        for reaction_id, scen_val in scen_values.items():
            try:
                reaction: cobra.Reaction = model.reactions.get_by_id(
                    reaction_id)
            except KeyError:
                print('reaction', reaction_id, 'not found!')
                continue
            # reactions set to 0 are still considered off
            if scen_val[0] == scen_val[1] and scen_val[0] != 0:
                reactions_in_objective.append(reaction_id)
                if abs_flux_weights:
                    weight = abs(scen_val[0])
                else:
                    if isinstance(weights_key, str):
                        try:
                            weight = float(reaction.annotation.get(
                                weights_key, default_weight))
                        except ValueError:  # the value from annotation cannot be converted to float
                            weight = 0
                        if weight <= 0:
                            print("The value of annotation key '"+weights_key+"' of reaction'" +
                                  reaction_id+"' is not a positive number, using default weight.")
                            weight = default_weight
                    else:
                        weight = default_weight

                if use_QP:
                    try:
                        model.objective += ((reaction.flux_expression -
                                            scen_val[0])**2)/weight
                    except ValueError:  # solver does not support QP
                        raise QPnotSupportedException
                else:
                    pos_slack = model.problem.Variable(
                        reaction_id+"_make_feasible_linear_pos_slack", lb=0, ub=None)
                    neg_slack = model.problem.Variable(
                        reaction_id+"_make_feasible_linear_neg_slack", lb=0, ub=None)
                    elastic_constr = model.problem.Constraint(
                        Zero, lb=scen_val[0], ub=scen_val[0])
                    model.add_cons_vars([pos_slack, neg_slack, elastic_constr])
                    elastic_constr.set_linear_coefficients({reaction.forward_variable: 1.0, reaction.reverse_variable: -1.0,
                                                            pos_slack: 1.0, neg_slack: -1.0})
                    # for each pair one slack will always be zero
                    model.objective.set_linear_coefficients(
                        {pos_slack: 1.0/weight, neg_slack: 1.0/weight})
            else:
                reaction.lower_bound = scen_val[0]
                reaction.upper_bound = scen_val[1]
        solution = model.optimize()

        return solution, reactions_in_objective
