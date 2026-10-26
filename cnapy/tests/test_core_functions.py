"""Tests for functions in cnapy/core.py that had no tests yet (yield optimization, making a scenario
feasible, element balances, biomass weight, replacing IDs) and for FluxVectorContainer.

The optlang-based functions are run with GLPK, because the pip versions of Gurobi/CPLEX that may be
the default solver have size-limited licenses.

run: pytest cnapy/tests/test_core_functions.py
"""
import math

import cobra
import numpy
import pytest

from cnapy.appdata import Scenario
from cnapy.core import (check_biomass_weight, element_exchange_balance, highs_yopt, make_scenario_feasible,
                        make_scenario_feasible_osqp, replace_ids)
from cnapy.flux_vector_container import FluxVectorContainer

BIOMASS = "Ec_biomass_iJO1366_core_53p95M"


@pytest.fixture(scope="module")
def model(ecc2_reference_model):
    """shared by the tests of this module, which must not change it (switching the solver takes ~2 s)"""
    model = ecc2_reference_model.copy()
    model.solver = "glpk"
    return model


@pytest.fixture(scope="module")
def max_growth(model):
    """maximal growth rate with glucose uptake fixed at 10"""
    with model:
        model.reactions.EX_glc_e.bounds = (-10.0, -10.0)
        model.objective = BIOMASS
        return model.slim_optimize()


# --- highs_yopt -------------------------------------------------------------------------------

def test_yopt_biomass_yield_matches_fba(model, max_growth):
    assert model.reactions.EX_glc_e.lower_bound == -10.0  # yield is highest at maximal uptake (maintenance)
    sol = highs_yopt(model, {BIOMASS: 1.0}, {"EX_glc_e": -1.0})
    assert sol.status == "optimal" and not sol.scalable
    assert sol.objective_value == pytest.approx(max_growth / 10.0, rel=1e-6)
    assert sol.fluxes[BIOMASS] / -sol.fluxes["EX_glc_e"] == pytest.approx(sol.objective_value, rel=1e-6)


def test_yopt_minimize_and_scenario_constraints(model):
    sol = highs_yopt(model, {"EX_ac_e": 1.0}, {"EX_glc_e": -1.0}, obj_sense="minimize",
                     constraints=[({"EX_ac_e": 1.0}, ">=", 2.0)])
    assert sol.status == "optimal"
    assert sol.fluxes["EX_ac_e"] >= 2.0 - 1e-6
    assert sol.objective_value == pytest.approx(sol.fluxes["EX_ac_e"] / -sol.fluxes["EX_glc_e"], rel=1e-6)
    assert sol.objective_value == pytest.approx(0.2, rel=1e-6)  # 2 / 10: the minimum at maximal uptake
    sol_max = highs_yopt(model, {"EX_ac_e": 1.0}, {"EX_glc_e": -1.0})
    assert sol_max.status == "optimal" and sol_max.objective_value > sol.objective_value


def test_yopt_infeasible_constraints(model):
    sol = highs_yopt(model, {BIOMASS: 1.0}, {"EX_glc_e": -1.0}, constraints=[({BIOMASS: 1.0}, ">=", 2.0)])
    assert sol.status == "infeasible" and math.isnan(sol.objective_value)


def test_yopt_denominator_fixed_at_zero(model):
    sol = highs_yopt(model, {BIOMASS: 1.0}, {"EX_ac_e": 1.0}, constraints=[({"EX_ac_e": 1.0}, "=", 0.0)])
    assert sol.status == "infeasible" and math.isnan(sol.objective_value)


def test_yopt_undefined_yield(model):
    # acetate secretion can be zero while there is growth, so the yield is not bounded
    sol = highs_yopt(model, {BIOMASS: 1.0}, {"EX_ac_e": 1.0})
    assert sol.status == "unbounded" and math.isnan(sol.objective_value)


def test_yopt_unknown_reaction(model):
    with pytest.raises(KeyError):
        highs_yopt(model, {"UNKNOWN": 1.0}, {"EX_glc_e": -1.0})


