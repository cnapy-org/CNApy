"""UI independent computations"""

import os
import itertools
from collections import defaultdict, namedtuple
from typing import Dict, Tuple, List
from collections import Counter
import threading as th
import numpy
import pandas
import scipy.sparse as sp
import cobra
from cobra.util.array import create_stoichiometric_matrix
from cobra.core.dictlist import DictList
from cobra.core.solution import Solution
from optlang.symbolics import Add
from optlang import cplex_interface, gurobi_interface # , scip_interface
from cobra.exceptions import OptimizationError
import highspy
import osqp

import efmtool_link.efmtool4cobra as efmtool4cobra
import efmtool_link.efmtool_extern as efmtool_extern
from cnapy.flux_vector_container import FluxVectorMemmap, FluxVectorContainer
from cnapy.appdata import Scenario
# from cnapy.conservation_relations import find_redundant_metabolites_qr
import cnapy.optlang_highs_interface

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

SolverFailure = namedtuple('SolverFailure', ('status',))
# Result container for the standalone QP model (built without cobrapy's
# forward/reverse variable splitting); mirrors the small subset of
# cobra.Solution's interface (.status, .fluxes) that downstream code needs.
QPSolution = namedtuple('QPSolution', ('status', 'objective_value', 'fluxes'))

def make_scenario_feasible(cobra_model: cobra.Model, scen_values: Dict[str, Tuple[float, float]], use_QP: bool = False,
                              flux_weight_scale: float = 1.0, abs_flux_weights: bool = False, weights_key: str = None,
                              bm_reac_id: str = "", variable_constituents: List[cobra.Metabolite] = None,
                              max_coeff_change: float = 0.9, min_rel_changes: bool = True, bm_change_in_gram: bool = False,
                              gam_mets_param: Tuple[List[cobra.Metabolite], float, float, float] = ([], 0.0, 0.0, 0.0)):
    # For now, unless CPLEX or Gurobi are set as current solvers, OSQP will be used
    # for QPs because it performs mich better than HiGHS or SCIP.
    # There is some commented-out code that may be reactivated in case HiGHS or SCIP improve.
    if use_QP and cobra_model.problem not in (cplex_interface, gurobi_interface):
        osqp_settings={
            'max_iter': 100000,
            'eps_abs': cobra_model.tolerance,    # default is 1e-8
            'eps_rel': cobra_model.tolerance,    # default is 1e-8
        }
        return make_scenario_feasible_osqp(cobra_model, scen_values,
                                flux_weight_scale=flux_weight_scale, abs_flux_weights=abs_flux_weights,
                                weights_key=weights_key,
                                bm_reac_id=bm_reac_id, variable_constituents=variable_constituents,
                                max_coeff_change=max_coeff_change, min_rel_changes=min_rel_changes, 
                                bm_change_in_gram=bm_change_in_gram,
                                gam_mets_param=gam_mets_param, osqp_settings=osqp_settings)

    # if flux_weight_scale == 0 only biomass equation is adjusted
    # if bm_reac_id == "" only fluxes will be adjusted
    reactions_in_objective = []
    bm_mod = dict() # for use with Reaction.add_metabolites
    gam_mets_sign = []
    gam_adjust = 0
    with cobra_model as model:
        model.objective = model.problem.Objective(0, direction='min')
        scen_values.add_scenario_reactions_to_model(model)
        if use_QP:
            interface = model.problem  # optlang solver interface (shared between cobra_model and the standalone QP model)
            flux_vars = None      # populated below, only when use_QP
            met_constraints = None
            qp_terms = [] # list of terms for the quadratic objective
            qp_flux_targets = {}  # reaction_id -> (target_value, weight); QP terms built once flux_vars exist below
            # selection = find_redundant_metabolites_qr(create_stoichiometric_matrix(cobra_model))
            # redundant_met = model.metabolites.get_by_any(selection['remove_idx'].tolist())
            # redundant_met_ids = {m.id for m in redundant_met}
            # # Note: we deliberately do NOT call model.remove_metabolites() here.
            # # cobra_model is never mutated for the QP case -- the standalone
            # # qp_model built below just excludes these metabolites' rows when
            # # constructing its own mass-balance constraints. This also avoids
            # # a context-manager rollback bug: remove_metabolites() inside a
            # # `with cobra_model as model:` block gets replayed (re-added) at
            # # __exit__, which was tripping a stale-row-count bug in the HiGHS
            # # interface's constraint re-insertion path.
            # print("Excluding redundant (conserved-moiety) metabolites from the QP mass balance:")
            # print(redundant_met)
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
                    if scen_val[0] < reaction.lower_bound:
                        reaction.lower_bound = cobra.Configuration().lower_bound
                    if scen_val[0] > reaction.upper_bound:
                        reaction.upper_bound = cobra.Configuration().upper_bound
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
                        # Variable splitting is avoided entirely: no net_var/
                        # net_constr indirection is needed here anymore. We
                        # just remember the target/weight; the actual QP term
                        # is built directly on the single, unsplit flux
                        # variable once the standalone QP model exists below.
                        qp_flux_targets[reaction_id] = (scen_val[0], weight)
                    else:
                        pos_slack = model.problem.Variable(reaction_id+"_make_feasible_linear_pos_slack", lb=0, ub=None)
                        neg_slack = model.problem.Variable(reaction_id+"_make_feasible_linear_neg_slack", lb=0, ub=None)
                        elastic_constr = model.problem.Constraint(0, lb=scen_val[0], ub=scen_val[0])
                        model.add_cons_vars([pos_slack, neg_slack, elastic_constr])
                        elastic_constr.set_linear_coefficients({reaction.forward_variable: 1.0, reaction.reverse_variable: -1.0,
                                                                pos_slack: 1.0, neg_slack: -1.0})
                        # for each pair one slack will always be zero
                        model.objective.set_linear_coefficients({pos_slack: 1.0/weight, neg_slack: 1.0/weight})
                else:
                    reaction.lower_bound = scen_val[0]
                    reaction.upper_bound = scen_val[1]

        if use_QP:
            # Build a dedicated, standalone optlang Model with exactly one
            # (unsplit) flux variable per reaction, using the same solver
            # interface as cobra_model. This is where variable splitting is
            # avoided completely: cobra_model's own forward_variable /
            # reverse_variable machinery is never touched for the QP.
            # This is not strictly necessary for CPLEX/Gurobi, but lowers that numbers
            # of variables so that the community models can be used for more models.
            qp_model = interface.Model(name="scenario_feasibility_QP")

            flux_vars = {r.id: interface.Variable(r.id, lb=r.lower_bound, ub=r.upper_bound) for r in model.reactions}
            qp_model.add(list(flux_vars.values()))
            qp_model.update()

            # Mass balance constraints, one per metabolite EXCLUDING the
            # redundant (conserved-moiety) rows identified above -- those
            # rows are skipped here rather than removed from cobra_model.
            met_terms = defaultdict(list)
            for r in model.reactions:
                v = flux_vars[r.id]
                for met, coeff in r.metabolites.items():
                    # if met.id in redundant_met_ids:
                    #     continue
                    met_terms[met.id].append(coeff * v)

            met_constraints = {}
            for met_id, terms in met_terms.items():
                expr = terms[0] if len(terms) == 1 else Add(*terms)
                met_constraints[met_id] = interface.Constraint(expr, lb=0, ub=0, name=met_id, sloppy=True)
            qp_model.add(list(met_constraints.values()), sloppy=True)
            qp_model.update()  # commit constraints before any later set_linear_coefficients calls on them

            qp_terms += [((flux_vars[rid] - target) ** 2) / weight
                         for rid, (target, weight) in qp_flux_targets.items()]

        if len(bm_reac_id) > 0:
            mue_fixed = scen_values[bm_reac_id][0]
            bm_reaction: cobra.Reaction = cobra_model.reactions.get_by_id(bm_reac_id)
            gam_mets, gam_max_change, gam_weight, gam_base = gam_mets_param
            if variable_constituents is None:
                bm_coeff_var = [(met, met.elements, coeff) for met,coeff in bm_reaction.metabolites.items()]
                bm_coeff_var = [[m, m.formula_weight, c,None] for m,f,c in bm_coeff_var if c < 0 and m.formula_weight > 0 and f.get('C', 0) > 0 and f.get('P', 0) == 0]
            else:
                bm_coeff_var = [[met, met.formula_weight, bm_reaction.metabolites[met], None] for met in variable_constituents]
            # if use_QP:
            #     # A biomass constituent that happens to be one of the redundant
            #     # (conserved-moiety) rows has no entry in met_constraints (its
            #     # balance is only implicitly represented via the rest of its
            #     # conserved pool) -- skip it here rather than KeyError below.
            #     excluded = [m for m, *_ in bm_coeff_var if m.id in redundant_met_ids]
            #     if excluded:
            #         print("Skipping QP slack for biomass constituent(s) that are part of a "
            #               "removed conservation relation:", [m.id for m in excluded])
            #     bm_coeff_var = [entry for entry in bm_coeff_var if entry[0].id not in redundant_met_ids]
            if flux_weight_scale == 0: # otherwise they have already been integrated above
                for reac_id in scen_values:
                    try:
                        reaction = model.reactions.get_by_id(reac_id)
                    except KeyError:
                        print('reaction', reac_id, 'not found!')
                    else:
                        reaction.bounds = scen_values[reac_id]
                        if use_QP:
                            # keep the standalone QP's flux variable bounds in sync;
                            # set_bounds() avoids a transient lb>ub error that separate
                            # .lb=/.ub= assignments could hit depending on prior bounds
                            flux_vars[reaction.id].set_bounds(*reaction.bounds)
            bm_reaction.lower_bound = mue_fixed
            bm_reaction.upper_bound = mue_fixed
            if use_QP:
                flux_vars[bm_reaction.id].set_bounds(mue_fixed, mue_fixed)
                mass_const = interface.Constraint(0, lb=0, ub=0)
                qp_model.add([mass_const])
                qp_model.update()
            else:
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
                    slack = interface.Variable(met.id+"_slack", lb=-abs(coeff)*max_coeff_change, ub=abs(coeff)*max_coeff_change)
                    bm_coeff_var[i][3] = slack
                    qp_model.add([slack])
                    qp_model.update()  # slack must be committed before referencing it below
                    met_constraints[met.id].set_linear_coefficients({slack: mue_fixed})
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
                    scale = gam_max_change * mue_fixed
                    gam_slack = interface.Variable("gam_slack", lb=-scale, ub=scale)
                    qp_model.add([gam_slack])
                    qp_model.update()  # commit gam_slack before wiring it into met_constraints below
                    for i in range(len(gam_mets)):
                        met = gam_mets[i]
                        # if met.id in redundant_met_ids:
                        #     print("Skipping GAM slack wiring for", met.id,
                        #           "-- part of a removed conservation relation.")
                        #     continue
                        sign = numpy.sign(bm_reaction.metabolites[met]) # !! FIXME: only correct when gam_base is larger than biomass part !! 
                        met_constraints[met.id].set_linear_coefficients({gam_slack: sign})
                        gam_mets_sign[i] = sign
                    qp_terms.append((gam_weight  / scale**2) * (gam_slack**2))
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
                qp_model.objective = interface.Objective(Add(*qp_terms), direction='min')
                print(qp_model.objective)
            except ValueError: # solver does not support QP
                raise QPnotSupportedException
            try:
                # if interface == cnapy.optlang_highs_interface:
                #     qp_model.problem.setOptionValue("solver", model.solver.problem.getOptionValue("solver")[1])
                #     qp_model.problem.setOptionValue("kkt_tolerance", model.tolerance)
                #     qp_model.problem.setOptionValue("output_flag", True)
                # elif interface == scip_interface:
                #     qp_model.configuration.verbosity = 3
                status = qp_model.optimize()
            except Exception as exc:  # standalone optlang Model.optimize() generally returns a
                status = 'error'      # status string rather than raising; guard against solver-level errors anyway
                print("QP solver raised an exception:", exc)
            if status == 'optimal':
                fluxes = pandas.Series({r.id: flux_vars[r.id].primal for r in model.reactions})
                solution = QPSolution(status=status, objective_value=qp_model.objective.value, fluxes=fluxes)
                print(solution)
            else:
                solution = SolverFailure(status=status)
                print("Optimization failed, no solution could be found.")
                print("Try relaxing model tolerance or choose a different solver.")
        else:
            try:
                solution = model.optimize()
                print(solution)
            except OptimizationError:
                solution = SolverFailure(status=model.solver.status)
                print("Optimization failed, no solution could be found.")
                print("Try relaxing model tolerance or choose a different solver.")

        if solution.status == "optimal":
            if len(bm_reac_id) > 0:
                format_string = "{:.2g} {:.2g}"
                if use_QP:
                    for m,_,coeff,s in bm_coeff_var:
                        v = s.primal
                        if v != 0:
                            print(s.name, format_string.format(v, v/abs(coeff)))
                            bm_mod[m] = v
                    if len(gam_mets) > 0:
                        # gam_slack already represents the physical adjustment directly
                        # (its bounds/coefficients were rescaled to +/-gam_max_change*mue_fixed
                        # with unit constraint coefficients), so recovering the original
                        # [-gam_max_change, gam_max_change]-scaled quantity means dividing
                        # back out mue_fixed rather than re-multiplying by gam_max_change.
                        gam_adjust = gam_slack.primal / mue_fixed
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
                        print("gam_slack {:.3g}".format(gam_slack.primal))
                    else:
                        print("gam_slack_pos", model.solver.variables["gam_slack_pos"].primal)
                        print("gam_slack_neg", model.solver.variables["gam_slack_neg"].primal)

    return solution, reactions_in_objective, bm_mod, gam_mets_sign, gam_adjust


