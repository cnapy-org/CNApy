"""
optmdfpathway.py
=================

A cobrapy / optlang re-implementation of CellNetAnalyzer's OptMDFpathway
MILP (Haedicke et al., 2018, PLOS Comput Biol 14:e1006492), ported from the
CPLEX-based CNA implementation (CNAcomputeOptMDFpathway.m,
setup_driving_force_constraints.m, driving_forces.m).

Thermodynamic and concentration data live directly on the cobrapy model as
annotations (all optional; anything missing just falls back to a default /
gets no thermodynamic constraint):

  reaction.annotation['dG0']       standard Gibbs energy of reaction,
                                    delta_r G'0, as a number or a
                                    (value, uncertainty) pair. Reactions
                                    without this annotation may still carry
                                    flux but get no driving-force
                                    constraint.
  metabolite.annotation['Cmin']    per-metabolite concentration lower bound
  metabolite.annotation['Cmax']    per-metabolite concentration upper bound
                                    (in M); metabolites without these fall
                                    back to the Cmin/Cmax function
                                    arguments.

``optMDFpathway`` finds a flux distribution v and metabolite
log-concentrations x = log(c) such that

    S v = 0
    lb <= v <= ub          (lb/ub optionally overridden by Scenario bounds)
    log(Cmin) <= x <= log(Cmax)
    ratio_min <= exp(x_i - x_j) <= ratio_max   (optional; a fixed ratio is
                                                 the special case
                                                 ratio_min == ratio_max)

and, among all reactions that carry (nonzero) flux, the smallest
thermodynamic driving force

    df_r = -delta_r G'(x) = -( dG0_r + RT * sum_m S[m, r] * x_m )

is maximised (the classical max-min driving force, MDF -- Noor et al. 2014).
Unlike plain MDF, the pathway itself is a decision variable here
(OptMDFpathway), not fixed in advance.

Because "the MDF bound only has to hold for reactions that are actually
used" is a disjunctive condition, this needs a MILP: a binary indicator is
introduced for every candidate reaction direction and linked to the flux
through a big-M constraint, and the driving-force bound is only imposed
when that indicator is 1. Like the original CNA implementation,
``optMDFpathway`` runs an FVA preprocessing pass (via
core.multi_threaded_HiGHS_FVA) first, both to tighten those big-M values
and to prune reactions that are structurally blocked given the model and
any Scenario constraints.

Additional flux constraints -- fixed uptake rates, a fixed growth rate, and
so on -- are supplied as one or more cnapy Scenario objects (reaction_id ->
(lb, ub) mappings, the same shape core.make_scenario_feasible /
element_exchange_balance consume). These are applied directly as reaction
bound overrides on an internal copy of the model, exactly like
core.make_scenario_feasible does -- so both the FVA preprocessing step and
the MILP itself see them automatically, with no separate D/d constraint
matrix needed.

Two public functions are provided:

  optMDFpathway(...)          the main OptMDFpathway MILP.
  driving_force_ranges(...)   per-reaction min/max driving force given only
                               the concentration bounds (no flux coupling),
                               analogous to CNA's driving_forces.m. A
                               reaction only needs an LP when two or more of
                               its own metabolites participate in a
                               concentration_ratios constraint; otherwise
                               the range is computed analytically, exactly
                               as driving_forces.m does. In particular, if
                               concentration_ratios is empty (the common
                               case), no LPs are run at all.

Both functions operate on an internal copy of the model, so the model
passed in is never modified.

Performance note
-----------------
Every constraint and the objective are built from a placeholder zero
expression and added to the solver *before* their real coefficients are
attached via ``set_linear_coefficients``. That method talks directly to the
solver's constraint matrix (e.g. glp_set_mat_row for GLPK, the CPLEX/Gurobi
C APIs otherwise) and skips building/parsing a sympy expression tree
entirely. For models with many reactions and metabolites this is
substantially cheaper than constructing constraints as
``sum(coeff * variable for ...)`` expressions, which is what the
straightforward optlang usage would do. The one wrinkle is that
``set_linear_coefficients`` only works on variables/constraints/objectives
that are already attached to the solver *and* have been flushed there via
``solver.update()`` (additions are batched lazily), so every call site here
follows the pattern: build with ``Zero`` -> ``solver.add(...)`` ->
``solver.update()`` -> ``set_linear_coefficients(...)``. The same pattern is
used for driving_force_ranges' (occasional) per-reaction LPs: one Objective
is created once and its coefficients patched per reaction, rather than
rebuilding the Objective from scratch on every iteration.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import (
    Any, Dict, Iterable, List, Optional, Sequence, Tuple, TYPE_CHECKING, Union,
)

import cobra
from optlang.symbolics import Zero

from cnapy.core import multi_threaded_HiGHS_FVA

if TYPE_CHECKING:
    # cnapy.appdata.Scenario is duck-typed here (a dict-like reaction_id ->
    # (lb, ub) mapping, optionally with an add_scenario_reactions_to_model
    # method) rather than imported for real, so this module doesn't need the
    # cnapy/efmtool_link/CPLEX/Gurobi stack just to be importable.
    from cnapy.appdata import Scenario

Number = Union[int, float]
DG0Spec = Union[Number, Tuple[Number, Number]]  # value, or (value, uncertainty)


# ---------------------------------------------------------------------------
# Result container
# ---------------------------------------------------------------------------

@dataclass
class OptMDFResult:
    """Result of an optMDFpathway() call."""

    status: str
    mdf: Optional[float] = None
    fluxes: Dict[str, float] = field(default_factory=dict)
    concentrations: Dict[str, float] = field(default_factory=dict)
    driving_forces: Dict[str, float] = field(default_factory=dict)

    def __repr__(self) -> str:  # pragma: no cover - cosmetic
        if self.mdf is None:
            return f"<OptMDFResult status={self.status!r}>"
        return f"<OptMDFResult status={self.status!r} mdf={self.mdf:.4g}>"


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------

def _as_bound_dict(value: Union[Number, Dict[str, Number]],
                    metabolite_ids: Iterable[str]) -> Dict[str, float]:
    """Turn a scalar-or-dict concentration bound spec into a full dict."""
    if isinstance(value, dict):
        return {k: float(v) for k, v in value.items()}
    return {mid: float(value) for mid in metabolite_ids}


def _split_G0(spec: DG0Spec) -> Tuple[float, float]:
    """Unpack a dG0 entry into (value, uncertainty)."""
    if isinstance(spec, (tuple, list)):
        return float(spec[0]), float(spec[1])
    return float(spec), 0.0


def _reaction_dG0(rxn: cobra.Reaction) -> Optional[Tuple[float, float]]:
    """
    Read a reaction's standard Gibbs energy from annotation['dG0'] (a
    number, or a (value, uncertainty) pair). Returns None -- meaning "no
    thermodynamic constraint for this reaction" -- if the annotation is
    absent or NaN.
    """
    spec = rxn.annotation.get("dG0")
    if spec is None:
        return None
    val, unc = _split_G0(spec)
    if math.isnan(val):
        return None
    return val, unc


def _resolve_concentration_bounds(
    model: cobra.Model,
    Cmin: Union[Number, Dict[str, Number]],
    Cmax: Union[Number, Dict[str, Number]],
) -> Tuple[Dict[str, float], Dict[str, float]]:
    """
    Per-metabolite concentration bounds (in M): metabolite.annotation
    ['Cmin']/['Cmax'] take precedence when present; everything else falls
    back to the Cmin/Cmax arguments (a scalar applies to every metabolite,
    a dict supplies specific defaults).
    """
    met_ids = [met.id for met in model.metabolites]
    Cmin_d = _as_bound_dict(Cmin, met_ids)
    Cmax_d = _as_bound_dict(Cmax, met_ids)
    for met in model.metabolites:
        cmin_annot = met.annotation.get("Cmin")
        if cmin_annot is not None:
            Cmin_d[met.id] = float(cmin_annot)
        cmax_annot = met.annotation.get("Cmax")
        if cmax_annot is not None:
            Cmax_d[met.id] = float(cmax_annot)
    missing = [mid for mid in met_ids if mid not in Cmin_d or mid not in Cmax_d]
    if missing:
        raise ValueError(
            "Missing concentration bounds for metabolites: "
            f"{missing[:10]}{' ...' if len(missing) > 10 else ''}"
        )
    return Cmin_d, Cmax_d


def _normalize_concentration_ratios(
    concentration_ratios: Optional[Sequence[Sequence[Any]]],
) -> List[Tuple[str, str, float, float]]:
    """
    Normalize concentration_ratios entries into (met_i, met_j, ratio_min,
    ratio_max) tuples constraining concentration_i / concentration_j to
    [ratio_min, ratio_max]. Each entry may be given as:
      (met_i, met_j, ratio)                  -- a fixed ratio
      (met_i, met_j, ratio_min, ratio_max)   -- a ratio range
    """
    out: List[Tuple[str, str, float, float]] = []
    for entry in concentration_ratios or []:
        if len(entry) == 3:
            mi, mj, ratio = entry
            out.append((mi, mj, float(ratio), float(ratio)))
        elif len(entry) == 4:
            mi, mj, lo, hi = entry
            out.append((mi, mj, float(lo), float(hi)))
        else:
            raise ValueError(
                "Invalid concentration_ratios entry (expected length 3 for "
                f"a fixed ratio or 4 for a range): {entry!r}")
    return out


ConstraintTriple = Tuple[Dict[str, float], str, float]
ScenarioConstraint = Union["Scenario", ConstraintTriple]


def _is_constraint_triple(item: Any) -> bool:
    return (isinstance(item, tuple) and len(item) == 3
            and isinstance(item[0], dict) and isinstance(item[1], str))


def _as_constraint_list(
    scenario_constraints: Optional[Union[ScenarioConstraint, Iterable[ScenarioConstraint]]],
) -> List[ScenarioConstraint]:
    if scenario_constraints is None:
        return []
    if _is_constraint_triple(scenario_constraints):
        return [scenario_constraints]
    if hasattr(scenario_constraints, "items"):  # a single dict-like Scenario
        return [scenario_constraints]
    return list(scenario_constraints)


def scenario_constraints_to_triples(
    scenarios: Optional[Union[ScenarioConstraint, Iterable[ScenarioConstraint]]],
    m: cobra.Model,
) -> List[ConstraintTriple]:
    """
    Normalize a heterogeneous list of scenario constraints into
    (expression, constraint_type, rhs) triples -- exactly the format
    core.multi_threaded_HiGHS_FVA's ``constraints`` argument expects, so the
    same list drives both the FVA preprocessing step and the MILP's own
    linear constraints. Each entry may be:

      - a raw triple  ({reaction_id: coefficient}, constraint_type, rhs),
        with constraint_type in {'=', '<=', '>='} -- for arbitrary linear
        constraints over reaction fluxes that a single reaction's bounds
        can't express, e.g. a minimal yield requirement (product flux at
        least half the substrate uptake magnitude):
            ({"EX_product": 1.0, "EX_substrate": 0.5}, '>=', 0.0)

      - a Scenario-like object: a reaction_id -> (lb, ub) flux-bound
        mapping, the same shape core.make_scenario_feasible /
        element_exchange_balance consume. Any reactions it needs are added
        to `m` first via .add_scenario_reactions_to_model (if it has that
        method). A fixed bound (lb == ub) becomes a single '=' triple; a
        genuine range becomes up to two triples ('>=' / '<=', one per
        finite side).

    `m` is mutated in place only via Scenario.add_scenario_reactions_to_model
    calls (to register any reactions a Scenario needs); the constraints
    themselves are returned as triples, not applied to `m`.
    """
    triples: List[ConstraintTriple] = []
    for item in _as_constraint_list(scenarios):
        if _is_constraint_triple(item):
            expr, ctype, rhs = item
            if ctype not in ("=", "<=", ">="):
                raise ValueError(f"Unknown constraint type {ctype!r} in {item!r}")
            triples.append((dict(expr), ctype, float(rhs)))
        else:  # a Scenario-like reaction_id -> (lb, ub) mapping
            add_scenario_reactions = getattr(item, "add_scenario_reactions_to_model", None)
            if add_scenario_reactions is not None:
                add_scenario_reactions(m)
            for rid, (lb, ub) in item.items():
                expr = {rid: 1.0}
                if lb == ub:
                    triples.append((expr, "=", float(lb)))
                else:
                    if math.isfinite(lb):
                        triples.append((expr, ">=", float(lb)))
                    if math.isfinite(ub):
                        triples.append((expr, "<=", float(ub)))
    return triples


# ---------------------------------------------------------------------------
# main OptMDFpathway MILP
# ---------------------------------------------------------------------------

def optMDFpathway(
    model: cobra.Model,
    Cmin: Union[Number, Dict[str, Number]] = 1e-6,
    Cmax: Union[Number, Dict[str, Number]] = 1e-2,
    RT: float = 8.314e-3 * 298.15,
    scenarios: Optional[Union["Scenario", Iterable["Scenario"]]] = None,
    concentration_ratios: Optional[Sequence[Sequence[Any]]] = None,
    ignore_reactions: Optional[Iterable[str]] = None,
    flux_bound_M: Optional[Number] = None,
    dG_bound_M: Number = 1e4,
    B_bounds: Tuple[Number, Number] = (-1e4, 1e4),
    use_fva_preprocessing: Optional[bool] = None,
    blocked_flux_tol: float = 1e-9,
    verbose: bool = False,
) -> OptMDFResult:
    """
    Compute an OptMDFpathway solution: the flux distribution and metabolite
    concentration profile that jointly maximise the max-min driving force.

    Parameters
    ----------
    model : cobra.Model
        The metabolic model. Not modified (an internal copy is used).
        Reactions get their thermodynamic data from annotation['dG0'] (a
        number, or a (value, uncertainty) pair); reactions without this
        annotation may still carry flux but get no driving-force
        constraint. Metabolites get their concentration bounds from
        annotation['Cmin']/['Cmax'] when present, falling back to the
        Cmin/Cmax arguments below otherwise.
    Cmin, Cmax : float or dict {metabolite_id: value}
        Default concentration bounds in M (mol/L), used for any metabolite
        that doesn't carry annotation['Cmin']/['Cmax']. A scalar applies
        the same bound to every such metabolite; a dict may supply
        per-metabolite defaults.
    RT : float
        Gas constant * temperature, in energy units matching dG0 (default:
        RT at 25 deg C in kJ/mol).
    scenarios : optional scenario constraint(s)
        Additional linear constraints over reaction fluxes -- e.g. a fixed
        uptake rate, a fixed growth rate, or a minimal yield requirement.
        Each entry may be:
          - a raw triple ({reaction_id: coefficient}, constraint_type, rhs)
            with constraint_type in {'=', '<=', '>='}, for constraints a
            single reaction's bounds can't express, e.g. a minimal yield
            requirement (product flux at least half the substrate uptake
            magnitude): ({"EX_product": 1.0, "EX_substrate": 0.5}, '>=', 0.0)
          - a Scenario-like object: a reaction_id -> (lb, ub) flux-bound
            mapping, the same shape core.make_scenario_feasible /
            element_exchange_balance consume (a fixed bound becomes a
            single '=' constraint, a genuine range becomes one or two
            inequalities). Any reactions it needs are added to the internal
            model copy first, via .add_scenario_reactions_to_model if it
            has that method.
        A single item (not wrapped in a list) is also accepted. These are
        normalised into (expression, constraint_type, rhs) triples -- see
        scenario_constraints_to_triples -- which are then used both as the
        FVA preprocessing step's ``constraints`` argument and as ordinary
        linear constraints added to the MILP itself.
    concentration_ratios : optional list of tuples
        Constrains concentration_i / concentration_j for pairs of
        metabolites, e.g. to couple cofactor pairs such as ATP/ADP. Each
        entry is either
          (met_i, met_j, ratio)                 -- a fixed ratio, or
          (met_i, met_j, ratio_min, ratio_max)   -- a ratio range.
    ignore_reactions : optional iterable of reaction ids
        Reactions to exclude from driving-force constraints even if they
        carry a dG0 annotation (e.g. reactions with poorly defined
        thermodynamics).
    flux_bound_M : optional float
        Upper cap on the big-M used to link flux to its binary "reaction is
        active" indicator. If FVA preprocessing is used (the default), the
        per-reaction FVA bound is used directly (capped at this value if
        given); otherwise this defaults to the largest finite reaction
        bound in the model (or 1000 if none is finite), again capped per
        reaction at that reaction's own bound.
    dG_bound_M : float
        Big-M used to relax the driving-force constraint when a reaction's
        indicator is 0. Must be larger than the largest possible
        |driving force| in the model (default 1e4, generous for typical
        kJ/mol-scale thermodynamics with M-range concentrations).
    B_bounds : (float, float)
        Lower/upper bound for the MDF variable itself.
    use_fva_preprocessing : optional bool
        Mirrors the FVA preprocessing step the original CNA OptMDFpathway
        code runs before setting up the thermodynamic MILP: flux
        variability analysis (via core.multi_threaded_HiGHS_FVA, run with
        the same scenario constraints -- see ``scenarios`` above) computes
        the tightest achievable [lb, ub] per reaction given the whole
        network, which is then used (a) as the big-M in the flux/indicator
        linking constraints -- far tighter than a reaction's own static
        bounds, which speeds up and stabilises the MILP -- and (b) to
        altogether skip reactions that FVA proves are blocked in a given
        direction (or both), since they structurally cannot be "used" and
        so need no driving-force machinery at all.
        * None (default): try FVA preprocessing; if core.py's dependencies
          (cnapy/highspy/...) aren't importable, silently fall back to
          static reaction bounds.
        * True: require FVA preprocessing; raise ImportError if unavailable.
        * False: skip it and always use static reaction bounds (the
          behaviour before this option existed).
    blocked_flux_tol : float
        Absolute flux tolerance below which an FVA-computed bound is
        treated as zero (i.e. that direction is blocked). Only used when
        FVA preprocessing is active.
    verbose : bool
        Print basic solve information.

    Note
    ----
    If nothing forces the pathway to carry flux (no scenario/bound forcing
    nonzero flux anywhere), the all-zero flux vector trivially satisfies
    "every *active* reaction respects the MDF bound" (there are none), and
    mdf will just come back at B_bounds[1]. Always pair this with a
    scenario constraint that forces flux through the pathway, as in the
    demo below.

    Returns
    -------
    OptMDFResult
        .status               optlang solver status ("optimal" if solved)
        .mdf                  the maximal max-min driving force
        .fluxes               {reaction_id: flux}
        .concentrations       {metabolite_id: concentration in M}
        .driving_forces       {reaction_id: driving force}, only for
                               reactions that had a dG0 annotation and were
                               not found to be structurally blocked by FVA
    """
    m = model.copy()
    solver = m.solver
    # Use the solver-specific optlang classes (m.problem), not the generic
    # optlang.interface ones -- optlang models refuse to add variables /
    # constraints built from a different interface than their own backend.
    Variable, Constraint, Objective = m.problem.Variable, m.problem.Constraint, m.problem.Objective

    # -- 0) normalize scenario constraints into (expression, type, rhs)
    #    triples -- any reactions a Scenario-like entry needs are added to
    #    `m` here (via .add_scenario_reactions_to_model), so this must
    #    happen before anything below reads m.reactions / m.metabolites.
    scenario_triples = scenario_constraints_to_triples(scenarios, m)

    Cmin_d, Cmax_d = _resolve_concentration_bounds(m, Cmin, Cmax)
    ignore = set(ignore_reactions or [])
    ratio_specs = _normalize_concentration_ratios(concentration_ratios)

    # -- FVA preprocessing: compute the tightest achievable per-reaction
    #    flux range given the whole network + scenario constraints, for use
    #    as a tight big-M and to prune structurally blocked reactions.
    fva_bounds: Optional[Dict[str, Tuple[float, float]]] = None
    if use_fva_preprocessing is not False:
        tol = m.tolerance
        m.tolerance = blocked_flux_tol
        fva_lb, fva_ub, n_bad = multi_threaded_HiGHS_FVA(m, constraints=scenario_triples)
        m.tolerance = tol
        fva_bounds = {rxn.id: (lo, hi) for rxn, lo, hi in zip(m.reactions, fva_lb, fva_ub)}
        if verbose:
            print(f"FVA preprocessing done "
                    f"({n_bad} reaction(s) had solver trouble)" if n_bad
                    else "FVA preprocessing done.")

    # -- 1) log-concentration variables and the MDF variable B --------------
    # (logc is equivalent to c_vars in setup_driving_force_constraints.m)
    logc: Dict[str, Variable] = {}
    for mid in Cmin_d:
        lb, ub = math.log(Cmin_d[mid]), math.log(Cmax_d[mid])
        if lb > ub:
            raise ValueError(f"Cmin > Cmax for metabolite {mid!r}")
        logc[mid] = Variable(f"logc_{mid}", lb=lb, ub=ub)
    B = Variable("MDF", lb=B_bounds[0], ub=B_bounds[1])
    solver.add(list(logc.values()) + [B])

    # From here on, every constraint is created with a placeholder ``Zero``
    # expression (cheap: no variable-dependent sympy tree at all) and its
    # real coefficients are collected in a matching dict, to be pushed into
    # the solver later in one batch via set_linear_coefficients -- see the
    # module docstring's "Performance note".
    all_cons: List[Constraint] = []
    all_coeffs: List[Dict[Variable, float]] = []

    # -- 2) concentration ratio constraints (fixed or ranged) ----------------
    for i, (mi, mj, lo, hi) in enumerate(ratio_specs):
        all_cons.append(Constraint(
            Zero, lb=math.log(lo), ub=math.log(hi),
            name=f"conc_ratio_{i}_{mi}_{mj}"))
        all_coeffs.append({logc[mi]: 1.0, logc[mj]: -1.0})

    # -- 3) per-reaction driving-force machinery -----------------------------
    # Fallback big-M for when FVA preprocessing isn't available: the
    # largest finite static reaction bound in the model (or 1000).
    static_default_M = flux_bound_M
    if static_default_M is None:
        finite_bounds = [abs(b) for r in m.reactions
                          for b in (r.lower_bound, r.upper_bound)
                          if math.isfinite(b) and b != 0]
        static_default_M = max(finite_bounds) if finite_bounds else 1000.0

    stoich: Dict[str, Dict[str, float]] = {}   # rxn.id -> {met.id: coeff}
    G0_eff: Dict[str, float] = {}              # rxn.id -> worst-case delta_r G0

    new_bin_vars: List[Variable] = []
    n_fwd = n_rev = n_blocked = n_no_dG0 = 0

    for rxn in m.reactions:
        if rxn.id in ignore:
            continue
        dG0 = _reaction_dG0(rxn)
        if dG0 is None:
            n_no_dG0 += 1
            continue
        val, unc = dG0

        met_coeffs = {met.id: coeff for met, coeff in rxn.metabolites.items()}
        if not met_coeffs:
            continue

        # Per-reaction achievable flux range: the FVA-tightened one when
        # available (falling back to the static bounds if FVA had solver
        # trouble on this particular reaction), otherwise the static bounds.
        if fva_bounds is not None:
            fva_lo, fva_hi = fva_bounds[rxn.id]
            if math.isnan(fva_lo) or math.isnan(fva_hi):
                fva_lo, fva_hi = rxn.lower_bound, rxn.upper_bound
        else:
            fva_lo, fva_hi = rxn.lower_bound, rxn.upper_bound

        can_fwd = fva_hi > blocked_flux_tol
        can_rev = fva_lo < -blocked_flux_tol
        if not can_fwd and not can_rev:
            # Structurally blocked under the current network/constraints --
            # this reaction can never be "used", so it needs no MDF
            # constraint or binary at all.
            n_blocked += 1
            continue

        stoich[rxn.id] = met_coeffs
        # conservative (worst-case) standard Gibbs energy: adding the
        # uncertainty guarantees df_fwd >= B for every value the true dG0
        # could take in [val - unc, val + unc].
        G0_eff[rxn.id] = val + unc

        # driving force if the reaction runs forward:
        #   df_fwd = -G0_eff - RT * sum_m S[m] * logc[m]
        # Constraint enforced only when z_fwd = 1 (df_fwd >= B):
        #   -RT*sum(S[m]*logc[m]) - B - dG_bound_M*z_fwd  >=  G0_eff - dG_bound_M
        # (the constant G0_eff is folded straight into the constraint's
        # lower bound, since set_linear_coefficients only ever sets
        # *variable* coefficients, never a constant offset)
        if can_fwd:
            M_r = fva_hi if flux_bound_M is None else min(flux_bound_M, fva_hi)
            z_fwd = Variable(f"z_fwd_{rxn.id}", type="binary")
            new_bin_vars.append(z_fwd)

            all_cons.append(Constraint(Zero, ub=0, name=f"link_fwd_{rxn.id}"))
            all_coeffs.append({rxn.forward_variable: 1.0, z_fwd: -M_r})

            df_coeffs = {logc[mid]: -RT * coeff for mid, coeff in met_coeffs.items()}
            df_coeffs[B] = -1.0
            df_coeffs[z_fwd] = -dG_bound_M
            all_cons.append(Constraint(
                Zero, lb=G0_eff[rxn.id] - dG_bound_M, name=f"df_fwd_{rxn.id}"))
            all_coeffs.append(df_coeffs)
            n_fwd += 1

        # running in reverse negates the effective stoichiometry, so the
        # reverse driving force is simply -df_fwd:
        #   RT*sum(S[m]*logc[m]) - B - dG_bound_M*z_rev  >=  -G0_eff - dG_bound_M
        if can_rev:
            M_r = abs(fva_lo) if flux_bound_M is None else min(flux_bound_M, abs(fva_lo))
            z_rev = Variable(f"z_rev_{rxn.id}", type="binary")
            new_bin_vars.append(z_rev)

            all_cons.append(Constraint(Zero, ub=0, name=f"link_rev_{rxn.id}"))
            all_coeffs.append({rxn.reverse_variable: 1.0, z_rev: -M_r})

            df_coeffs = {logc[mid]: RT * coeff for mid, coeff in met_coeffs.items()}
            df_coeffs[B] = -1.0
            df_coeffs[z_rev] = -dG_bound_M
            all_cons.append(Constraint(
                Zero, lb=-G0_eff[rxn.id] - dG_bound_M, name=f"df_rev_{rxn.id}"))
            all_coeffs.append(df_coeffs)
            n_rev += 1

    # -- 4) scenario constraints (fixed uptake rates, yield requirements,
    #    ...), as ordinary linear constraints on the reactions' flux
    #    expressions -- reuses the same triples the FVA preprocessing step
    #    above was given, so both see exactly the same constraints. ---------
    for i, (expr, ctype, rhs) in enumerate(scenario_triples):
        coeffs: Dict[Variable, float] = {}
        try:
            rxns = {rid: m.reactions.get_by_id(rid) for rid in expr}
        except KeyError as exc:
            print(f"Skipping scenario constraint referencing a reaction not "
                  f"in the model ({exc}): {expr}")
            continue
        for rid, coeff in expr.items():
            rxn = rxns[rid]
            coeffs[rxn.forward_variable] = coeffs.get(rxn.forward_variable, 0.0) + coeff
            coeffs[rxn.reverse_variable] = coeffs.get(rxn.reverse_variable, 0.0) - coeff
        if ctype == "=":
            con = Constraint(Zero, lb=rhs, ub=rhs, name=f"scenario_{i}")
        elif ctype == "<=":
            con = Constraint(Zero, ub=rhs, name=f"scenario_{i}")
        else:  # ">="
            con = Constraint(Zero, lb=rhs, name=f"scenario_{i}")
        all_cons.append(con)
        all_coeffs.append(coeffs)

    # -- 5) push every binary + constraint into the solver in one batch,
    #    flush it, then patch in the real coefficients ------------------------
    solver.add(new_bin_vars)
    solver.add(all_cons)
    solver.update()  # flush pending additions so set_linear_coefficients can see them
    for con, coeffs in zip(all_cons, all_coeffs):
        con.set_linear_coefficients(coeffs)

    # -- 6) objective: maximise the max-min driving force --------------------
    solver.objective = Objective(Zero, direction="max")
    solver.update()
    solver.objective.set_linear_coefficients({B: 1.0})

    if verbose:
        print(f"OptMDFpathway: {len(stoich)} reactions with dG0 annotations "
              f"({n_fwd} forward + {n_rev} reverse directions, "
              f"{n_blocked} blocked & skipped, {n_no_dG0} without a dG0 "
              f"annotation), {len(new_bin_vars)} binaries" +
              ("" if fva_bounds is not None else
               f", default big-M = {static_default_M:g}"))

    status = solver.optimize()
    result = OptMDFResult(status=status)
    if status != "optimal":
        if verbose:
            print(f"Solve finished with status: {status}")
        return result

    result.mdf = B.primal
    for rxn in m.reactions:
        result.fluxes[rxn.id] = rxn.flux
    for mid, v in logc.items():
        result.concentrations[mid] = math.exp(v.primal)
    for rid, coeffs in stoich.items():
        dG = G0_eff[rid] + RT * sum(
            coeff * math.log(result.concentrations[mid])
            for mid, coeff in coeffs.items())
        result.driving_forces[rid] = -dG

    if verbose:
        print(f"MDF = {result.mdf:.4g} (same energy units as dG0/RT)")

    return result


# ---------------------------------------------------------------------------
# driving-force ranges (no flux coupling) -- analogous to driving_forces.m
# ---------------------------------------------------------------------------

def driving_force_ranges(
    model: cobra.Model,
    Cmin: Union[Number, Dict[str, Number]] = 1e-6,
    Cmax: Union[Number, Dict[str, Number]] = 1e-2,
    RT: float = 8.314e-3 * 298.15,
    concentration_ratios: Optional[Sequence[Sequence[Any]]] = None,
    ignore_reactions: Optional[Iterable[str]] = None,
) -> Dict[str, Tuple[float, float]]:
    """
    For every reaction with a dG0 annotation, compute the achievable range
    of its driving force from the concentration bounds (and
    concentration_ratios) alone, with no coupling to the flux distribution
    -- mirrors CNA's driving_forces.m.

    Like driving_forces.m, a reaction only needs an LP when *two or more*
    of its own metabolites participate in a concentration_ratios constraint
    (with each other or with something outside the reaction) -- only then
    can a ratio constraint actually couple the extremes achievable within
    that one reaction. Otherwise each metabolite of the reaction can
    independently be pushed to whichever bound (Cmin or Cmax) favours the
    direction being optimised, which is computed directly with no solver
    call at all. In particular, if concentration_ratios is empty (the
    common case), no LPs are run at all.

    Parameters
    ----------
    model, Cmin, Cmax, RT, concentration_ratios, ignore_reactions :
        Same meaning as in optMDFpathway (dG0/Cmin/Cmax read from
        annotations first, falling back to the Cmin/Cmax arguments).

    Returns
    -------
    dict {reaction_id: (min_driving_force, max_driving_force)}
    """
    Cmin_d, Cmax_d = _resolve_concentration_bounds(model, Cmin, Cmax)
    ignore = set(ignore_reactions or [])
    ratio_specs = _normalize_concentration_ratios(concentration_ratios)

    log_cmin = {mid: math.log(v) for mid, v in Cmin_d.items()}
    log_cmax = {mid: math.log(v) for mid, v in Cmax_d.items()}

    has_ratio = set()
    for mi, mj, _, _ in ratio_specs:
        has_ratio.add(mi)
        has_ratio.add(mj)

    ranges: Dict[str, Tuple[float, float]] = {}
    # reactions where a ratio constraint links >=2 of their own metabolites
    # -- the only ones that actually need an LP:
    lp_needed: List[Tuple[str, Dict[str, float], float]] = []

    for rxn in model.reactions:
        if rxn.id in ignore:
            continue
        dG0 = _reaction_dG0(rxn)
        if dG0 is None:
            continue
        val, unc = dG0
        met_coeffs = {met.id: coeff for met, coeff in rxn.metabolites.items()}
        if not met_coeffs:
            continue
        G0_eff = val + unc

        n_ratio_linked = sum(1 for mid in met_coeffs if mid in has_ratio)
        if n_ratio_linked <= 1:
            # Analytic extremes (see driving_forces.m): to minimise
            # df = -G0_eff - RT*sum(coeff*logc), maximise sum(coeff*logc) by
            # pushing positive-coefficient metabolites to logCmax and
            # negative-coefficient ones to logCmin (and vice versa for the
            # maximum) -- valid whenever no ratio constraint ties this
            # reaction's own metabolites' extremes together.
            pos_at_max = sum(c * log_cmax[mid] for mid, c in met_coeffs.items() if c > 0)
            pos_at_min = sum(c * log_cmin[mid] for mid, c in met_coeffs.items() if c > 0)
            neg_at_min = sum(c * log_cmin[mid] for mid, c in met_coeffs.items() if c < 0)
            neg_at_max = sum(c * log_cmax[mid] for mid, c in met_coeffs.items() if c < 0)
            min_df = -G0_eff - RT * (pos_at_max + neg_at_min)
            max_df = -G0_eff - RT * (pos_at_min + neg_at_max)
            ranges[rxn.id] = (min_df, max_df)
        else:
            lp_needed.append((rxn.id, met_coeffs, G0_eff))

    if not lp_needed:
        return ranges

    # Only reached when concentration_ratios actually couples two or more
    # metabolites within the same reaction -- build the optlang model
    # lazily, and only now.
    m = model.copy()
    solver = m.solver
    Variable, Constraint, Objective = m.problem.Variable, m.problem.Constraint, m.problem.Objective

    logc: Dict[str, Variable] = {
        mid: Variable(f"logc_{mid}", lb=log_cmin[mid], ub=log_cmax[mid])
        for mid in Cmin_d
    }
    solver.add(list(logc.values()))

    ratio_cons: List[Constraint] = []
    ratio_coeffs: List[Dict[Variable, float]] = []
    for i, (mi, mj, lo, hi) in enumerate(ratio_specs):
        ratio_cons.append(Constraint(
            Zero, lb=math.log(lo), ub=math.log(hi),
            name=f"conc_ratio_{i}_{mi}_{mj}"))
        ratio_coeffs.append({logc[mi]: 1.0, logc[mj]: -1.0})
    solver.add(ratio_cons)
    solver.update()
    for con, coeffs in zip(ratio_cons, ratio_coeffs):
        con.set_linear_coefficients(coeffs)

    # A single reusable objective: coefficients are patched per reaction via
    # set_linear_coefficients rather than rebuilding the Objective (and
    # parsing a fresh sympy expression) on every iteration.
    solver.objective = Objective(Zero, direction="min")
    solver.update()

    prev_coeffs: Dict[Variable, float] = {}
    for rid, met_coeffs, G0_eff in lp_needed:
        term_coeffs = {logc[mid]: -RT * coeff for mid, coeff in met_coeffs.items()}
        reset = {v: 0.0 for v in prev_coeffs if v not in term_coeffs}
        solver.objective.set_linear_coefficients({**reset, **term_coeffs})
        prev_coeffs = term_coeffs

        solver.objective.direction = "min"
        solver.optimize()
        lo_df = -G0_eff + solver.objective.value
        solver.objective.direction = "max"
        solver.optimize()
        hi_df = -G0_eff + solver.objective.value
        ranges[rid] = (lo_df, hi_df)

    return ranges


# ---------------------------------------------------------------------------
# self-test / demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # A tiny toy pathway:  EX_A -> A -R1-> B -R2-> C -> EX_C
    # R1 is thermodynamically favourable at standard conditions, R2 is not
    # (it needs a concentration gradient to become favourable) -- a good
    # minimal test that the MILP actually engages the concentration
    # variables rather than just doing plain FBA.
    toy = cobra.Model("toy_pathway")

    A = cobra.Metabolite("A", compartment="c")
    B = cobra.Metabolite("B", compartment="c")
    C = cobra.Metabolite("C", compartment="c")

    EX_A = cobra.Reaction("EX_A", lower_bound=-10, upper_bound=0)
    EX_A.add_metabolites({A: -1})

    R1 = cobra.Reaction("R1", lower_bound=0, upper_bound=1000)
    R1.add_metabolites({A: -1, B: 1})
    R1.annotation["dG0"] = -5.0  # kJ/mol, favourable at standard conditions

    R2 = cobra.Reaction("R2", lower_bound=0, upper_bound=1000)
    R2.add_metabolites({B: -1, C: 1})
    R2.annotation["dG0"] = 3.0  # kJ/mol, needs help from concentrations

    EX_C = cobra.Reaction("EX_C", lower_bound=0, upper_bound=1000)
    EX_C.add_metabolites({C: -1})

    toy.add_reactions([EX_A, R1, R2, EX_C])

    # A minimal Scenario stand-in -- only needs to behave like a
    # {reaction_id: (lb, ub)} mapping (a real cnapy Scenario may
    # additionally implement .add_scenario_reactions_to_model; see
    # scenario_constraints_to_triples' docstring). Combined here with a
    # genuine multi-reaction constraint given directly as a triple: a
    # minimal yield requirement of >= 0.5 mol C per mol A consumed
    # (EX_A is negative while importing, so -EX_A is the uptake magnitude).
    scenario = {"EX_C": (1.0, 1000.0)}                          # force >= 1 unit of net C production
    yield_constraint = ({"EX_C": 1.0, "EX_A": 0.5}, ">=", 0.0)  # EX_C >= 0.5 * (-EX_A)

    result = optMDFpathway(
        toy,
        Cmin=1e-6,
        Cmax=1e-2,
        scenarios=[scenario, yield_constraint],
        # use_fva_preprocessing defaults to "try it, fall back quietly if
        # core.py's dependencies (cnapy/highspy/...) aren't importable" --
        # explicitly set True/False to require it / always skip it.
        verbose=True,
    )

    print(result)
    print("fluxes:        ", result.fluxes)
    print("concentrations:", result.concentrations)
    print("driving forces:", result.driving_forces)

    print("\ndriving_force_ranges, no concentration_ratios "
          "(purely analytic, no LPs run at all):")
    for rid, (lo, hi) in driving_force_ranges(toy).items():
        print(f"  {rid}: [{lo:.3g}, {hi:.3g}] kJ/mol")

    print("\ndriving_force_ranges with a concentration ratio *range* on "
          "A/B (couples two metabolites of R1, so R1 now needs an LP; R2 "
          "still doesn't, since only B -- one of its two metabolites -- "
          "is ratio-linked):")
    ranges = driving_force_ranges(
        toy, concentration_ratios=[("A", "B", 0.5, 2.0)])
    for rid, (lo, hi) in ranges.items():
        print(f"  {rid}: [{lo:.3g}, {hi:.3g}] kJ/mol")