"""UI independent computations"""

import itertools
from collections import defaultdict
from typing import Dict, Tuple, List
from collections import Counter
import numpy
import cobra
from cobra.util.array import create_stoichiometric_matrix
from cobra.core.dictlist import DictList
from optlang.symbolics import Zero, Add

import efmtool_link.efmtool4cobra as efmtool4cobra
import efmtool_link.efmtool_extern as efmtool_extern
from cnapy.flux_vector_container import FluxVectorMemmap, FluxVectorContainer
from cnapy.appdata import Scenario

organic_elements = ['C', 'O', 'H', 'N', 'P', 'S']


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
                              max_coeff_change: float = 0.9, min_rel_changes: bool = True, bm_change_in_gram: bool = False,
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
                                weight = float(reaction.annotation.get(weights_key, flux_weight_scale))
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
                        pos_slack = model.problem.Variable(reaction_id+"_make_feasible_linear_pos_slack", lb=0, ub=None)
                        neg_slack = model.problem.Variable(reaction_id+"_make_feasible_linear_neg_slack", lb=0, ub=None)
                        elastic_constr = model.problem.Constraint(Zero, lb=scen_val[0], ub=scen_val[0])
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
                bm_coeff_var = [(met, met.elements, coeff) for met,coeff in bm_reaction.metabolites.items()]
                bm_coeff_var = [[m, m.formula_weight, c,None] for m,f,c in bm_coeff_var if c < 0 and m.formula_weight > 0 and f.get('C', 0) > 0 and f.get('P', 0) == 0]
            else:
                bm_coeff_var = [[met, met.formula_weight, bm_reaction.metabolites[met], None] for met in variable_constituents]
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

            i = 0
            while i < len(bm_coeff_var):
                met, mol_weigt, coeff, _ = bm_coeff_var[i]
                if met in gam_mets and gam_base > 0:
                    coeff = coeff - numpy.sign(coeff)*gam_base
                    if coeff == 0: # can e.g. occur when ATP is only used for GAM
                        del bm_coeff_var[i]
                        continue
                    bm_coeff_var[i][2] = coeff
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
                i += 1

            if len(gam_mets) > 0:
                gam_mets_sign = [0] * len(gam_mets)
                if use_QP:
                    gam_slack = model.problem.Variable("gam_slack", lb=-1.0, ub=1.0)
                    model.add_cons_vars([gam_slack])
                    for i in range(len(gam_mets)):
                        met = gam_mets[i]
                        sign = numpy.sign(bm_reaction.metabolites[met]) # !! FIXME: only correct when gam_base is larger than biomass part !! 
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
                    qp_terms += [(s/abs(c)*(w if bm_change_in_gram else 1))**2 for _,w,c,s in bm_coeff_var]
                else:
                    qp_terms += [(s*(w if bm_change_in_gram else 1))**2 for _,w,_,s in bm_coeff_var]
            else:
                if min_rel_changes:
                    if bm_change_in_gram: # change in [g] relative
                        model.objective.set_linear_coefficients({s: abs(1/c)*w for (s,c,w) in
                            itertools.chain(*(((s_p,c,w),(s_n,c,w)) for _,w,c,(s_p,s_n) in bm_coeff_var))})
                    else: # change in [mmol] relative
                        model.objective.set_linear_coefficients({s: abs(1/c) for (s,c) in itertools.chain(*(((s_p,c),(s_n,c)) for _,_,c,(s_p,s_n) in bm_coeff_var))})
                else:
                    if bm_change_in_gram: # change in [g] absolute
                        model.objective.set_linear_coefficients({s: c*w for (s,c,w) in
                            itertools.chain(*(((s_p,c,w),(s_n,c,w)) for _,w,c,(s_p,s_n) in bm_coeff_var))})
                    else: # change in [mmol] absolute
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
                if len(gam_mets) > 0:
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
                if len(gam_mets) > 0:
                    gam_adjust = gam_max_change * \
                        (model.solver.variables["gam_slack_pos"].primal - model.solver.variables["gam_slack_neg"].primal)
            if len(gam_mets) > 0:
                if use_QP:
                    print("gam_slack {:.3g}".format(model.solver.variables["gam_slack"].primal))
                else:
                    print("gam_slack_pos", model.solver.variables["gam_slack_pos"].primal)
                    print("gam_slack_neg", model.solver.variables["gam_slack_neg"].primal)

        return solution, reactions_in_objective, bm_mod, gam_mets_sign, gam_adjust