def make_scenario_feasible_osqp(cobra_model: cobra.Model, scen_values: Scenario,
                                flux_weight_scale: float = 1.0, abs_flux_weights: bool = False, weights_key: str = None,
                                bm_reac_id: str = "", variable_constituents: List[cobra.Metabolite] = None,
                                max_coeff_change: float = 0.9, min_rel_changes: bool = True, bm_change_in_gram: bool = False,
                                gam_mets_param: Tuple[List[cobra.Metabolite], float, float, float] = ([], 0.0, 0.0, 0.0),
                                osqp_settings: dict = None):
    """QP variant of make_scenario_feasible that builds and solves the problem directly with the osqp
    Python package, bypassing optlang/cobra.util.solver entirely (i.e. this replaces the use_QP=True
    branch of make_scenario_feasible; there is no use_QP parameter here since this function is always QP).

    Deliberate differences from the optlang-based use_QP=True path, all a consequence of not building the
    problem through cobra's optlang Model:

    - Each reaction is a single (possibly negative) variable with cobra's own bounds, not optlang's
      forward/reverse split. Consequently the "net_flux" helper variable used in make_scenario_feasible
      (introduced there only to avoid cross-terms between the forward and reverse variables) is not
      needed; the flux variable itself is used directly in the quadratic deviation terms.
    - Variable bounds are enforced as extra rows appended to the constraint matrix, since osqp has no
      native notion of variable bounds.
    - `solution` is a real cobra.core.Solution (status/objective_value/fluxes) on success, or the same
      SolverFailure(status=...) namedtuple used in make_scenario_feasible on failure/infeasibility, so
      callers can keep using `solution.status == "optimal"`.
    - `objective_value` includes the constant term(s) dropped when completing the square for osqp's
      0.5 x^T P x + q^T x form, so it is comparable to what make_scenario_feasible would report.

    This function assumes scen_values.add_scenario_reactions_to_model only performs cobra-level edits
    (e.g. via add_reactions/bounds) since it is invoked through the normal cobra_model context manager
    here, exactly as in make_scenario_feasible; no optlang objects are ever created or required.

    All other parameters have the same meaning as in make_scenario_feasible.

    osqp_settings: optional dict overriding the default osqp solver settings (verbose, polish, eps_abs,
    eps_rel, max_iter).
    """

    reactions_in_objective: List[str] = []
    bm_mod = dict()  # for use with Reaction.add_metabolites
    gam_mets_sign = []
    gam_adjust = 0

    # (reaction_id, target_value, weight) for the flux-fixation quadratic terms; resolved to column
    # indices once the final (post-scenario) reaction list is known.
    quad_terms = []

    with cobra_model as model:
        scen_values.add_scenario_reactions_to_model(model)

        if flux_weight_scale > 0:
            for reaction_id, scen_val in scen_values.items():
                if reaction_id == bm_reac_id:
                    continue  # growth rate will be fixed below if biomass adjustment is used
                try:
                    reaction: cobra.Reaction = model.reactions.get_by_id(reaction_id)
                except KeyError:
                    print('reaction', reaction_id, 'not found!')
                    continue
                # reactions set to 0 are still considered off
                if scen_val[0] == scen_val[1] and scen_val[0] != 0:
                    reactions_in_objective.append(reaction_id)
                    if scen_val[0] < reaction.lower_bound:
                        reaction.lower_bound = cobra.Configuration().lower_bound
                    if scen_val[0] > reaction.upper_bound:
                        reaction.upper_bound = cobra.Configuration().upper_bound
                    if abs_flux_weights:
                        weight = abs(scen_val[0]) * flux_weight_scale  # for scaling relative to biomass adjustment
                    else:
                        if isinstance(weights_key, str):
                            try:
                                weight = float(reaction.annotation.get(weights_key, flux_weight_scale))
                            except ValueError:
                                weight = 0
                            if weight <= 0:
                                print("The value of annotation key '" + weights_key + "' of reaction'" +
                                    reaction_id + "' is not a positive number, using default weight.")
                                weight = flux_weight_scale
                        else:
                            weight = flux_weight_scale
                    quad_terms.append((reaction_id, scen_val[0], weight))
                else:
                    reaction.lower_bound = scen_val[0]
                    reaction.upper_bound = scen_val[1]

        bm_coeff_var = []  # [metabolite, mol_weight, coeff], slack column index tracked separately below
        gam_mets: List[cobra.Metabolite] = []
        gam_max_change = gam_weight = gam_base = 0.0
        mue_fixed = None
        bm_reaction = None
        use_gam = False

        if len(bm_reac_id) > 0:
            mue_fixed = scen_values[bm_reac_id][0]
            bm_reaction = cobra_model.reactions.get_by_id(bm_reac_id)
            gam_mets, gam_max_change, gam_weight, gam_base = gam_mets_param
            if variable_constituents is None:
                bm_coeff_all = [(met, met.elements, coeff) for met, coeff in bm_reaction.metabolites.items()]
                bm_coeff_var = [[m, m.formula_weight, c] for m, f, c in bm_coeff_all
                                if c < 0 and m.formula_weight > 0 and f.get('C', 0) > 0 and f.get('P', 0) == 0]
            else:
                bm_coeff_var = [[met, met.formula_weight, bm_reaction.metabolites[met]] for met in variable_constituents]

            if flux_weight_scale == 0:  # otherwise they have already been integrated above
                for reac_id in scen_values:
                    try:
                        reaction = model.reactions.get_by_id(reac_id)
                    except KeyError:
                        print('reaction', reac_id, 'not found!')
                    else:
                        reaction.bounds = scen_values[reac_id]

            bm_reaction.lower_bound = mue_fixed
            bm_reaction.upper_bound = mue_fixed

            i = 0
            while i < len(bm_coeff_var):
                met, mol_weigt, coeff = bm_coeff_var[i]
                if met in gam_mets and gam_base > 0:
                    coeff = coeff - numpy.sign(coeff) * gam_base
                    if coeff == 0:  # can e.g. occur when ATP is only used for GAM
                        del bm_coeff_var[i]
                        continue
                    bm_coeff_var[i][2] = coeff
                i += 1

            use_gam = len(gam_mets) > 0

        # ---- final (post-scenario) cobra model structure ----
        n_rxns = len(model.reactions)
        n_mets = len(model.metabolites)
        rxn_index = {r.id: idx for idx, r in enumerate(model.reactions)}
        met_index = {m.id: idx for idx, m in enumerate(model.metabolites)}

        col_lower = numpy.array([r.lower_bound for r in model.reactions], dtype=numpy.double)
        col_upper = numpy.array([r.upper_bound for r in model.reactions], dtype=numpy.double)
        S = create_stoichiometric_matrix(model, array_type='lil')

        # ---- assign column indices for the extra (slack) variables ----
        extra_lb: List[float] = []
        extra_ub: List[float] = []
        gam_slack_idx = None
        if use_gam:
            gam_slack_idx = n_rxns + len(extra_lb)
            extra_lb.append(-1.0)
            extra_ub.append(1.0)

        bm_slack_idx = []  # parallel to bm_coeff_var
        for met, mol_weigt, coeff in bm_coeff_var:
            bm_slack_idx.append(n_rxns + len(extra_lb))
            extra_lb.append(-abs(coeff) * max_coeff_change)
            extra_ub.append(abs(coeff) * max_coeff_change)

        n_vars = n_rxns + len(extra_lb)
        col_lower = numpy.concatenate([col_lower, extra_lb])
        col_upper = numpy.concatenate([col_upper, extra_ub])

        # ---- diagonal quadratic objective: P (diagonal) and q ----
        P_diag = numpy.zeros(n_vars)
        q = numpy.zeros(n_vars)
        const_offset = 0.0  # only affects the reported objective_value, not the solution itself

        for reaction_id, target, weight in quad_terms:
            j = rxn_index[reaction_id]
            P_diag[j] += 2.0 / weight
            q[j] += -2.0 * target / weight
            const_offset += target ** 2 / weight

        if gam_slack_idx is not None:
            P_diag[gam_slack_idx] += 2.0 * gam_weight

        for (met, mol_weigt, coeff), s_idx in zip(bm_coeff_var, bm_slack_idx):
            scale = mol_weigt if bm_change_in_gram else 1.0
            a = (scale / abs(coeff)) ** 2 if min_rel_changes else scale ** 2
            P_diag[s_idx] += 2.0 * a

        # ---- constraint matrix: stoichiometry (+ slack contributions), mass balance, box bounds ----
        n_eq_extra = 1 if len(bm_reac_id) > 0 else 0  # the mass_const row
        A_eq = sp.lil_matrix((n_mets + n_eq_extra, n_vars))
        A_eq[:n_mets, :n_rxns] = S

        if gam_slack_idx is not None:
            for met in gam_mets:
                sign = numpy.sign(bm_reaction.metabolites[met])
                gam_mets_sign.append(sign)
                A_eq[met_index[met.id], gam_slack_idx] += sign * gam_max_change * mue_fixed

        mass_row = n_mets  # only used/meaningful when n_eq_extra == 1
        for (met, mol_weigt, coeff), s_idx in zip(bm_coeff_var, bm_slack_idx):
            A_eq[met_index[met.id], s_idx] += mue_fixed
            if n_eq_extra:
                A_eq[mass_row, s_idx] += mol_weigt

        l_eq = numpy.zeros(n_mets + n_eq_extra)
        u_eq = numpy.zeros(n_mets + n_eq_extra)

        A_box = sp.eye(n_vars, format='lil')
        A = sp.vstack([A_eq, A_box]).tocsc()
        l = numpy.concatenate([l_eq, col_lower])
        u = numpy.concatenate([u_eq, col_upper])

        P = sp.diags(P_diag, format='csc')

        settings = dict(verbose=False, polish=True, eps_abs=1e-8, eps_rel=1e-8, max_iter=20000)
        if osqp_settings:
            settings.update(osqp_settings)

        prob = osqp.OSQP()
        prob.setup(P=P, q=q, A=A, l=l, u=u, **settings)
        res = prob.solve()
        raw_status = res.info.status

        if raw_status in ("solved", "solved inaccurate"):
            status = "optimal"
        elif "infeasible" in raw_status:
            status = "infeasible"
        elif "unbounded" in raw_status:
            status = "unbounded"
        else:
            status = raw_status

        if status == "optimal":
            objective_value = res.info.obj_val + const_offset
            fluxes = pandas.Series(res.x[:n_rxns], index=[r.id for r in model.reactions])
            solution = Solution(objective_value, status, fluxes)
            print(solution)

            if len(bm_reac_id) > 0:
                format_string = "{:.2g} {:.2g}"
                for (met, mol_weigt, coeff), s_idx in zip(bm_coeff_var, bm_slack_idx):
                    v = res.x[s_idx]
                    if v != 0:
                        print(met.id, format_string.format(v, v / abs(coeff)))
                        bm_mod[met] = v
                if gam_slack_idx is not None:
                    gam_adjust = gam_max_change * res.x[gam_slack_idx]
                    print("gam_slack {:.3g}".format(res.x[gam_slack_idx]))
        else:
            solution = SolverFailure(status=status)
            print("Optimization failed, no solution could be found. (osqp status: {})".format(raw_status))

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

