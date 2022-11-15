"""UI independent computations"""

import itertools
from typing import Dict, Tuple, List
import gurobipy
import numpy
import cobra
from cobra.util.array import create_stoichiometric_matrix
from cobra.core.formula import Formula
from optlang.symbolics import Zero, Add
from qtpy.QtWidgets import QMessageBox

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
                              flux_weight_scale: float = 1.0, abs_flux_weights: bool = False, weights_key: str = None,
                              bm_reac_id: str = "", variable_constituents: List[cobra.Metabolite] = None,
                              max_coeff_change: float = 0.9, min_rel_changes: bool = True,
                              gam_mets_param: Tuple[List[cobra.Metabolite], float, float, float] = ([], 0.0, 0.0, 0.0)):
    # if flux_weight_scale == 0 only biomass equation is adjusted
    # if bm_reac_id == "" only fluxes will be adjusted
    reactions_in_objective = []
    bm_mod = dict() # for use with Reaction.add_metabolites
    gam_mets_sign = []
    gam_adjust = 0
    if use_QP:
        qp_terms = [] # list of terms for the quadratic objective
    with cobra_model as model:
        model.objective = model.problem.Objective(Zero, direction='min')
        if flux_weight_scale > 0:
            for reaction_id, scen_val in scen_values.items():
                if reaction_id == bm_reac_id:
                    continue # growth rate will be fixed below if biomass adjustment is used
                try:
                    reaction: cobra.Reaction = model.reactions.get_by_id(reaction_id)
                except KeyError:
                    print('reaction', reaction_id, 'not found!')
                    continue
                # reactions set to 0 are still considered off
                if scen_val[0] == scen_val[1] and scen_val[0] != 0:
                    reactions_in_objective.append(reaction_id)
                    if abs_flux_weights:
                        weight = abs(scen_val[0]) * flux_weight_scale # for scaling relative to biomass adjustment
                    else:
                        if isinstance(weights_key, str):
                            try:
                                weight = float(reaction.annotation.get(
                                    weights_key, flux_weight_scale))
                            except ValueError:
                                weight = 0
                            if weight <= 0:
                                print("The value of annotation key '"+weights_key+"' of reaction'" +
                                    reaction_id+"' is not a positive number, using default weight.")
                                weight = flux_weight_scale
                        else:
                            weight = flux_weight_scale

                    if use_QP:
                        qp_terms.append(((reaction.flux_expression - scen_val[0])**2)/weight)
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
                        model.objective.set_linear_coefficients({pos_slack: 1.0/weight, neg_slack: 1.0/weight})
                else:
                    reaction.lower_bound = scen_val[0]
                    reaction.upper_bound = scen_val[1]

        if len(bm_reac_id) > 0:
            mue_fixed = scen_values[bm_reac_id][0]
            bm_reaction: cobra.Reaction = cobra_model.reactions.get_by_id(bm_reac_id)
            gam_mets, gam_max_change, gam_weight, gam_base = gam_mets_param
            if variable_constituents is None:
                bm_coeff_var = [(met, Formula(met.formula), coeff) for met,coeff in bm_reaction.metabolites.items()]
                bm_coeff_var = [[m,f.weight,c,None] for m,f,c in bm_coeff_var if c < 0 and f.weight > 0 and f.elements.get('C', 0) > 0 and f.elements.get('P', 0) == 0]
            else:
                bm_coeff_var = [[met, Formula(met.formula).weight, bm_reaction.metabolites[met], None] for met in variable_constituents]
            if flux_weight_scale == 0: # otherwise they have already been integrated above
                for reac_id in scen_values:
                    try:
                        reaction = model.reactions.get_by_id(reac_id)
                    except KeyError:
                        print('reaction', reac_id, 'not found!')
                    else:
                        reaction.bounds = scen_values[reac_id]
            bm_reaction.lower_bound = mue_fixed
            bm_reaction.upper_bound = mue_fixed
            mass_const = model.problem.Constraint(0, lb=0, ub=0)
            model.add_cons_vars([mass_const])

            for i in range(len(bm_coeff_var)):
                met, mol_weigt, coeff, _ = bm_coeff_var[i]
                if met in gam_mets and gam_base > 0:
                    coeff = coeff - numpy.sign(coeff)*gam_base
                    bm_coeff_var[i][2] = coeff
                    print(bm_coeff_var[i])
                if use_QP:
                    slack = model.problem.Variable(met.id+"_slack", lb=-abs(coeff)*max_coeff_change, ub=abs(coeff)*max_coeff_change)
                    bm_coeff_var[i][3] = slack
                    model.add_cons_vars([slack])
                    met.constraint.set_linear_coefficients({slack: mue_fixed})
                    mass_const.set_linear_coefficients({slack: mol_weigt})
                else:
                    pos_slack = model.problem.Variable(met.id+"_pos_slack", lb=0, ub=abs(coeff)*max_coeff_change)
                    neg_slack = model.problem.Variable(met.id+"_neg_slack", lb=0, ub=abs(coeff)*max_coeff_change)
                    slacks = (pos_slack, neg_slack)
                    bm_coeff_var[i][3] = slacks
                    model.add_cons_vars(slacks)
                    met.constraint.set_linear_coefficients({pos_slack: mue_fixed, neg_slack: -mue_fixed})
                    mass_const.set_linear_coefficients({pos_slack: mol_weigt, neg_slack: -mol_weigt})

            if len(gam_mets) > 0:
                gam_mets_sign = [0] * len(gam_mets)
                if use_QP:
                    gam_slack = model.problem.Variable("gam_slack", lb=-1.0, ub=1.0)
                    model.add_cons_vars([gam_slack])
                    for i in range(len(gam_mets)):
                        met = gam_mets[i]
                        sign = numpy.sign(bm_reaction.metabolites[met])
                        met.constraint.set_linear_coefficients({gam_slack: sign*gam_max_change*mue_fixed})
                        gam_mets_sign[i] = sign
                    qp_terms.append(gam_weight * (gam_slack**2))
                else:
                    gam_slack_pos = model.problem.Variable("gam_slack_pos", lb=0.0, ub=1.0)
                    gam_slack_neg = model.problem.Variable("gam_slack_neg", lb=0.0, ub=1.0)
                    model.add_cons_vars([gam_slack_pos, gam_slack_neg])
                    for i in range(len(gam_mets)):
                        met = gam_mets[i]
                        sign = numpy.sign(bm_reaction.metabolites[met])
                        met.constraint.set_linear_coefficients({gam_slack_pos: sign*gam_max_change*mue_fixed,
                                                                gam_slack_neg: -sign*gam_max_change*mue_fixed})
                        gam_mets_sign[i] = sign
                    model.objective.set_linear_coefficients({gam_slack_pos: gam_weight, gam_slack_neg: gam_weight})

            if use_QP:
                if min_rel_changes:
                    qp_terms += [(s/abs(c))**2 for _,_,c,s in bm_coeff_var]
                else:
                    qp_terms += [s**2 for _,_,_,s in bm_coeff_var]
            else:
                if min_rel_changes:
                    model.objective.set_linear_coefficients({s: abs(1/c) for (s,c) in itertools.chain(*(((s_p,c),(s_n,c)) for _,_,c,(s_p,s_n) in bm_coeff_var))})
                else:
                    model.objective.set_linear_coefficients({s: 1 for s in itertools.chain(*((s_p,s_n) for _,_,_,(s_p,s_n) in bm_coeff_var))})

        if use_QP:
            try:
                model.objective = model.problem.Objective(Add(*qp_terms), direction='min')
            except ValueError: # solver does not support QP
                raise QPnotSupportedException
        solution = model.optimize()
        print(solution)

        if len(bm_reac_id) > 0:
            format_string = "{:.2g} {:.2g}"
            if use_QP:
                for m,_,coeff,s in bm_coeff_var:
                    v = model.solver.variables[s.name].primal
                    if v != 0:
                        print(s.name, format_string.format(v, v/abs(coeff)))
                        bm_mod[m] = v
                if gam_mets_param is not None:
                    for met, sign in zip(gam_mets, gam_mets_sign):
                        gam_adjust = gam_max_change * model.solver.variables["gam_slack"].primal
            else:
                for m,_,coeff,(s_p,s_n) in bm_coeff_var:
                    v = model.solver.variables[s_p.name].primal
                    if v != 0:
                        print(s_p.name, format_string.format(v, v/abs(coeff)))
                        bm_mod[m] = v
                    v = model.solver.variables[s_n.name].primal
                    if v != 0:
                        print(s_n.name, format_string.format(v, v/abs(coeff)))
                        bm_mod[m] = -v
                if gam_mets_param is not None:
                    for met, sign in zip(gam_mets, gam_mets_sign):
                        gam_adjust = gam_max_change * \
                            (model.solver.variables["gam_slack_pos"].primal - model.solver.variables["gam_slack_neg"].primal)
            if gam_mets_param is not None:
                if use_QP:
                    print("gam_slack", model.solver.variables["gam_slack"].primal)
                else:
                    print("gam_slack_pos", model.solver.variables["gam_slack_pos"].primal)
                    print("gam_slack_neg", model.solver.variables["gam_slack_neg"].primal)

        return solution, reactions_in_objective, bm_mod, gam_mets_sign, gam_adjust

