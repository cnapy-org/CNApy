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
    lb <= v <= ub          (plus any linear scenario constraints, see below)
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

Additional flux constraints -- fixed uptake rates, a fixed growth rate, a
minimal yield requirement, and so on -- are supplied via ``scenarios``:
either raw (expression, constraint_type, rhs) triples for arbitrary linear
constraints over reaction fluxes, or cnapy Scenario-like objects
(reaction_id -> (lb, ub) mappings, the same shape
core.make_scenario_feasible / element_exchange_balance consume), which are
normalised into the same triple form. These triples are used directly both
as core.multi_threaded_HiGHS_FVA's ``constraints`` argument and as ordinary
linear constraints added to the MILP -- no separate D/d matrix needed.

Strictly (fully) flux-coupled reaction groups -- e.g. from flux coupling
analysis -- can be supplied via ``reaction_subsets`` to speed up both
stages: FVA preprocessing runs on a compressed model with one reaction per
group (see _compress_for_fva), and the MILP shares one pair of binaries and
one flux-linking constraint per group instead of per reaction. Each
member's own driving-force constraint is still built individually --
thermodynamics is inherently per-reaction -- just gated by the group's
shared binaries.

For solving more than once against the same model/constraints -- most
importantly, iterative thermodynamic-bottleneck analysis (solve, find the
current minimal bottleneck, relax exactly its driving-force constraint(s),
repeat for as many iterations as the caller wants) -- use OptMDFAnalysis
directly instead of optMDFpathway: it builds the model copy, FVA, and MILP
exactly once, and every subsequent solve()/find_bottleneck()/relax() call
only touches what actually changed.

Public API:

  OptMDFAnalysis(...)         stateful solver: build once, call .solve(),
                               .shadow_prices(), .find_bottleneck(),
                               .relax(...), .step(), or .run() as needed.
  optMDFpathway(...)          one-shot wrapper around OptMDFAnalysis, for
                               callers that just want a single solve.
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

Both OptMDFAnalysis and driving_force_ranges operate on an internal copy of
the model, so the model passed in is never modified.

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

import contextlib
import math
from dataclasses import dataclass, field
from typing import (
    Any, Dict, Iterable, Iterator, List, Optional, Sequence, Set, Tuple,
    TYPE_CHECKING, Union,
)
import time

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
    driving_force_duals: Dict[str, float] = field(default_factory=dict)
    bottleneck_reactions: List[str] = field(default_factory=list)
    objective_value: Optional[float] = None

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
# strictly-coupled reaction subsets (flux coupling)
# ---------------------------------------------------------------------------

def _normalize_reaction_subsets(
    reaction_subsets: Optional[Sequence[Sequence[Tuple[str, Number]]]],
) -> Dict[str, Tuple[str, float]]:
    """
    Normalize a list of strictly-coupled reaction subsets into a flat
    {reaction_id: (representative_id, ratio)} lookup (including the
    representative's own entry, mapped to itself with ratio 1.0), where

        flux(reaction_id) == ratio * flux(representative_id)

    holds in every feasible steady state (ratio may be negative, meaning
    the reaction runs opposite the representative as oriented in the
    model). Reactions not mentioned in any subset simply aren't present in
    the returned dict -- callers should treat a missing entry as
    (reaction_id, 1.0), i.e. its own singleton subset.

    Each subset is a sequence of (reaction_id, factor) pairs; the first
    entry is taken as that subset's representative (factor must be
    nonzero), and every other member's ratio to it is factor_i / factor_rep.
    A subset with fewer than two entries carries no coupling information
    and is ignored.
    """
    out: Dict[str, Tuple[str, float]] = {}
    for subset in reaction_subsets or []:
        subset = list(subset)
        if len(subset) < 2:
            continue
        rep_id, rep_factor = subset[0]
        rep_factor = float(rep_factor)
        if rep_factor == 0:
            raise ValueError(f"Representative reaction {rep_id!r} in a "
                              "reaction_subsets entry has a zero factor")
        for rid, factor in subset:
            if rid in out:
                raise ValueError(
                    f"Reaction {rid!r} appears in more than one "
                    "reaction_subsets entry")
            out[rid] = (rep_id, float(factor) / rep_factor)
    return out


def _compress_for_fva(
    m: cobra.Model,
    subset_ratio: Dict[str, Tuple[str, float]],
    scenario_triples: Sequence[ConstraintTriple],
) -> Tuple[cobra.Model, List[ConstraintTriple]]:
    """
    Build a smaller, throwaway model for FVA purposes only: for every
    reaction_subsets group, keep just the representative reaction, with its
    stoichiometry rebuilt as the ratio-weighted sum of every member's
    original stoichiometry (so metabolites shared with reactions outside
    the subset keep the correct net coefficient; a metabolite touched only
    by members of one subset -- e.g. an intermediate in an unbranched chain
    -- automatically ends up with an all-zero row, which is harmless: HiGHS
    treats it as a trivially satisfied 0 <= 0 <= 0 constraint) and bounds
    tightened to the intersection of every member's own bound (translated
    through the group's ratios). The other members are then removed.
    scenario_triples referencing a dropped member are rewritten in terms of
    its representative (coefficient scaled by the member's ratio).

    This model is for FVA only -- it must never be used for the MILP
    itself, since each individual member's own identity (and therefore its
    own thermodynamic data) has been thrown away. The original `m` is not
    modified; if there is nothing to compress, `m` itself is returned
    unchanged (no copy made).

    Returns
    -------
    (compressed_model, rewritten_scenario_triples)
    """
    groups: Dict[str, List[Tuple[str, float]]] = {}
    for member_id, (rep_id, ratio) in subset_ratio.items():
        groups.setdefault(rep_id, []).append((member_id, ratio))
    groups = {rep_id: members for rep_id, members in groups.items() if len(members) > 1}

    if not groups:
        return m, list(scenario_triples)

    m_fva = m.copy()

    for rep_id, members in groups.items():
        combined: Dict[str, float] = {}
        lo, hi = -math.inf, math.inf
        for member_id, ratio in members:
            member = m.reactions.get_by_id(member_id)  # original (uncompressed) stoichiometry/bounds
            for met, coeff in member.metabolites.items():
                combined[met.id] = combined.get(met.id, 0.0) + coeff * ratio
            m_lo, m_hi = member.lower_bound, member.upper_bound
            if ratio > 0:
                cand_lo, cand_hi = m_lo / ratio, m_hi / ratio
            else:
                cand_lo, cand_hi = m_hi / ratio, m_lo / ratio
            lo, hi = max(lo, cand_lo), min(hi, cand_hi)
        if lo > hi:
            raise ValueError(
                f"reaction_subsets entry for representative {rep_id!r} has "
                f"inconsistent bounds/ratios: intersected range is "
                f"[{lo}, {hi}]. Check the given factors against each "
                "member's actual bounds.")

        rep = m_fva.reactions.get_by_id(rep_id)
        rep.subtract_metabolites(dict(rep.metabolites))
        rep.add_metabolites({m_fva.metabolites.get_by_id(mid): coeff
                              for mid, coeff in combined.items() if coeff != 0.0})
        rep.bounds = (lo, hi)

        other_members = [m_fva.reactions.get_by_id(mid) for mid, _ in members if mid != rep_id]
        m_fva.remove_reactions(other_members)

    rewritten: List[ConstraintTriple] = []
    for expr, ctype, rhs in scenario_triples:
        new_expr: Dict[str, float] = {}
        for rid, coeff in expr.items():
            rep_id, ratio = subset_ratio.get(rid, (rid, 1.0))
            new_expr[rep_id] = new_expr.get(rep_id, 0.0) + coeff * ratio
        new_expr = {k: v for k, v in new_expr.items() if v != 0.0}
        rewritten.append((new_expr, ctype, rhs))

    return m_fva, rewritten