# --- make_scenario_feasible -------------------------------------------------------------------

def infeasible_scenario():
    scen = Scenario()
    scen[BIOMASS] = (1.2, 1.2)  # more than the maximal growth rate with this glucose uptake
    scen["EX_glc_e"] = (-10.0, -10.0)
    return scen


def assert_fluxes_feasible(model, fluxes, reactions):
    with model:
        for r in reactions:
            model.reactions.get_by_id(r).bounds = (fluxes[r] - 1e-6, fluxes[r] + 1e-6)
        assert model.slim_optimize(error_value=None) is not None


def test_make_scenario_feasible_lp(model, max_growth):
    solution, reactions_in_objective, bm_mod, _, _ = make_scenario_feasible(model, infeasible_scenario())
    assert solution.status == "optimal"
    assert sorted(reactions_in_objective) == sorted([BIOMASS, "EX_glc_e"])
    assert solution.objective_value == pytest.approx(1.2 - max_growth, abs=1e-6)  # weighted L1 change
    assert solution.fluxes[BIOMASS] == pytest.approx(max_growth, abs=1e-6)
    assert solution.fluxes["EX_glc_e"] == pytest.approx(-10.0, abs=1e-6)
    assert bm_mod == {}
    assert_fluxes_feasible(model, solution.fluxes, [BIOMASS, "EX_glc_e"])


@pytest.mark.parametrize("osqp_directly", [True, False], ids=["osqp", "use_QP"])
def test_make_scenario_feasible_qp(model, max_growth, osqp_directly):
    if osqp_directly:
        solution, reactions_in_objective, _, _, _ = make_scenario_feasible_osqp(model, infeasible_scenario())
    else:  # with GLPK as solver, use_QP=True must delegate to OSQP
        solution, reactions_in_objective, _, _, _ = make_scenario_feasible(model, infeasible_scenario(),
                                                                           use_QP=True)
    assert solution.status == "optimal"
    assert sorted(reactions_in_objective) == sorted([BIOMASS, "EX_glc_e"])
    assert solution.objective_value == pytest.approx((1.2 - max_growth) ** 2, abs=1e-5)  # squared change
    assert solution.fluxes[BIOMASS] == pytest.approx(max_growth, abs=1e-4)
    assert solution.fluxes["EX_glc_e"] == pytest.approx(-10.0, abs=1e-4)


def test_make_scenario_feasible_keeps_feasible_scenario(model):
    scen = infeasible_scenario()
    scen[BIOMASS] = (0.5, 0.5)
    solution, _, _, _, _ = make_scenario_feasible(model, scen)
    assert solution.status == "optimal"
    assert solution.objective_value == pytest.approx(0.0, abs=1e-9)
    assert solution.fluxes[BIOMASS] == pytest.approx(0.5, abs=1e-9)


@pytest.mark.parametrize("osqp", [False, True], ids=["lp", "osqp"])
def test_make_scenario_feasible_adjusted_biomass_scenario_reaction(model, max_growth, osqp):
    # setup as created by the dialog: the adjusted biomass reaction is a scenario reaction with the bounds of the
    # original one and the growth rate as scenario value, the original biomass reaction is switched off
    biomass = model.reactions.get_by_id(BIOMASS)
    adjusted = "adjusted_" + BIOMASS
    scen = infeasible_scenario()
    scen.reactions = {adjusted: [{m.id: c for m, c in biomass.metabolites.items()}, *biomass.bounds]}
    scen[adjusted] = scen.pop(BIOMASS)
    scen[BIOMASS] = (0.0, 0.0)
    if osqp:
        solution, reactions_in_objective, _, _, _ = make_scenario_feasible_osqp(model, scen)
        abs_tol = 1e-4
    else:
        solution, reactions_in_objective, _, _, _ = make_scenario_feasible(model, scen)
        abs_tol = 1e-6
    assert solution.status == "optimal"
    assert sorted(reactions_in_objective) == sorted([adjusted, "EX_glc_e"])
    assert solution.fluxes[adjusted] == pytest.approx(max_growth, abs=abs_tol)
    assert solution.fluxes[BIOMASS] == pytest.approx(0.0, abs=abs_tol)
    assert adjusted not in model.reactions