def build_highs_fba_model(cobra_model: cobra.Model, constraints=None) -> highspy.HighsLp:
    """Build a highspy.HighsLp instance directly from a cobrapy Model,
    bypassing optlang entirely. """

    if constraints is None:
        constraints = []
    n_rxns = len(cobra_model.reactions)
    n_mets = len(cobra_model.metabolites)
    n_constr = len(constraints)
    n_rows = n_mets + n_constr

    col_lower = numpy.empty(n_rxns, dtype=numpy.double)
    col_upper = numpy.empty(n_rxns, dtype=numpy.double)
    col_cost = numpy.zeros(n_rxns, dtype=numpy.double)

    for j in range(len(cobra_model.reactions)):
        rxn = cobra_model.reactions[j]
        col_lower[j], col_upper[j] = rxn.lower_bound, rxn.upper_bound
        col_cost[j] = rxn.objective_coefficient

    row_lower = numpy.zeros(n_rows, dtype=numpy.double)
    row_upper = numpy.zeros(n_rows, dtype=numpy.double)

    S = create_stoichiometric_matrix(cobra_model, array_type="lil")
    S.resize((n_rows, n_rxns))
    for i in range(n_constr):
        row_idx = n_mets + i
        expression, constraint_type, rhs = constraints[i]
        if constraint_type == '=':
            row_lower[row_idx] = rhs
            row_upper[row_idx] = rhs
        elif constraint_type == '<=':
            row_lower[row_idx] = -float('inf')
            row_upper[row_idx] = rhs
        elif constraint_type == '>=':
            row_lower[row_idx] = rhs
            row_upper[row_idx] = float('inf')
        else:
            print("Skipping constraint of unknown type", constraint_type)
            continue
        try:
            col_idx = list(map(cobra_model.reactions.index, expression.keys()))
        except KeyError:
            print("Skipping constraint containing a reaction that is not in the model:", expression)
            continue
        S[row_idx, col_idx] = list(expression.values())

    lp = highspy.HighsLp()
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.num_col_ = n_rxns
    lp.num_row_ = n_rows
    lp.col_cost_ = col_cost
    lp.col_lower_ = col_lower
    lp.col_upper_ = col_upper
    lp.row_lower_ = row_lower
    lp.row_upper_ = row_upper
    row_lengths = [len(row) for row in S.rows]
    indptr = numpy.zeros(len(row_lengths) + 1, dtype=numpy.int32)
    indptr[1:] = numpy.cumsum(row_lengths)
    lp.a_matrix_.start_ = indptr
    lp.a_matrix_.index_ = numpy.array([col for row in S.rows for col in row], dtype=numpy.int32)
    lp.a_matrix_.value_ = numpy.array([val for row in S.data for val in row], dtype=S.dtype)
    lp.sense_ = (
        highspy.ObjSense.kMaximize if cobra_model.objective_direction == "max"
        else highspy.ObjSense.kMinimize
    )
    
    return lp