def element_exchange_balance(model: cobra.Model, scen_values: Dict[str, Tuple[float, float]], non_boundary_reactions: List[str],
                             organic_elements_only=False):
    reaction_fluxes: List[Tuple(cobra.Reaction, float)] = []
    for reac_id in non_boundary_reactions:
        if reac_id in scen_values:
            reaction_fluxes.append((model.reactions.get_by_id(reac_id), scen_values[reac_id][0]))
        else:
            print("Reaction", reac_id, "is not in the current scenario.")
    for reac_id, (flux, ub) in scen_values.items():
        if flux != ub:
            print("Reaction", reac_id, "does not have a fixed flux value, using its lower bound for the calculation.")
        rxn = model.reactions.get_by_id(reac_id)
        if rxn.boundary:
            reaction_fluxes.append((rxn, flux))

    influx = dict()
    efflux = dict()
    organic_elements = ['C', 'O', 'H', 'N', 'P', 'S']
    for rxn, flux in reaction_fluxes:
        for met, coeff in rxn.metabolites.items():
            val = coeff * flux
            if val > 0:
                flux_dict = influx
            elif val < 0:
                flux_dict = efflux
            else:
                continue
            for el, count in met.elements.items():
                if not organic_elements_only or el in organic_elements:
                    flux_dict[el] = flux_dict.get(el, 0) + count * val

    elements = set(influx.keys()).union(efflux.keys())
    def print_in_out_balance():
        in_ = influx.get(el, 0)
        out = efflux.get(el, 0)
        print("{:2s}:{:.2f},\t{:.2f},\t{:.5g}".format(el, in_, out, in_ + out))
    for el in organic_elements:
        if el in elements:
            print_in_out_balance()
            elements.remove(el)
    for el in elements:
        print_in_out_balance()

# TODO: should not be in the core module
def model_optimization_with_exceptions(model: cobra.Model):
    try:
        return model.optimize()
    except gurobipy.GurobiError as error:
        msgBox = QMessageBox()
        msgBox.setWindowTitle("Gurobi Error!")
        msgBox.setText("Calculation failed due to the following Gurobi solver error " +\
                       "(if this error cannot be resolved,\ntry using a different solver by changing " +\
                       "it under 'Config->Configure cobrapy'):\n"+error.message+\
                       "\nNOTE: Another error message will follow, you can safely ignore it.")
        msgBox.setIcon(QMessageBox.Warning)
        msgBox.exec()
