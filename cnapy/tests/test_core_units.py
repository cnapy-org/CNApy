"""
Unit-level tests for the functions that back MainWindow.fba() / .fva():

    cnapy.core_gui.model_optimization_with_exceptions
    cnapy.core.multi_threaded_HiGHS_FVA

These don't touch Qt widgets at all (beyond core_gui's QMessageBox import),
so they're the fastest, most robust layer of coverage - a good place to
catch a regression in the solve logic itself, independent of whether the
slot wiring around it is also correct (see test_mainwindow_slots.py for
that layer).
"""
import math

import cobra
import pytest

from cnapy.core_gui import model_optimization_with_exceptions
from cnapy.core import multi_threaded_HiGHS_FVA


def test_model_optimization_matches_cobrapy_optimize(ecc2_model):
    """model_optimization_with_exceptions is (for the non-error path)
    exactly model.optimize() - verify it doesn't alter that result."""
    reference = ecc2_model.copy().optimize()
    result = model_optimization_with_exceptions(ecc2_model)

    assert result.status == "optimal"
    assert result.status == reference.status
    assert result.objective_value == pytest.approx(reference.objective_value, rel=1e-6)


def test_model_optimization_infeasible_scenario(ecc2_model):
    """Forcing an infeasible scenario (uptake blocked but growth required)
    should come back with status 'infeasible', not raise."""
    biomass = next(r for r in ecc2_model.reactions if r.objective_coefficient != 0)
    biomass.lower_bound = 1.0  # force nonzero growth
    for ex in ecc2_model.exchanges:
        ex.lower_bound = 0.0  # block every uptake

    result = model_optimization_with_exceptions(ecc2_model)
    assert result.status == "infeasible"


def _finite_bounds_model(model: cobra.Model) -> cobra.Model:
    """Mirror what MainWindow.fva() does before calling multi_threaded_HiGHS_FVA:
    replace +/-inf reaction bounds with cobra's configured defaults, since
    the HiGHS-backed FVA path does not accept unbounded rows."""
    cfg = cobra.Configuration()
    m = model.copy()
    for r in m.reactions:
        if r.lower_bound == -float("inf"):
            r.lower_bound = cfg.lower_bound
        if r.upper_bound == float("inf"):
            r.upper_bound = cfg.upper_bound
    return m


def test_fva_unconstrained_matches_cobrapy(ecc2_model, fva_reference):
    """With no additional scenario constraints, multi_threaded_HiGHS_FVA's
    per-reaction min/max should match cobrapy's own (structural,
    fraction_of_optimum=0) FVA, precomputed in fva_reference (see
    generate_fva_reference_data.py) rather than recomputed here."""
    model = _finite_bounds_model(ecc2_model)

    lb, ub, n_bad = multi_threaded_HiGHS_FVA(model, constraints=[])
    assert n_bad == 0

    reference = fva_reference["unconstrained"]
    for i, rxn in enumerate(model.reactions):
        ref_lo, ref_hi = reference[rxn.id]
        assert lb[i] == pytest.approx(ref_lo, abs=1e-5), f"lower bound mismatch for {rxn.id}"
        assert ub[i] == pytest.approx(ref_hi, abs=1e-5), f"upper bound mismatch for {rxn.id}"


def test_fva_with_growth_constraint_matches_cobrapy(ecc2_model, fva_reference):
    """With an explicit constraint fixing growth at its optimum (the
    "growth-coupled" FVA a user gets by first fixing biomass in a
    scenario), results should match the growth_coupled entries in
    fva_reference (cobrapy's fraction_of_optimum=1.0 FVA, precomputed)."""
    model = _finite_bounds_model(ecc2_model)
    biomass_id = fva_reference["biomass_reaction_id"]
    biomass = model.reactions.get_by_id(biomass_id)

    opt = model.copy().optimize().objective_value
    assert opt == pytest.approx(fva_reference["biomass_objective_value"], rel=1e-6), (
        "live model's optimum no longer matches the value the cached "
        "growth_coupled FVA reference was computed at - regenerate with "
        "generate_fva_reference_data.py"
    )
    constraints = [({biomass.id: 1.0}, "=", opt)]

    lb, ub, n_bad = multi_threaded_HiGHS_FVA(model, constraints=constraints)
    assert n_bad == 0

    reference = fva_reference["growth_coupled"]
    for i, rxn in enumerate(model.reactions):
        if rxn.id == biomass_id:
            continue  # pinned reaction; trivially equal to opt on both sides
        ref_lo, ref_hi = reference[rxn.id]
        assert lb[i] == pytest.approx(ref_lo, abs=1e-4), f"lower bound mismatch for {rxn.id}"
        assert ub[i] == pytest.approx(ref_hi, abs=1e-4), f"upper bound mismatch for {rxn.id}"


def test_fva_infeasible_scenario_raises(ecc2_model):
    """multi_threaded_HiGHS_FVA is documented (and relied on by
    MainWindow.fva()) to raise cobra.exceptions.Infeasible rather than
    return garbage bounds when the scenario itself has no feasible flux."""
    model = _finite_bounds_model(ecc2_model)
    biomass = next(r for r in model.reactions if r.objective_coefficient != 0)
    constraints = [({biomass.id: 1.0}, ">=", 1e6)]  # unachievable growth

    with pytest.raises(cobra.exceptions.Infeasible):
        multi_threaded_HiGHS_FVA(model, constraints=constraints)


def test_fva_bounds_are_internally_consistent(ecc2_model):
    """Sanity property that should hold regardless of the reference
    implementation: lower <= upper for every reaction, and both bounds lie
    within the reaction's own (possibly scenario-tightened) bounds."""
    model = _finite_bounds_model(ecc2_model)
    lb, ub, n_bad = multi_threaded_HiGHS_FVA(model, constraints=[])
    assert n_bad == 0

    for i, rxn in enumerate(model.reactions):
        assert not math.isnan(lb[i]) and not math.isnan(ub[i])
        # 1e-6, not 1e-7: matches the tolerance used for the two checks
        # below, and blocked/near-zero-flux reactions can come back as e.g.
        # -1.5e-07 instead of exactly 0.0 depending on the solver's own
        # feasibility tolerance and platform-specific floating-point noise
        # (observed on Linux but not Windows/macOS for this exact model).
        assert lb[i] <= ub[i] + 1e-6
        assert lb[i] >= rxn.lower_bound - 1e-6
        assert ub[i] <= rxn.upper_bound + 1e-6