@pytest.mark.parametrize("osqp", [False, True], ids=["lp", "osqp"])
@pytest.mark.parametrize("scenario_reaction", [False, True], ids=["model_reaction", "scenario_reaction"])
def test_make_scenario_feasible_weights_from_scenario_annotations(model, max_growth, osqp, scenario_reaction):
    scen = infeasible_scenario()
    reac_id = BIOMASS
    if scenario_reaction:
        biomass = model.reactions.get_by_id(BIOMASS)
        reac_id = "adjusted_" + BIOMASS
        scen.reactions = {reac_id: [{m.id: c for m, c in biomass.metabolites.items()}, *biomass.bounds]}
        scen[reac_id] = scen.pop(BIOMASS)
        scen[BIOMASS] = (0.0, 0.0)
    # the later scenario annotation takes precedence
    scen.annotations = [{"reaction_id": reac_id, "key": "weight", "value": "3"},
                        {"reaction_id": reac_id, "key": "weight", "value": "2"}]
    if osqp:
        solution, _, _, _, _ = make_scenario_feasible_osqp(model, scen, weights_key="weight")
        assert solution.objective_value == pytest.approx((1.2 - max_growth) ** 2 / 2, abs=1e-5)
    else:
        solution, _, _, _, _ = make_scenario_feasible(model, scen, weights_key="weight")
        assert solution.objective_value == pytest.approx((1.2 - max_growth) / 2, abs=1e-6)
    assert solution.status == "optimal"
    assert "weight" not in model.reactions.get_by_id(BIOMASS).annotation


def test_make_scenario_feasible_leaves_model_unchanged(model):
    bounds = {r.id: r.bounds for r in model.reactions}
    objective = str(model.objective.expression)
    make_scenario_feasible(model, infeasible_scenario())
    assert {r.id: r.bounds for r in model.reactions} == bounds
    assert str(model.objective.expression) == objective


# --- element_exchange_balance / check_biomass_weight ------------------------------------------

def test_element_exchange_balance(model):
    scen = Scenario()
    scen["EX_glc_e"] = (-10.0, -10.0)  # C6H12O6
    scen["EX_ac_e"] = (5.0, 5.0)       # C2H3O2
    scen["EX_co2_e"] = (20.0, 20.0)    # CO2
    messages = []
    influx, efflux = element_exchange_balance(model, scen, [], organic_elements_only=True,
                                              print_func=lambda *args: messages.append(args))
    assert dict(influx) == pytest.approx({"C": 60.0, "H": 120.0, "O": 60.0})
    assert dict(efflux) == pytest.approx({"C": -30.0, "H": -15.0, "O": -50.0})
    assert messages  # the balance table


def test_element_exchange_balance_non_boundary_reactions(model):
    scen = Scenario()
    scen["PGI"] = (2.0, 2.0)  # internal reaction, balanced: only counted if requested
    messages = []
    influx, efflux = element_exchange_balance(model, scen, ["PGI", "PFK"],
                                              print_func=lambda *args: messages.append(" ".join(map(str, args))))
    # g6p_c -> f6p_c: both C6, so in- and outflux of each element cancel
    assert set(influx) == set(efflux) and all(influx[el] + efflux[el] == pytest.approx(0.0) for el in influx)
    assert influx["C"] == pytest.approx(12.0)
    assert any("PFK" in m and "fixed" in m for m in messages)  # PFK has no fixed flux value


def test_check_biomass_weight(model):
    # the iJO1366 core biomass is normalized to 1 g/mmol
    assert check_biomass_weight(model, BIOMASS) == pytest.approx(1.0, abs=1e-3)


# --- replace_ids ------------------------------------------------------------------------------