def element_exchange_balance(model: cobra.Model, scen_values: Scenario, non_boundary_reactions: List[str],
                             organic_elements_only=False, print_func=print):
    influx = defaultdict(int)
    efflux = defaultdict(int)
    with model as model:
        scen_values.add_scenario_reactions_to_model(model)
        reaction_fluxes: List[Tuple(cobra.Reaction, float)] = []
        for reac_id in non_boundary_reactions:
            reaction: cobra.Reaction = model.reactions.get_by_id(reac_id)
            val = scen_values.get(reac_id, None)
            if val is None:
                val = reaction.bounds
            if val[0] == val[1]:
                reaction_fluxes.append((reaction, val[0]))
            else:
                print_func("Non-boundary reaction", reac_id, "does not have a fixed flux value and will be ignored.")

        for reac_id, (flux, ub) in scen_values.items():
            if flux != ub:
                print_func("Reaction", reac_id, "does not have a fixed flux value, using its lower bound for the calculation.")
            rxn = model.reactions.get_by_id(reac_id)
            if rxn.boundary:
                reaction_fluxes.append((rxn, flux))

        metabolites_without_formulas = set()
        for rxn, flux in reaction_fluxes:
            for met, coeff in rxn.metabolites.items():
                val = coeff * flux
                if val > 0:
                    flux_dict = influx
                elif val < 0:
                    flux_dict = efflux
                else:
                    continue
                if len(met.elements) == 0:
                    metabolites_without_formulas.add(met.id)
                for el, count in met.elements.items():
                    if not organic_elements_only or el in organic_elements:
                        flux_dict[el] += count * val

        elements = set(influx.keys()).union(efflux.keys())
        print_func("Element   Influx    Outflux    Balance")
        def print_in_out_balance():
            in_ = influx.get(el, 0)
            out = efflux.get(el, 0)
            print_func(" {:3s}  {:10.2f} {:10.2f} {:10.4g}".format(el, in_, out, in_ + out))
        for el in organic_elements:
            if el in elements:
                print_in_out_balance()
                elements.remove(el)
        for el in elements:
            print_in_out_balance()
        if len(metabolites_without_formulas) > 0:
            print_func("WARNING: Metabolites wihtout formulas encountered:")
            print_func(", ".join(met for met in metabolites_without_formulas))
            print_func("The results are likely to be incorrect!")
    return influx, efflux

def check_biomass_weight(model: cobra.Model, bm_reac_id: str) -> float:
    """
    This function assumes that the biomass coefficients are in mmol/gDW.
    It only returns a correct value if the molecular weights of all biomass constituents are given.
    """
    bm_coeff = [(m, c) for m,c in model.reactions.get_by_id(bm_reac_id).metabolites.items()]
    bm_weight = 0.0
    for m,c in bm_coeff:
        w = m.formula_weight
        if w is None or w == 0:
            print("Molecular weight of biomass component", m.id, "cannot be calculated from its formula", m.formula)
        else:
            bm_weight += w/1000*-c
#    bm_weight = sum(m.formula_weight/1000*-c for m,c in bm_coeff)
    print("Flux of 1 through the biomass reaction produces", bm_weight, "g biomass.")
    return bm_weight

def replace_ids(dict_list: DictList, annotation_key: str, unambiguous_only: bool = False,
                unique_only: bool = True, candidates_separator: str ="") -> None:
    # can be used to replace IDs of reactions or metabolites with ones that are taken from the anotation
    # use model.compartments.keys() as compartment_ids if the metabolites have compartment suffixes
    # does not rename exchange reactions
    all_candidates = [None] * len(dict_list)
    if unique_only:
        candidates_count: Counter = Counter()
    for i, entry in enumerate(dict_list):
        candidates = entry.annotation.get(annotation_key, [])
        if not isinstance(candidates, list):
            if len(candidates_separator) > 0:
                candidates = candidates.split(candidates_separator)
            else:
                candidates = [candidates]
        if len(candidates) > 0 and hasattr(entry, 'compartment'):
            candidates = [c+"_"+entry.compartment for c in candidates]
        if unique_only:
            candidates_count.update(candidates)
        all_candidates[i] = candidates

    for entry, candidates in zip(dict_list, all_candidates):
        if unique_only:
            candidates = [c for c in candidates if candidates_count[c] == 1]
        if unambiguous_only and len(candidates) > 1:
            continue
        old_id = entry.id
        for new_id in candidates:
            if new_id == old_id:
                print(old_id, "remains unchanged")
                break
            try:
                entry.id = new_id
                entry.annotation['original ID'] = old_id
                break
            except ValueError: # new_id already in use
                pass
        if len(candidates) > 0 and new_id != old_id and old_id == entry.id:
            print("Could not find a new ID for", entry.id, "in", candidates)