# ---------------------------------------------------------------------------
# thermodynamic bottleneck search (deletion filter)
# ---------------------------------------------------------------------------

def _find_minimal_bottleneck(
    solver,
    df_constraints: Dict[str, Dict[str, Any]],
    fluxes: Dict[str, float],
    driving_forces: Dict[str, float],
    mdf: float,
    tol: float = 1e-6,
) -> List[str]:
    """
    Deletion-filter search for a minimal thermodynamic bottleneck set: a
    smallest set of reactions such that relaxing exactly their
    driving-force constraints (removing the requirement df_r >= mdf
    entirely, as if that reaction's own thermodynamics didn't matter)
    allows mdf to improve, and no proper subset of the set suffices. This
    is the LP analogue of finding an Irreducible Infeasible Subsystem, just
    for an optimality bound instead of infeasibility.

    Must be called with `solver` already solved as a fixed-binary LP at its
    optimum (see optMDFpathway) -- duals/constraint-removal comparisons
    aren't meaningful while the solver could still restructure which
    reactions are active.

    Only reactions tied exactly at the current mdf (df_r <= mdf + tol) are
    ever candidates: anything with real slack (df_r > mdf) cannot be part
    of any minimal bottleneck, since its constraint isn't currently
    limiting anything. A reaction with a nonzero shadow-price dual is not
    on its own a reliable indicator here -- with redundant/parallel tied
    reactions (e.g. isozymes), LP duality can attribute all the "credit" to
    an arbitrary one of them, but relaxing that one alone may do nothing;
    only an explicit relax-and-resolve check like this one can confirm
    which reactions truly are (jointly) necessary.

    Uses |tied| + 2 LP re-solves: one to confirm relaxing every tied
    reaction at once even helps at all (if not, mdf isn't limited by
    thermodynamics here -- e.g. it's capped by B_bounds or a scenario
    constraint instead, and an empty list is returned), then one per
    candidate to test whether it can be dropped from the relaxed set while
    the improvement persists.

    Every constraint's bound is restored to its original value before
    returning (whether or not it ended up in the reported set), leaving
    `solver` back at the original optimum.
    """
    def active_constraint(rid: str):
        direction = "fwd" if fluxes[rid] >= 0 else "rev"
        return df_constraints.get(rid, {}).get(direction)

    tied_cons = {
        rid: active_constraint(rid)
        for rid, df in driving_forces.items() if df <= mdf + tol
    }
    print(tied_cons)
    tied_cons = {rid: con for rid, con in tied_cons.items() if con is not None}
    if not tied_cons:
        return []

    orig_lb = {rid: con.lb for rid, con in tied_cons.items()}

    def relax(rids):
        for rid in rids:
            tied_cons[rid].lb = -1e9

    def restore(rids):
        for rid in rids:
            tied_cons[rid].lb = orig_lb[rid]

    def improves() -> bool:
        status = solver.optimize()
        return status == "optimal" and solver.objective.value > mdf + tol

    # Step 1: relax every tied reaction at once -- confirm an improvement is
    # even achievable before searching for a minimal subset of it.
    relax(tied_cons)
    if not improves():
        restore(tied_cons)
        solver.optimize()
        return []

    # Step 2: deletion filter. Try re-enforcing each candidate in turn; if
    # the (still-partly-relaxed) set keeps improving without it, it wasn't
    # needed -- leave it re-enforced permanently. Otherwise it's necessary
    # -- relax it again before moving on.
    necessary = set(tied_cons)
    for rid, con in tied_cons.items():
        con.lb = orig_lb[rid]
        if improves():
            necessary.discard(rid)
        else:
            con.lb = -1e9

    restore(tied_cons)
    solver.optimize()  # leave the solver back at the original optimum
    return sorted(necessary)


# ---------------------------------------------------------------------------
# OptMDFAnalysis: stateful solver for (iterative) OptMDFpathway
# ---------------------------------------------------------------------------