def test_replace_metabolite_ids_from_annotation(ecc2_model):
    old = {m.id: m.annotation.get("metanetx.chemical") for m in ecc2_model.metabolites}
    replace_ids(ecc2_model.metabolites, "metanetx.chemical")
    by_original = {m.annotation.get("original ID", m.id): m for m in ecc2_model.metabolites}
    assert set(by_original) == set(old)
    for old_id, mnx in old.items():
        met = by_original[old_id]
        if mnx is None:
            assert met.id == old_id and "original ID" not in met.annotation
        else:
            assert met.id == mnx + "_" + met.compartment
    assert len({m.id for m in ecc2_model.metabolites}) == len(ecc2_model.metabolites)
    ecc2_model.metabolites.get_by_id(next(iter(by_original.values())).id)  # DictList index was updated


def test_replace_reaction_ids_unique_only(ecc2_model):
    mnx = {r.id: r.annotation.get("metanetx.reaction") for r in ecc2_model.reactions}
    counts = {}
    for v in mnx.values():
        counts[v] = counts.get(v, 0) + 1
    replace_ids(ecc2_model.reactions, "metanetx.reaction")
    shared = 0
    for r in ecc2_model.reactions:
        old_id = r.annotation.get("original ID", r.id)
        value = mnx[old_id]
        if value is None or counts[value] > 1:  # shared annotations are not used
            assert r.id == old_id
            shared += value is not None
        else:
            assert r.id == value
    assert shared > 0  # ECC2 has reactions that share a MetaNetX ID


def test_replace_ids_candidates_and_ambiguity():
    model = cobra.Model()  # the DictList index is only updated for reactions that belong to a model
    for rid, annotation in [("R1", "x;y"), ("R2", "z"), ("R3", "z2;R2"), ("R4", "")]:
        r = cobra.Reaction(rid)
        if annotation:
            r.annotation["key"] = annotation
        model.add_reactions([r])
    reactions = model.reactions
    replace_ids(reactions, "key", unambiguous_only=True, candidates_separator=";")
    assert [r.id for r in reactions] == ["R1", "z", "R3", "R4"]  # R1 and R3 have two candidates
    replace_ids(reactions, "key", candidates_separator=";")
    assert [r.id for r in reactions] == ["x", "z", "z2", "R4"]
    assert reactions.get_by_id("x").annotation["original ID"] == "R1"


# --- FluxVectorContainer ----------------------------------------------------------------------

def test_flux_vector_container_save_load(tmp_path):
    fv_mat = numpy.array([[1.0, 0.0, -2.5], [0.0, 3.0, 1.0]])
    fvc = FluxVectorContainer(fv_mat, reac_id=["R1", "R2", "R3"], irreversible=numpy.array([1, 0]),
                              unbounded=numpy.array([0, 1]))
    path = str(tmp_path / "modes.npz")
    fvc.save(path)
    loaded = FluxVectorContainer(path)
    numpy.testing.assert_array_equal(loaded.fv_mat, fv_mat)
    assert loaded.reac_id == ["R1", "R2", "R3"]
    numpy.testing.assert_array_equal(loaded.irreversible, [1, 0])
    numpy.testing.assert_array_equal(loaded.unbounded, [0, 1])
    assert len(loaded) == 2
    assert loaded[0] == {"R1": 1.0, "R3": -2.5}
    assert loaded.is_integer_vector_rounded(1, decimals=3) and not loaded.is_integer_vector_rounded(0, decimals=3)
    loaded.clear()
    assert loaded.reac_id == [] and loaded.fv_mat.shape == (0, 0)


def test_flux_vector_container_requires_reac_id():
    with pytest.raises(TypeError):
        FluxVectorContainer(numpy.zeros((1, 2)))


def test_flux_vector_container_invalid_file(tmp_path, monkeypatch):
    messages = []
    monkeypatch.setattr("cnapy.flux_vector_container.QMessageBox.critical", lambda *args: messages.append(args))
    path = tmp_path / "bad.npz"
    path.write_text("not an npz file")
    fvc = FluxVectorContainer(str(path))
    assert len(messages) == 1
    assert not hasattr(fvc, "fv_mat")