class FVAHiGHSworker(th.Thread):
    def __init__(self, job_queue, job_queue_lock, lb, ub, lp_data, tolerance):
        super().__init__()
        self.job_queue = job_queue
        self.job_queue_lock = job_queue_lock
        self.lb = lb
        self.ub = ub
        self.lp_data = lp_data
        self.tolerance = tolerance
        self.n_bad = 0

    def run(self):
        h = highspy.Highs()
        h.passModel(self.lp_data)
        h.setOptionValue("solver", "simplex")
        h.setOptionValue("simplex_strategy", 4) # primal simplex, typically fastest for FBA-like problems
        h.setOptionValue("output_flag", False) # reduces execution time even though no output was visible before
        h.setOptionValue("kkt_tolerance", self.tolerance)
        h.changeObjectiveSense(highspy.ObjSense.kMinimize)
        # both min and max jobs use MINIMIZE
        while True:
            with self.job_queue_lock:
                if not self.job_queue:
                    break
                i, coef = self.job_queue.pop()

            h.changeColCost(i, coef)
            h.run()

            if h.getModelStatus() == highspy.HighsModelStatus.kOptimal:
                obj_val = h.getInfo().objective_function_value
            else:
                obj_val = float("NaN")
                self.n_bad += 1

            if coef == -1:
                self.ub[i] = -obj_val
            else:
                self.lb[i] = obj_val
            h.changeColCost(i, 0.0)

