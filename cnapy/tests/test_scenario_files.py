"""Tests for saving/loading scenarios as .scen (JSON) and .val files (Scenario.save/load in cnapy/appdata.py)
and for parse_scenario. The spreadsheet format is covered by test_scenario_spreadsheet.py.

run: pytest cnapy/tests/test_scenario_files.py
"""
import json
import math

import cobra
import pytest

from cnapy.appdata import AppData, Scenario, parse_scenario
from test_scenario_spreadsheet import MODEL_REACTIONS, isobutanol_scenario


@pytest.fixture
def appdata(qapp):
    appdata = AppData()
    model = cobra.Model("test")
    model.add_reactions([cobra.Reaction(r) for r in MODEL_REACTIONS])
    appdata.project.cobra_py_model = model
    return appdata


def flux_tuples(scen):
    # values loaded from JSON are lists, compare them as tuples
    return {r: tuple(v) for r, v in scen.items()}


def write_json(path, json_dict):
    with open(path, "w") as fp:
        json.dump(json_dict, fp)
    return str(path)


def scen_json(**fields):
    json_dict = {"fluxes": {}, "pinned_reactions": [], "description": "", "objective_direction": "max",
                 "objective_coefficients": {}, "use_scenario_objective": False, "reactions": {},
                 "constraints": [], "annotations": [], "version": 3}
    json_dict.update(fields)
    return json_dict


def test_scen_round_trip(tmp_path, appdata):
    path = str(tmp_path / "scen.scen")
    expected = isobutanol_scenario()
    expected.save(path)
    assert not expected.has_unsaved_changes
    unknown_ids, incompatible_constraints, skipped = appdata.project.scen_values.load(path, appdata)
    assert unknown_ids == [] and incompatible_constraints == [] and skipped == []
    scen = appdata.project.scen_values  # replaced by a copy when the flux values are set
    assert scen.file_name == path
    assert flux_tuples(scen) == dict(expected)  # also checks that -inf survives
    assert scen.pinned_reactions == expected.pinned_reactions
    assert scen.description == expected.description
    assert scen.objective_direction == "min"
    assert scen.objective_coefficients == expected.objective_coefficients
    assert scen.use_scenario_objective is True
    assert scen.reactions == expected.reactions
    assert scen.constraints == expected.constraints
    assert scen.annotations == expected.annotations
    assert {r: tuple(v) for r, v in appdata.project.comp_values.items()} == dict(expected)


def test_scen_unknown_ids_are_reported_and_dropped(tmp_path, appdata):
    path = write_json(tmp_path / "unknown.scen", scen_json(
        # the scenario reaction R_new can have a flux value, its R_ prefix must not be stripped
        fluxes={"PGI": [1.0, 2.0], "R_BIOMASS": [0.1, 0.1], "UNKNOWN": [3.0, 3.0], "R_UNKNOWN": [1.0, 1.0],
                "R_new": [4.0, 4.0]},
        pinned_reactions=["PGI", "UNKNOWN_PINNED"],
        objective_coefficients={"BIOMASS": 1.0, "UNKNOWN_OBJ": 2.0},
        reactions={"PGI": [{"a_c": -1.0}, 0.0, 10.0], "R_new": [{"a_c": -1.0}, 0.0, 10.0]},
        constraints=[[{"PGI": 1.0, "R_new": 1.0}, "<=", 5.0], [{"UNKNOWN": 1.0}, ">=", 1.0], [None, "", ""]]))
    unknown_ids, incompatible_constraints, skipped = appdata.project.scen_values.load(path, appdata)
    # reported with the IDs given in the file, also when they start with R_
    assert sorted(unknown_ids) == ["R_UNKNOWN", "UNKNOWN", "UNKNOWN_OBJ", "UNKNOWN_PINNED"]
    assert incompatible_constraints == [[{"UNKNOWN": 1.0}, ">=", 1.0]]
    assert skipped == ["PGI"]  # a scenario reaction must not replace a model reaction
    scen = appdata.project.scen_values
    # R_ prefix stripped from R_BIOMASS
    assert flux_tuples(scen) == {"PGI": (1.0, 2.0), "BIOMASS": (0.1, 0.1), "R_new": (4.0, 4.0)}
    assert tuple(appdata.project.comp_values["R_new"]) == (4.0, 4.0)
    assert scen.pinned_reactions == {"PGI"}
    assert scen.objective_coefficients == {"BIOMASS": 1.0}
    assert scen.reactions == {"R_new": [{"a_c": -1.0}, 0.0, 10.0]}  # bounds unchanged
    assert scen.constraints == [[{"PGI": 1.0, "R_new": 1.0}, "<=", 5.0], Scenario.empty_constraint]


def test_scen_merge_keeps_metadata(tmp_path, appdata):
    scen = appdata.project.scen_values
    scen["PGI"] = (1.0, 2.0)
    scen["EX_o2_e"] = (-5.0, 0.0)
    scen.pinned_reactions = {"PGI"}
    scen.description = "keep me"
    scen.objective_coefficients = {"BIOMASS": 1.0}
    scen.constraints = [[{"PGI": 1.0}, "<=", 3.0]]
    path = write_json(tmp_path / "merge.scen", scen_json(
        fluxes={"PGI": [3.0, 3.0], "EX_glc__D_e": [-10.0, -10.0]}, pinned_reactions=["BIOMASS"],
        description="other", objective_direction="min", objective_coefficients={"PGI": 1.0},
        constraints=[[{"EX_o2_e": 1.0}, ">=", -1.0]]))
    unknown_ids, _, _ = scen.load(path, appdata, merge=True)
    assert unknown_ids == []
    merged = appdata.project.scen_values
    assert flux_tuples(merged) == {"PGI": (3.0, 3.0), "EX_o2_e": (-5.0, 0.0), "EX_glc__D_e": (-10.0, -10.0)}
    assert merged.pinned_reactions == {"PGI", "BIOMASS"}
    assert merged.description == "keep me"
    assert merged.objective_direction == "max"
    assert merged.objective_coefficients == {"BIOMASS": 1.0}
    assert merged.constraints == [[{"PGI": 1.0}, "<=", 3.0]]