class OptMDFAnalysis:
    """
    Stateful OptMDFpathway solver, for cases where you want to solve more
    than once against the same model/constraints -- most importantly,
    iterative thermodynamic-bottleneck analysis: solve, find the current
    minimal bottleneck, permanently relax exactly its driving-force
    constraint(s), and repeat.

    Building the model copy, running FVA preprocessing, and constructing
    every constraint of the MILP is done exactly once, in __init__ (see
    optMDFpathway for what all of this means -- the modelling is identical;
    this class only changes *when* work happens, not what is computed).
    Repeated calls to solve() just re-optimize the same solver object;
    finding a bottleneck and relaxing it only ever touches the specific
    driving-force constraint(s) involved, never rebuilding anything.

    Typical usage, an unbounded number of iterations decided as you go:

        analysis = OptMDFAnalysis(model, scenarios=[...])
        for result, bottleneck in analysis.run():
            print(result.mdf, bottleneck)
            if result.mdf >= target or not bottleneck:
                break

    or with manual control over each step:

        analysis = OptMDFAnalysis(model, scenarios=[...])
        result = analysis.solve()
        while True:
            bottleneck = analysis.find_bottleneck()
            if not bottleneck:
                break                       # mdf is no longer thermodynamically limited
            analysis.relax(bottleneck)
            result = analysis.solve()

    optMDFpathway(...) is a thin one-shot wrapper around this class, for
    callers that just want a single solve (optionally with shadow prices
    and/or one bottleneck set) without managing the object themselves.
    """

    def __init__(
        self,
        model: cobra.Model,
        Cmin: Union[Number, Dict[str, Number]] = 1e-6,
        Cmax: Union[Number, Dict[str, Number]] = 1e-2,
        RT: float = 8.314e-3 * 298.15,
        scenarios: Optional[Union[ScenarioConstraint, Iterable[ScenarioConstraint]]] = None,
        concentration_ratios: Optional[Sequence[Sequence[Any]]] = None,
        reaction_subsets: Optional[Sequence[Sequence[Tuple[str, Number]]]] = None,
        ignore_reactions: Optional[Iterable[str]] = None,
        flux_bound_M: Optional[Number] = None,
        dG_bound_M: Number = 1e4,
        B_bounds: Tuple[Number, Number] = (-1e4, 1e4),
        use_fva_preprocessing: Optional[bool] = None,
        blocked_flux_tol: float = 1e-9,
        bottleneck_tol: float = 1e-6,
        verbose: bool = False,
    ):
        """
        Build the model copy, run FVA preprocessing, and construct the full
        MILP -- everything solve() will need, done exactly once here.

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
            Default concentration bounds in M (mol/L), used for any
            metabolite that doesn't carry annotation['Cmin']/['Cmax']. A
            scalar applies the same bound to every such metabolite; a dict
            may supply per-metabolite defaults.
        RT : float
            Gas constant * temperature, in energy units matching dG0
            (default: RT at 25 deg C in kJ/mol).
        scenarios : optional scenario constraint(s)
            Additional linear constraints over reaction fluxes -- e.g. a
            fixed uptake rate, a fixed growth rate, or a minimal yield
            requirement. Each entry may be a raw
            ({reaction_id: coefficient}, constraint_type, rhs) triple with
            constraint_type in {'=', '<=', '>='}, or a Scenario-like
            reaction_id -> (lb, ub) mapping (core.make_scenario_feasible /
            element_exchange_balance's shape; any reactions it needs are
            added via .add_scenario_reactions_to_model if present). See
            scenario_constraints_to_triples for full details. Used both as
            the FVA preprocessing step's ``constraints`` argument and as
            ordinary linear constraints added to the MILP.
        concentration_ratios : optional list of tuples
            Constrains concentration_i / concentration_j for pairs of
            metabolites, e.g. to couple cofactor pairs such as ATP/ADP.
            Each entry is (met_i, met_j, ratio) for a fixed ratio, or
            (met_i, met_j, ratio_min, ratio_max) for a range.
        reaction_subsets : optional list of lists of (reaction_id, factor)
            Strictly (fully) flux-coupled reaction groups -- e.g. from flux
            coupling analysis -- where flux(reaction_id) == (factor /
            factor_of_first_entry) * flux(first entry's reaction_id) holds
            in every feasible steady state. Speeds up both FVA
            preprocessing (run on a compressed model, one reaction per
            group -- see _compress_for_fva) and the MILP (one pair of
            binaries and one flux-linking constraint per group instead of
            per reaction; each member's own driving-force constraint is
            still built individually since thermodynamics can't be
            shared). Each reaction may appear in at most one subset.
        ignore_reactions : optional iterable of reaction ids
            Reactions to exclude from driving-force constraints even if
            they carry a dG0 annotation.
        flux_bound_M : optional float
            Upper cap on the big-M used to link flux to its binary
            "reaction is active" indicator; see optMDFpathway.
        dG_bound_M : float
            Big-M used to relax the driving-force constraint when a
            reaction's indicator is 0; see optMDFpathway.
        B_bounds : (float, float)
            Lower/upper bound for the MDF variable itself.
        use_fva_preprocessing : optional bool
            None (default): try FVA, fall back to static bounds if
            core.py's dependencies aren't importable. True: require it.
            False: always use static bounds. See optMDFpathway.
        blocked_flux_tol : float
            Absolute flux tolerance below which an FVA-computed bound is
            treated as zero (that direction is blocked).
        bottleneck_tol : float
            Absolute driving-force tolerance used by find_bottleneck() to
            decide whether a reaction is "tied" at mdf and whether relaxing
            a candidate set counts as an improvement.
        verbose : bool
            Print setup information now, and progress information from
            solve()/find_bottleneck()/relax() later.
        """
        m = model.copy()
        solver = m.solver
        if verbose:
            m.problem.verbosity = 1
        # Use the solver-specific optlang classes (m.problem), not the generic
        # optlang.interface ones -- optlang models refuse to add variables /
        # constraints built from a different interface than their own backend.
        Variable, Constraint, Objective = m.problem.Variable, m.problem.Constraint, m.problem.Objective

        # Capture the model's own objective (e.g. biomass) before it gets
        # overwritten below with "maximize B" -- solve_fba() uses this.
        native_objective_coeffs = {
            rxn.id: rxn.objective_coefficient for rxn in m.reactions
            if rxn.objective_coefficient != 0
        }
        native_objective_direction = m.objective_direction

        # -- 0) normalize scenario constraints into (expression, type, rhs)
        #    triples -- any reactions a Scenario-like entry needs are added to
        #    `m` here (via .add_scenario_reactions_to_model), so this must
        #    happen before anything below reads m.reactions / m.metabolites.
        scenario_triples = scenario_constraints_to_triples(scenarios, m)
        subset_ratio = _normalize_reaction_subsets(reaction_subsets)

        Cmin_d, Cmax_d = _resolve_concentration_bounds(m, Cmin, Cmax)
        ignore = set(ignore_reactions or [])
        ratio_specs = _normalize_concentration_ratios(concentration_ratios)

        # -- FVA preprocessing: compute the tightest achievable per-reaction
        #    flux range given the whole network + scenario constraints, for use
        #    as a tight big-M and to prune structurally blocked reactions. If
        #    reaction_subsets were given, this runs on a compressed model (see
        #    _compress_for_fva) and the result is expanded back afterwards.
        fva_bounds: Optional[Dict[str, Tuple[float, float]]] = None
        if use_fva_preprocessing is not False:
            m_fva, fva_triples = _compress_for_fva(m, subset_ratio, scenario_triples)
            fva_lb, fva_ub, n_bad = multi_threaded_HiGHS_FVA(m_fva, constraints=fva_triples)
            fva_bounds_compressed = {rxn.id: (lo, hi) for rxn, lo, hi in zip(m_fva.reactions, fva_lb, fva_ub)}
            # Expand back to every reaction of the (uncompressed) `m`: a
            # representative (or any reaction outside reaction_subsets)
            # reads its bound directly; a subset member derives it from its
            # representative's bound scaled by their ratio.
            fva_bounds = {}
            for rxn in m.reactions:
                rep_id, ratio = subset_ratio.get(rxn.id, (rxn.id, 1.0))
                lo_rep, hi_rep = fva_bounds_compressed[rep_id]
                if math.isnan(lo_rep) or math.isnan(hi_rep):
                    fva_bounds[rxn.id] = (lo_rep, hi_rep)
                elif ratio > 0:
                    fva_bounds[rxn.id] = (ratio * lo_rep, ratio * hi_rep)
                else:
                    fva_bounds[rxn.id] = (ratio * hi_rep, ratio * lo_rep)
            if verbose:
                msg = (f"FVA preprocessing done "
                        f"({n_bad} reaction(s) had solver trouble)" if n_bad
                        else "FVA preprocessing done.")
                if m_fva is not m:
                    msg += (f" [{len(m.reactions)} reactions compressed to "
                            f"{len(m_fva.reactions)} via reaction_subsets]")
                print(msg)

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

        # -- 3) per-subset driving-force machinery -------------------------------
        # Reactions are grouped by representative (every reaction not covered by
        # reaction_subsets is its own singleton group, ratio 1.0), so that
        # strictly-coupled reactions share one pair of "group active
        # forward/reverse" binaries and one flux/indicator-linking constraint
        # (on the representative only) instead of paying for that per reaction.
        # Each member with its own dG0 annotation still gets its own
        # driving-force constraint -- thermodynamics is inherently per-reaction
        # and can't be shared -- gated by the group's shared binaries, sign-
        # flipped for members whose ratio to the representative is negative
        # (they then run opposite it).
        #
        # Fallback big-M for when FVA preprocessing isn't available: the
        # largest finite static reaction bound in the model (or 1000).
        static_default_M = flux_bound_M
        if static_default_M is None:
            finite_bounds = [abs(b) for r in m.reactions
                              for b in (r.lower_bound, r.upper_bound)
                              if math.isfinite(b) and b != 0]
            static_default_M = max(finite_bounds) if finite_bounds else 1000.0

        groups: Dict[str, List[Tuple[cobra.Reaction, float]]] = {}
        for rxn in m.reactions:
            rep_id, ratio = subset_ratio.get(rxn.id, (rxn.id, 1.0))
            groups.setdefault(rep_id, []).append((rxn, ratio))

        stoich: Dict[str, Dict[str, float]] = {}   # rxn.id -> {met.id: coeff}
        G0_eff: Dict[str, float] = {}              # rxn.id -> worst-case delta_r G0
        df_constraints: Dict[str, Dict[str, Constraint]] = {}  # rxn.id -> {"fwd"/"rev": constraint}

        new_bin_vars: List[Variable] = []
        n_fwd = n_rev = n_blocked = n_no_dG0 = 0

        for rep_id, members in groups.items():
            rep_rxn = m.reactions.get_by_id(rep_id)

            # Which (non-ignored) members actually need a driving-force
            # constraint? Skip the whole group's binaries/linking if none do.
            active_members: List[Tuple[cobra.Reaction, float, float, float]] = []
            for member_rxn, ratio in members:
                if member_rxn.id in ignore:
                    continue
                dG0 = _reaction_dG0(member_rxn)
                if dG0 is None:
                    n_no_dG0 += 1
                    continue
                if not member_rxn.metabolites:
                    continue
                val, unc = dG0
                active_members.append((member_rxn, ratio, val, unc))
            if not active_members:
                continue

            # Representative's achievable flux range: the FVA-tightened one
            # when available (falling back to the static bounds if FVA had
            # solver trouble), otherwise the static bounds.
            if fva_bounds is not None:
                fva_lo, fva_hi = fva_bounds[rep_id]
                if math.isnan(fva_lo) or math.isnan(fva_hi):
                    fva_lo, fva_hi = rep_rxn.lower_bound, rep_rxn.upper_bound
            else:
                fva_lo, fva_hi = rep_rxn.lower_bound, rep_rxn.upper_bound

            can_fwd = fva_hi > blocked_flux_tol
            can_rev = fva_lo < -blocked_flux_tol
            if not can_fwd and not can_rev:
                # Structurally blocked under the current network/constraints --
                # nothing in this group can ever be "used", so none of its
                # members need an MDF constraint or binary at all.
                n_blocked += len(active_members)
                continue

            z_fwd = z_rev = None
            if can_fwd:
                M_r = fva_hi if flux_bound_M is None else min(flux_bound_M, fva_hi)
                z_fwd = Variable(f"z_fwd_{rep_id}", type="binary")
                new_bin_vars.append(z_fwd)
                all_cons.append(Constraint(Zero, ub=0, name=f"link_fwd_{rep_id}"))
                all_coeffs.append({rep_rxn.forward_variable: 1.0, z_fwd: -M_r})
            if can_rev:
                M_r = abs(fva_lo) if flux_bound_M is None else min(flux_bound_M, abs(fva_lo))
                z_rev = Variable(f"z_rev_{rep_id}", type="binary")
                new_bin_vars.append(z_rev)
                all_cons.append(Constraint(Zero, ub=0, name=f"link_rev_{rep_id}"))
                all_coeffs.append({rep_rxn.reverse_variable: 1.0, z_rev: -M_r})

            for member_rxn, ratio, val, unc in active_members:
                met_coeffs = {met.id: coeff for met, coeff in member_rxn.metabolites.items()}
                stoich[member_rxn.id] = met_coeffs
                # conservative (worst-case) standard Gibbs energy: adding the
                # uncertainty guarantees df_fwd >= B for every value the true
                # dG0 could take in [val - unc, val + unc].
                G0_eff[member_rxn.id] = val + unc

                if member_rxn.id != rep_id:
                    # Safety net: strict coupling means the network's own mass
                    # balance already implies flux(member) == ratio*flux(rep)
                    # in every feasible flux vector, so this is mathematically
                    # redundant -- but pinning it down explicitly and cheaply
                    # (a linear equality, not a binary) makes the shared-binary
                    # sharing above correct by construction rather than by
                    # trusting reaction_subsets to exactly match the model.
                    all_cons.append(Constraint(
                        Zero, lb=0, ub=0, name=f"couple_{member_rxn.id}_{rep_id}"))
                    all_coeffs.append({
                        member_rxn.forward_variable: 1.0, member_rxn.reverse_variable: -1.0,
                        rep_rxn.forward_variable: -ratio, rep_rxn.reverse_variable: ratio,
                    })

                # A positive ratio means the member runs forward exactly when
                # the representative does (and reverse exactly when it does);
                # a negative ratio flips that correspondence.
                fwd_indicator = z_fwd if ratio > 0 else z_rev
                rev_indicator = z_rev if ratio > 0 else z_fwd

                # driving force if the reaction runs forward:
                #   df_fwd = -G0_eff - RT * sum_m S[m] * logc[m]
                # Constraint enforced only when the indicator = 1 (df_fwd >= B):
                #   -RT*sum(S[m]*logc[m]) - B - dG_bound_M*z  >=  G0_eff - dG_bound_M
                # (the constant G0_eff is folded straight into the constraint's
                # lower bound, since set_linear_coefficients only ever sets
                # *variable* coefficients, never a constant offset)
                if fwd_indicator is not None:
                    df_coeffs = {logc[mid]: -RT * coeff for mid, coeff in met_coeffs.items()}
                    df_coeffs[B] = -1.0
                    df_coeffs[fwd_indicator] = -dG_bound_M
                    df_fwd_con = Constraint(
                        Zero, lb=G0_eff[member_rxn.id] - dG_bound_M, name=f"df_fwd_{member_rxn.id}")
                    all_cons.append(df_fwd_con)
                    all_coeffs.append(df_coeffs)
                    df_constraints.setdefault(member_rxn.id, {})["fwd"] = df_fwd_con
                    n_fwd += 1

                # running in reverse negates the effective stoichiometry, so
                # the reverse driving force is simply -df_fwd:
                #   RT*sum(S[m]*logc[m]) - B - dG_bound_M*z  >=  -G0_eff - dG_bound_M
                if rev_indicator is not None:
                    df_coeffs = {logc[mid]: RT * coeff for mid, coeff in met_coeffs.items()}
                    df_coeffs[B] = -1.0
                    df_coeffs[rev_indicator] = -dG_bound_M
                    df_rev_con = Constraint(
                        Zero, lb=-G0_eff[member_rxn.id] - dG_bound_M, name=f"df_rev_{member_rxn.id}")
                    all_cons.append(df_rev_con)
                    all_coeffs.append(df_coeffs)
                    df_constraints.setdefault(member_rxn.id, {})["rev"] = df_rev_con
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
            n_groups_used = len({subset_ratio.get(rid, (rid, 1.0))[0] for rid in stoich})
            subset_note = (f", sharing {n_groups_used} group(s)' binaries via "
                            "reaction_subsets" if subset_ratio else "")
            print(f"OptMDFpathway: {len(stoich)} reactions with dG0 annotations "
                  f"({n_fwd} forward + {n_rev} reverse directions, "
                  f"{n_blocked} blocked & skipped, {n_no_dG0} without a dG0 "
                  f"annotation), {len(new_bin_vars)} binaries" + subset_note +
                  ("" if fva_bounds is not None else
                   f", default big-M = {static_default_M:g}"))

        # -- everything solve()/shadow_prices()/find_bottleneck()/relax()
        #    need going forward, preserved for reuse across iterations. ----
        self.model = m
        self.solver = solver
        self.RT = RT
        self.logc = logc
        self.B = B
        self.stoich = stoich
        self.G0_eff = G0_eff
        self.df_constraints = df_constraints
        self.bin_vars = new_bin_vars
        self._bin_var_bounds = {z: (z.lb, z.ub) for z in new_bin_vars}
        self.subset_ratio = subset_ratio
        self.bottleneck_tol = bottleneck_tol
        self.verbose = verbose
        self._native_objective_coeffs = native_objective_coeffs
        self._native_objective_direction = native_objective_direction

        #: One OptMDFResult per solve() call, in order.
        self.history: List[OptMDFResult] = []
        #: One bottleneck-set-that-was-relaxed per relax() call, in order
        #: (mirrors self.history when driven via step()/run()).
        self.relaxed_log: List[List[str]] = []
        #: Reaction ids whose driving-force constraint(s) have been
        #: permanently relaxed via relax() so far.
        self._relaxed: Set[str] = set()

    # -- internal: temporarily solve as a pure LP with every binary fixed --
    @contextlib.contextmanager
    def _fixed_binary_lp(self) -> Iterator[Optional[str]]:
        """
        Context manager: fix every binary at its currently-solved value
        (rounded to 0/1) and switch it to continuous, re-solve (so duals
        and constraint-removal comparisons are meaningful -- see
        optMDFpathway's compute_shadow_prices docstring for why), yield the
        resulting status, then always restore every binary to its original
        (type='binary', bounds=[0, 1]) state and re-solve again before
        returning control -- so the model is back in proper MILP form for
        the next solve()/find_bottleneck() call regardless of what the
        caller did in between, even if it raised an exception.
        """
        if not self.bin_vars:
            yield self.history[-1].status if self.history else None
            return
        for z in self.bin_vars:
            z_val = round(z.primal)
            z.type = "continuous"
            z.lb = z.ub = z_val
        status = self.solver.optimize()
        try:
            yield status
        finally:
            for z in self.bin_vars:
                lb, ub = self._bin_var_bounds[z]
                z.lb, z.ub = lb, ub
                z.type = "binary"
            self.solver.optimize()

    # -- public API -----------------------------------------------------------

    def _extract_result(self, status: str) -> OptMDFResult:
        """Build an OptMDFResult from the solver's current (just-solved)
        state. Shared by solve() and solve_fba() -- everything except
        .mdf and .objective_value is identical between them."""
        result = OptMDFResult(status=status)
        if status != "optimal":
            return result
        for rxn in self.model.reactions:
            result.fluxes[rxn.id] = rxn.flux
        for mid, v in self.logc.items():
            result.concentrations[mid] = math.exp(v.primal)
        for rid, coeffs in self.stoich.items():
            dG_fwd = self.G0_eff[rid] + self.RT * sum(
                coeff * math.log(result.concentrations[mid])
                for mid, coeff in coeffs.items())
            df_fwd = -dG_fwd
            # Report the driving force of the direction the reaction
            # actually ran in this solution (df_fwd if flux >= 0, else
            # -df_fwd, i.e. the reverse driving force): a reaction running
            # in reverse can have a very negative df_fwd (that's *why* it
            # runs in reverse) even though the direction it actually took
            # satisfies df >= mdf.
            result.driving_forces[rid] = df_fwd if result.fluxes[rid] >= 0 else -df_fwd
        return result

    def solve(self) -> OptMDFResult:
        """
        Solve the MILP as it currently stands (including any driving-force
        constraints previously relaxed via relax()) and return an
        OptMDFResult, exactly as optMDFpathway does. Appended to
        self.history.
        """
        start_time = time.monotonic()
        status = self.solver.optimize()
        print(time.monotonic() - start_time)
        result = self._extract_result(status)
        if status != "optimal":
            if self.verbose:
                print(f"Solve finished with status: {status}")
            self.history.append(result)
            return result

        result.mdf = self.B.primal
        if self.verbose:
            print(f"MDF = {result.mdf:.4g} (same energy units as dG0/RT)")
        self.history.append(result)
        return result

    @contextlib.contextmanager
    def _temporary_objective(self, coeffs: Dict[Any, float], direction: str) -> Iterator[None]:
        """Swap in a different objective (built from {variable: coefficient}
        pairs) for the duration of the block, then always restore "maximize
        B" -- this class's normal, permanent objective -- afterwards."""
        Objective = self.model.problem.Objective
        self.solver.objective = Objective(Zero, direction=direction)
        self.solver.update()
        self.solver.objective.set_linear_coefficients(coeffs)
        try:
            yield
        finally:
            self.solver.objective = Objective(Zero, direction="max")
            self.solver.update()
            self.solver.objective.set_linear_coefficients({self.B: 1.0})

    def solve_fba(
        self,
        objective: Optional[Dict[str, Number]] = None,
        direction: Optional[str] = None,
    ) -> OptMDFResult:
        """
        Thermodynamically-constrained FBA: instead of maximising the MDF
        itself, optimise the model's own objective (e.g. biomass) subject
        to every constraint already in the MILP -- including B's own
        bounds, so B_bounds[0] (set when constructing this analysis) acts
        as a required minimum MDF for whichever flux distribution is
        found. Everything else (scenarios, concentration_ratios,
        reaction_subsets, any reactions already relax()ed) applies exactly
        as in solve(). If B_bounds[0] is set higher than any flux
        distribution can actually achieve, this is simply infeasible --
        same as any other over-constrained MILP.

        Parameters
        ----------
        objective : optional dict {reaction_id: coefficient}
            Defaults to the model's own objective (read from
            reaction.objective_coefficient when this analysis was
            constructed). Supply this to optimise something else instead
            (e.g. a different reaction, or a linear combination).
        direction : optional 'max' or 'min'
            Defaults to the model's own objective_direction. Only used
            together with an explicit ``objective``.

        Returns
        -------
        OptMDFResult
            Same fields as solve(), plus .objective_value: the optimised
            objective's value (e.g. the growth rate). .mdf is B's value at
            this solution (>= B_bounds[0] by construction).
        """
        coeffs = objective if objective is not None else self._native_objective_coeffs
        obj_direction = direction if direction is not None else self._native_objective_direction
        if not coeffs:
            raise ValueError(
                "No objective to optimise: the model has no objective set "
                "(and none was given). Set model.objective before "
                "constructing OptMDFAnalysis, or pass objective= explicitly."
            )
        var_coeffs: Dict[Any, float] = {}
        for rid, coeff in coeffs.items():
            rxn = self.model.reactions.get_by_id(rid)
            var_coeffs[rxn.forward_variable] = var_coeffs.get(rxn.forward_variable, 0.0) + coeff
            var_coeffs[rxn.reverse_variable] = var_coeffs.get(rxn.reverse_variable, 0.0) - coeff

        with self._temporary_objective(var_coeffs, obj_direction):
            status = self.solver.optimize()
            result = self._extract_result(status)
            if status == "optimal":
                result.mdf = self.B.primal
                result.objective_value = self.solver.objective.value
                if self.verbose:
                    print(f"Thermodynamic FBA: objective = {result.objective_value:.6g}, "
                          f"mdf = {result.mdf:.4g} (>= B_bounds[0])")
            elif self.verbose:
                print(f"Thermodynamic FBA finished with status: {status}")
        self.history.append(result)
        return result

    def shadow_prices(self) -> Dict[str, float]:
        """
        Shadow prices d(mdf)/d(dG0_r) of every reaction's driving-force
        constraint, for the most recent solve() result: how much the MDF
        would improve per unit its dG0 were relaxed. Nonzero only for
        reactions whose constraint is exactly binding (df_r == mdf) in that
        solution -- see optMDFpathway's compute_shadow_prices docstring for
        the full explanation (including its caveat: with redundant/tied
        reactions, e.g. isozymes, a nonzero dual on one of them doesn't
        necessarily mean relaxing *that one alone* would help -- use
        find_bottleneck() to confirm which reactions are actually, jointly,
        necessary).

        Requires a prior solve() with status "optimal"; raises RuntimeError
        otherwise.
        """
        if not self.history or self.history[-1].status != "optimal":
            raise RuntimeError("shadow_prices() requires a prior solve() "
                                "that returned status 'optimal'.")
        result = self.history[-1]
        duals: Dict[str, float] = {}
        with self._fixed_binary_lp() as lp_status:
            if lp_status == "optimal":
                if self.verbose and abs(self.B.primal - result.mdf) > 1e-6:
                    print(f"Note: shadow-price LP resolve landed on "
                          f"mdf={self.B.primal:.6g}, slightly different "
                          f"from the original {result.mdf:.6g} (likely "
                          "solution degeneracy); duals are still valid for "
                          "the LP that was actually solved.")
                for rid in self.stoich:
                    direction = "fwd" if result.fluxes[rid] >= 0 else "rev"
                    con = self.df_constraints.get(rid, {}).get(direction)
                    if con is not None:
                        duals[rid] = con.dual
            elif self.verbose:
                print(f"Shadow-price LP resolve finished with status "
                      f"{lp_status!r} (expected 'optimal'); skipping shadow prices.")
        return duals

    def find_bottleneck(self) -> List[str]:
        """
        A minimal thermodynamic bottleneck set for the most recent solve()
        result -- see _find_minimal_bottleneck for the algorithm (a
        deletion-filter search: relax every reaction currently tied at mdf
        at once to confirm improvement is possible, then re-enforce each
        one at a time, keeping it re-enforced whenever the rest still
        improve without it). An empty list means mdf isn't currently
        limited by any reaction's thermodynamics (e.g. it's capped by
        B_bounds or a scenario constraint instead), or -- after enough
        relax() calls -- that nothing thermodynamically limiting remains.

        Reactions already relaxed by a previous relax() call are excluded
        from consideration (their constraint is already permanently
        non-binding, so they can never be part of a *new* bottleneck).

        Uses the same fixed-binary LP as shadow_prices() (a handful of
        extra re-solves, restored afterwards either way); requires a prior
        solve() with status "optimal".
        """
        if not self.history or self.history[-1].status != "optimal":
            raise RuntimeError("find_bottleneck() requires a prior solve() "
                                "that returned status 'optimal'.")
        result = self.history[-1]
        driving_forces = {rid: df for rid, df in result.driving_forces.items()
                           if rid not in self._relaxed}
        with self._fixed_binary_lp() as lp_status:
            if lp_status != "optimal":
                if self.verbose:
                    print(f"Bottleneck-search LP resolve finished with status "
                          f"{lp_status!r} (expected 'optimal'); skipping.")
                return []
            start_time = time.monotonic()
            bottleneck = _find_minimal_bottleneck(
                self.solver, self.df_constraints, result.fluxes,
                driving_forces, result.mdf, tol=self.bottleneck_tol)
            print(time.monotonic() - start_time)
        if self.verbose:
            print(f"Bottleneck: {bottleneck}" if bottleneck else
                  "No thermodynamic bottleneck (mdf isn't limited by any "
                  "reaction's driving force here).")
        return bottleneck

    def relax(self, reactions: Iterable[str]) -> None:
        """
        Permanently relax (exempt from df_r >= mdf entirely) the
        driving-force constraint(s) of the given reactions, so every future
        solve() no longer enforces them. Idempotent -- reactions already
        relaxed, or without a driving-force constraint at all (e.g. no
        dG0 annotation), are silently skipped and not recorded in
        relaxed_log. Their driving force is still computed and reported by
        solve() (it's simply no longer constrained), and they're
        automatically excluded from future find_bottleneck() candidate
        sets.
        """
        actually_relaxed = []
        for rid in reactions:
            cons = self.df_constraints.get(rid)
            if not cons:
                continue
            for con in cons.values():
                con.lb = -1e9
            self._relaxed.add(rid)
            actually_relaxed.append(rid)
        if actually_relaxed:
            self.relaxed_log.append(actually_relaxed)
            if self.verbose:
                print(f"Relaxed: {actually_relaxed}")

    def step(self) -> Tuple[OptMDFResult, List[str]]:
        """
        One iteration of the bottleneck-relaxation loop: solve(), find the
        bottleneck for that result, relax() it (if non-empty), and return
        (result, bottleneck). An empty bottleneck means mdf is no longer
        thermodynamically limited -- further calls won't improve it.
        """
        result = self.solve()
        if result.status != "optimal":
            return result, []
        bottleneck = self.find_bottleneck()
        if bottleneck:
            self.relax(bottleneck)
        return result, bottleneck

    def run(self, max_iterations: Optional[int] = None) -> Iterator[Tuple[OptMDFResult, List[str]]]:
        """
        Generator: repeatedly call step(), yielding (result, bottleneck)
        each time, until either the bottleneck comes back empty (mdf is no
        longer thermodynamically limited, or the solve failed) or
        max_iterations have been yielded. Since it's a generator, the
        caller decides how many iterations to actually consume -- e.g.

            for result, bottleneck in analysis.run():
                print(result.mdf, bottleneck)
                if result.mdf >= target:
                    break
        """
        n = 0
        while max_iterations is None or n < max_iterations:
            result, bottleneck = self.step()
            yield result, bottleneck
            n += 1
            if result.status != "optimal" or not bottleneck:
                return