def multi_threaded_HiGHS_FVA(model: cobra.Model, constraints=None):
    pre_tol = 1e-9
    num_proc = os.cpu_count()
    if num_proc is None:
        num_proc = 2 # unlikely that there are any single-core users
    elif num_proc > 4:
        num_proc -= 1
        if num_proc > 8:
            num_proc -= 1 
    num_reac = len(model.reactions)
    lb = [float('NaN')] * num_reac
    ub = [float('NaN')] * num_reac
    job_queue = []

    lp_data = build_highs_fba_model(model, constraints)
    lp_data.col_cost_[:] = 1.0
    lp_data.sense_ = highspy.ObjSense.kMaximize
    h = highspy.Highs()
    h.passModel(lp_data)
    h.setOptionValue("solver", "simplex")
    h.setOptionValue("kkt_tolerance", pre_tol)
    h.setOptionValue("output_flag", False)
    h.run()
    status = h.getModelStatus()
    if status == highspy.HighsModelStatus.kInfeasible:
        raise cobra.exceptions.Infeasible("")
    elif status != highspy.HighsModelStatus.kOptimal:
        raise ValueError(f"Unexpected solver status {h.modelStatusToString(status)} during FVA")
    solution = h.getSolution()
    pre_ub = list(solution.col_value)
    for i in range(num_reac):
        if abs(model.reactions[i].upper_bound- pre_ub[i]) < pre_tol:
            ub[i] = model.reactions[i].upper_bound
        else:
            job_queue.append((i, -1))

    h.changeObjectiveSense(highspy.ObjSense.kMinimize)
    h.run()
    status = h.getModelStatus()
    if status == highspy.HighsModelStatus.kInfeasible:
        raise cobra.exceptions.Infeasible("")
    elif status != highspy.HighsModelStatus.kOptimal:
        raise ValueError(f"Unexpected solver status {h.modelStatusToString(status)} during FVA")
    solution = h.getSolution()
    pre_lb = list(solution.col_value)
    for i in range(num_reac):
        if abs(model.reactions[i].lower_bound - pre_lb[i]) < pre_tol:
            lb[i] = model.reactions[i].lower_bound
        else:
            job_queue.append((i, 1))

    lp_data.col_cost_[:] = 0.0
    job_queue_lock = th.Lock()
    workers = [None] * num_proc
    for p in range(num_proc):
        workers[p] = FVAHiGHSworker(job_queue, job_queue_lock, lb, ub, lp_data, model.tolerance)
    for i in range(num_proc):
        workers[i].start()
    for i in range(num_proc):
        workers[i].join()
    return lb, ub, sum(workers[p].n_bad for p in range(num_proc))