def test_scen_merge_values_of_scenario_reactions(tmp_path, appdata):
    scen = appdata.project.scen_values
    scen.reactions = {"S1": [{"a_c": -1.0}, 0.0, 10.0]}
    path = write_json(tmp_path / "merge.scen", scen_json(
        fluxes={"S1": [2.0, 3.0], "S2": [1.0, 1.0]}, reactions={"S2": [{"b_c": -1.0}, 0.0, 10.0]}))
    unknown_ids, _, _ = scen.load(path, appdata, merge=True)
    # the scenario reactions of a merged file are not taken over, hence neither the value of S2
    assert unknown_ids == ["S2"]
    merged = appdata.project.scen_values
    assert flux_tuples(merged) == {"S1": (2.0, 3.0)}
    assert merged.reactions == {"S1": [{"a_c": -1.0}, 0.0, 10.0]}


def test_load_scenario_into_model_with_scenario_reaction_values(appdata):
    scen = appdata.project.scen_values
    scen.reactions = {"S1": [{"a_c": -1.0}, 0.0, 10.0], "S2": [{"a_c": 1.0}, -5.0, 5.0]}
    scen["S1"] = (2.0, 3.0)  # overrides the bounds of the scenario reaction
    scen["PGI"] = (1.0, 1.0)
    model = appdata.project.cobra_py_model
    with model as m:
        appdata.project.load_scenario_into_model(m)
        assert m.reactions.S1.bounds == (2.0, 3.0)
        assert m.reactions.S2.bounds == (-5.0, 5.0)  # without scenario value it keeps its own bounds
        assert m.reactions.PGI.bounds == (1.0, 1.0)
    assert "S1" not in model.reactions and "S2" not in model.reactions


def test_load_scenario_into_model_annotations_are_reverted(appdata):
    scen = appdata.project.scen_values
    scen.reactions = {"S1": [{"a_c": -1.0}, 0.0, 10.0]}
    scen.annotations = [{"reaction_id": "PGI", "key": "existing", "value": "scenario"},
                        {"reaction_id": "PGI", "key": "new", "value": "x"},
                        {"reaction_id": "S1", "key": "new", "value": "y"}]
    model = appdata.project.cobra_py_model
    pgi = model.reactions.PGI
    pgi.annotation["existing"] = "model"
    assert scen.reaction_annotation(pgi, "existing") == "scenario"
    assert scen.reaction_annotation(pgi, "missing", "default") == "default"
    with model as m:
        appdata.project.load_scenario_into_model(m)
        assert m.reactions.PGI.annotation == {"existing": "scenario", "new": "x"}
        assert m.reactions.S1.annotation == {"new": "y"}
    assert pgi.annotation == {"existing": "model"}


def test_scen_load_without_merge_replaces_everything(tmp_path, appdata):
    scen = appdata.project.scen_values
    scen["PGI"] = (1.0, 2.0)
    scen.pinned_reactions = {"PGI"}
    scen.description = "old"
    path = write_json(tmp_path / "new.scen", scen_json(fluxes={"BIOMASS": [0.5, 0.5]}))
    scen.load(path, appdata)
    loaded = appdata.project.scen_values
    assert flux_tuples(loaded) == {"BIOMASS": (0.5, 0.5)}
    assert loaded.pinned_reactions == set() and loaded.description == ""


def test_legacy_flux_only_scen(tmp_path, appdata):
    path = write_json(tmp_path / "legacy.scen", {"PGI": [1.0, 2.0], "UNKNOWN": [0.0, 0.0]})
    unknown_ids, _, _ = appdata.project.scen_values.load(path, appdata)
    assert unknown_ids == ["UNKNOWN"]
    assert flux_tuples(appdata.project.scen_values) == {"PGI": (1.0, 2.0)}


def test_val_file(tmp_path, appdata):
    path = tmp_path / "scenario.val"
    path.write_text("## CellNetAnalyzer scenario\nPGI 1.5\n\nR_BIOMASS 0.2\nnot a valid line\nUNKNOWN 1\n")
    unknown_ids, _, _ = appdata.project.scen_values.load(str(path), appdata)
    assert unknown_ids == ["UNKNOWN"]
    scen = appdata.project.scen_values
    assert dict(scen) == {"PGI": (1.5, 1.5), "BIOMASS": (0.2, 0.2)}
    assert scen.file_name == ""  # .val files are not saved back


def test_load_missing_file_raises(tmp_path, appdata):
    with pytest.raises(FileNotFoundError):
        appdata.project.scen_values.load(str(tmp_path / "missing.scen"), appdata)


@pytest.mark.parametrize("text, expected", [
    ("5", (5.0, 5.0)),
    ("-1.5", (-1.5, -1.5)),
    ("(-1, 2)", (-1, 2)),
    ("(0.5,0.5)", (0.5, 0.5)),
])
def test_parse_scenario(text, expected):
    assert parse_scenario(text) == expected


def test_parse_scenario_inf():
    lb, ub = parse_scenario("-inf")
    assert lb == ub == -math.inf


@pytest.mark.parametrize("text", ["abc", "(1, 2"])
def test_parse_scenario_invalid(text):
    with pytest.raises((ValueError, SyntaxError)):
        parse_scenario(text)
