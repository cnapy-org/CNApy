"""Tests for elementary flux modes (cnapy.core.efm_computation, runs efmtool via Java) and minimal cut sets
(optlang_enumerator's compute_mcs, called like the MCS dialog does) on a toy network whose EFMs and MCSs
are known.

Toy network:   R1: -> A    R2: A -> B    R3: A -> C    R4: B <-> C    R5: B ->    R6: C ->

EFMs (4): R1 R2 R5 | R1 R3 R6 | R1 R2 R4 R6 | R1 R3 -R4 R5
MCSs for the target R6 >= 1: {R1} | {R6} | {R2, R3} | {R3, R4}

run: pytest cnapy/tests/test_efm_mcs.py
"""
import cobra
import numpy
import pytest

from cnapy.appdata import Scenario
from cnapy.core import efm_computation

EXPECTED_EFMS = {(("R1", 1), ("R2", 1), ("R5", 1)),
                 (("R1", 1), ("R3", 1), ("R6", 1)),
                 (("R1", 1), ("R2", 1), ("R4", 1), ("R6", 1)),
                 (("R1", 1), ("R3", 1), ("R4", -1), ("R5", 1))}


def toy_model(r6_backwards=False):
    model = cobra.Model("toy")
    a, b, c = (cobra.Metabolite(m, compartment="c") for m in "ABC")
    reactions = {"R1": ({a: 1}, 0), "R2": ({a: -1, b: 1}, 0), "R3": ({a: -1, c: 1}, 0),
                 "R4": ({b: -1, c: 1}, -1000), "R5": ({b: -1}, 0), "R6": ({c: -1}, 0)}
    for rid, (stoichiometry, lb) in reactions.items():
        r = cobra.Reaction(rid, lower_bound=lb, upper_bound=1000)
        r.add_metabolites(stoichiometry)
        model.add_reactions([r])
    if r6_backwards:  # written as the uptake of C, so it can only run backwards
        model.reactions.R6.add_metabolites({c: 2}, combine=True)
        model.reactions.R6.bounds = (-1000, 0)
    return model


def efm_set(ems, flip=()):
    """EFMs as sets of (reaction, sign) with the flux of R1 normalized to 1"""
    result = set()
    for row in numpy.asarray(ems.fv_mat):
        r1 = row[ems.reac_id.index("R1")]
        assert r1 > 0
        mode = []
        for rid, v in zip(ems.reac_id, row / r1):
            if abs(v) > 1e-9:
                assert v == pytest.approx(round(v))  # all EFMs of the toy network have unit fluxes
                mode.append((rid, -int(round(v)) if rid in flip else int(round(v))))
        result.add(tuple(mode))
    return result


@pytest.fixture
def in_tmp_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)  # efmtool writes its temporary files into the current directory


def test_efms_of_toy_network(in_tmp_dir):
    ems, scenario = efm_computation(toy_model(), Scenario(), False)
    assert ems is not None, "efmtool failed, see the console output (is Java available?)"
    assert scenario == {}
    assert ems.reac_id == ["R1", "R2", "R3", "R4", "R5", "R6"]
    assert len(ems) == 4
    assert efm_set(ems) == EXPECTED_EFMS
    assert numpy.all(ems.irreversible)


def test_efms_with_reaction_knocked_out_by_scenario(in_tmp_dir):
    scen = Scenario()
    scen["R5"] = (0.0, 0.0)
    scen["R2"] = (0.0, 5.0)  # only (0, 0) is applied
    ems, scenario = efm_computation(toy_model(), scen, True)
    assert scenario == {"R5": (0, 0)}
    assert "R5" not in ems.reac_id
    assert efm_set(ems) == {m for m in EXPECTED_EFMS if ("R5", 1) not in m}


def test_efms_with_irreversible_backwards_reaction(in_tmp_dir):
    ems, _ = efm_computation(toy_model(r6_backwards=True), Scenario(), False)
    # same EFMs, but R6 carries a negative flux
    assert efm_set(ems, flip={"R6"}) == EXPECTED_EFMS


def test_mcs_of_toy_network():
    from optlang_enumerator import mcs_computation
    model = toy_model()
    model.solver = "glpk"
    reac_id = model.reactions.list_attr("id")
    reac_id_symbols = mcs_computation.get_reac_id_symbols(reac_id)
    targets = [mcs_computation.relations2leq_matrix(
        mcs_computation.parse_relations([("R6", ">=", 1.0)], reac_id_symbols=reac_id_symbols), reac_id)]
    mcs, err_val = mcs_computation.compute_mcs(model, targets=targets, max_mcs_size=3, timeout=60)
    assert err_val == 0
    assert {frozenset(reac_id[i] for i in m) for m in mcs} == {
        frozenset({"R1"}), frozenset({"R6"}), frozenset({"R2", "R3"}), frozenset({"R3", "R4"})}