# ---------------------------------------------------------------------------
# optMDFpathway: one-shot convenience wrapper around OptMDFAnalysis
# ---------------------------------------------------------------------------

def optMDFpathway(
    model: cobra.Model,
    Cmin: Union[Number, Dict[str, Number]] = 1e-6,
    Cmax: Union[Number, Dict[str, Number]] = 1e-2,
    RT: float = 8.314e-3 * 298.15,
    scenarios: Optional[Union[ScenarioConstraint, Iterable[ScenarioConstraint]]] = None,
    concentration_ratios: Optional[Sequence[Sequence[Any]]] = None,
    reaction_subsets: Optional[Sequence[Sequence[Tuple[str, Number]]]] = None,
    ignore_reactions: Optional[Iterable[str]] = None,
    flux_bound_M: Optional[Number] = None,
    dG_bound_M: Number = 1e4,
    B_bounds: Tuple[Number, Number] = (-1e4, 1e4),
    use_fva_preprocessing: Optional[bool] = None,
    blocked_flux_tol: float = 1e-9,
    bottleneck_tol: float = 1e-6,
    compute_shadow_prices: bool = False,
    find_minimal_bottleneck: bool = False,
    verbose: bool = False,
) -> OptMDFResult:
    """
    Compute a single OptMDFpathway solution: the flux distribution and
    metabolite concentration profile that jointly maximise the max-min
    driving force. A thin one-shot wrapper around OptMDFAnalysis(model,
    ...).solve() -- see that class's docstring (and its __init__'s, for the
    full parameter reference) for the underlying model and for iterative
    use (solving more than once against the same model/constraints, most
    importantly repeated bottleneck-relaxation analysis, without paying to
    rebuild the model/FVA/MILP on every call).

    Parameters not listed below (Cmin, Cmax, RT, scenarios,
    concentration_ratios, reaction_subsets, ignore_reactions, flux_bound_M,
    dG_bound_M, B_bounds, use_fva_preprocessing, blocked_flux_tol) are
    exactly OptMDFAnalysis.__init__'s.

    bottleneck_tol : float
        Only relevant when find_minimal_bottleneck=True; see
        OptMDFAnalysis.__init__.
    compute_shadow_prices : bool
        If True, also compute OptMDFAnalysis.shadow_prices() and attach it
        as result.driving_force_duals: d(mdf)/d(dG0_r) for every reaction,
        nonzero only where the driving-force constraint is exactly binding.
        See OptMDFAnalysis.shadow_prices's docstring for the important
        caveat about redundant/tied reactions.
    find_minimal_bottleneck : bool
        If True, also compute OptMDFAnalysis.find_bottleneck() and attach
        it as result.bottleneck_reactions: a minimal set of reactions whose
        driving-force constraints, relaxed together, would allow mdf to
        improve (empty if mdf isn't thermodynamically limited here).
    verbose : bool
        Print setup and solve information.

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
        .driving_force_duals  {reaction_id: d(mdf)/d(dG0_r)}, only if
                               compute_shadow_prices=True
        .bottleneck_reactions minimal bottleneck set, only if
                               find_minimal_bottleneck=True
    """
    analysis = OptMDFAnalysis(
        model, Cmin=Cmin, Cmax=Cmax, RT=RT, scenarios=scenarios,
        concentration_ratios=concentration_ratios, reaction_subsets=reaction_subsets,
        ignore_reactions=ignore_reactions, flux_bound_M=flux_bound_M,
        dG_bound_M=dG_bound_M, B_bounds=B_bounds,
        use_fva_preprocessing=use_fva_preprocessing,
        blocked_flux_tol=blocked_flux_tol, bottleneck_tol=bottleneck_tol,
        verbose=verbose,
    )
    result = analysis.solve()
    if result.status == "optimal":
        if compute_shadow_prices:
            result.driving_force_duals = analysis.shadow_prices()
        if find_minimal_bottleneck:
            result.bottleneck_reactions = analysis.find_bottleneck()
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
    from optlang import highs_interface
    cobra.Configuration.solver = highs_interface
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

    print("\nSame toy pathway, but telling optMDFpathway that R1 and R2 are "
          "strictly (1:1) flux-coupled -- true here since B has no other "
          "source or sink. This collapses their 2 binaries down to 1 and "
          "gives the identical MDF:")
    result_subset = optMDFpathway(
        toy,
        Cmin=1e-6,
        Cmax=1e-2,
        scenarios=[scenario, yield_constraint],
        reaction_subsets=[[("R1", 1.0), ("R2", 1.0)]],
        verbose=True,
    )
    print(result_subset)

    print("\nThermodynamic bottleneck analysis (shadow prices of the "
          "driving-force constraints): which reaction is actually limiting "
          "the MDF, and how much would relaxing its dG0 help?")
    result_dual = optMDFpathway(
        toy, Cmin=1e-6, Cmax=1e-2, scenarios=[scenario],
        compute_shadow_prices=True, find_minimal_bottleneck=True,
        use_fva_preprocessing=False,
    )
    for rid, dual in result_dual.driving_force_duals.items():
        tag = "<- nonzero dual" if dual != 0 else "  (has slack)"
        print(f"  {rid}: d(mdf)/d(dG0) = {dual:+.3f}  {tag}")
    print(f"  verified minimal bottleneck set: {result_dual.bottleneck_reactions}")

    print("\nIterative bottleneck relaxation via OptMDFAnalysis: builds the "
          "model/FVA/MILP once, then repeatedly solves, finds the current "
          "bottleneck, and permanently relaxes it -- an unbounded number of "
          "iterations, decided on the fly, with no rebuilding in between:")
    chain = cobra.Model("chain")
    W, X, Y, Zm = (cobra.Metabolite(n, compartment="c") for n in "WXYZ")
    EX_W = cobra.Reaction("EX_W", lower_bound=-10, upper_bound=0)
    EX_W.add_metabolites({W: -1})
    Ra = cobra.Reaction("Ra", lower_bound=0, upper_bound=1000)
    Ra.add_metabolites({W: -1, X: 1})
    Ra.annotation["dG0"] = -20.0  # favourable, never the bottleneck
    Rb = cobra.Reaction("Rb", lower_bound=0, upper_bound=1000)
    Rb.add_metabolites({X: -1, Y: 1})
    Rb.annotation["dG0"] = 8.0  # unfavourable -- the first bottleneck
    Rc = cobra.Reaction("Rc", lower_bound=0, upper_bound=1000)
    Rc.add_metabolites({Y: -1, Zm: 1})
    Rc.annotation["dG0"] = 6.0  # unfavourable -- the second bottleneck
    EX_Z = cobra.Reaction("EX_Z", lower_bound=0, upper_bound=1000)
    EX_Z.add_metabolites({Zm: -1})
    chain.add_reactions([EX_W, Ra, Rb, Rc, EX_Z])

    analysis = OptMDFAnalysis(
        chain, Cmin=1e-6, Cmax=1e-2,
        scenarios={"EX_Z": (1.0, 1000.0)},
        use_fva_preprocessing=False,
    )
    for result, bottleneck in analysis.run(max_iterations=10):
        print(f"  mdf={result.mdf:.3f}  bottleneck_relaxed={bottleneck}")
    print(f"  {len(analysis.history)} solves total, model/FVA/MILP built once")
