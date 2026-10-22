"""Tests for reading/writing scenarios as .xlsx spreadsheets (cnapy/scenario_spreadsheet.py).

run: pytest cnapy/tests/test_scenario_spreadsheet.py
"""
import cobra
import openpyxl
import pytest

from cnapy.appdata import AppData, Scenario
from cnapy.scenario_spreadsheet import (ScenarioSpreadsheetError, read_scenario_xlsx, write_scenario_xlsx,
                                        FLUXES, REACTIONS, CONSTRAINTS, ANNOTATIONS, GENERAL, HEADERS)

MODEL_REACTIONS = ["EX_glc__D_e", "EX_o2_e", "BIOMASS", "PGI"]


def isobutanol_scenario() -> Scenario:
    scen = Scenario()
    scen["EX_glc__D_e"] = (-10.0, -10.0)
    scen["EX_o2_e"] = (-float("inf"), 0.0)
    scen.pinned_reactions = {"EX_glc__D_e", "PGI"}
    scen.description = "isobutanol production\nwith a minimal yield"
    scen.objective_direction = "min"
    scen.objective_coefficients = {"EX_iBuOH": 1.0, "BIOMASS": -0.5}
    scen.use_scenario_objective = True
    scen.reactions = {"EX_iBuOH": [{"iBuOH_c": -1.0}, 0.0, 1000.0],
                      "iBuOH": [{"h_c": -4.0, "nadh_c": -2.0, "pyr_c": -2.0, "co2_c": 2.0, "h2o_c": 1.0,
                                 "iBuOH_c": 1.0, "nad_c": 2.0}, -5.0, 1000.0]}
    scen.constraints = [[{"EX_iBuOH": 1.0, "EX_glc__D_e": 1.0}, ">=", 0.0], [{"PGI": 2.0}, "<=", 3.5]]
    scen.annotations = [{"reaction_id": "iBuOH", "key": "biocyc.reaction", "value": "RXN-1"}]
    return scen


def make_workbook(path, sheets):
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for title, rows in sheets.items():
        ws = wb.create_sheet(title)
        ws.append(HEADERS[title])
        for row in rows:
            ws.append(row)
    wb.save(path)
    return path


def test_round_trip(tmp_path):
    scen = isobutanol_scenario()
    path = tmp_path / "scen.xlsx"
    write_scenario_xlsx(scen, path)
    d = read_scenario_xlsx(path, MODEL_REACTIONS)
    assert d["fluxes"] == dict(scen)
    assert set(d["pinned_reactions"]) == scen.pinned_reactions
    assert d["description"] == scen.description
    assert d["objective_direction"] == "min"
    assert d["objective_coefficients"] == scen.objective_coefficients
    assert d["use_scenario_objective"] is True
    assert d["reactions"] == scen.reactions
    assert d["constraints"] == scen.constraints
    assert d["annotations"] == scen.annotations


def test_empty_scenario_and_template(tmp_path):
    path = tmp_path / "template.xlsx"
    write_scenario_xlsx(Scenario(), path, include_examples=True)  # example rows are comments
    d = read_scenario_xlsx(path, MODEL_REACTIONS)
    assert d["fluxes"] == {} and d["reactions"] == {} and d["constraints"] == [] and d["annotations"] == []
    assert d["pinned_reactions"] == [] and d["objective_coefficients"] == {}
    assert d["use_scenario_objective"] is False


def test_hand_written_sheet(tmp_path):
    path = make_workbook(tmp_path / "hand.xlsx", {
        FLUXES: [["EX_glc__D_e", -10, None, None],
                 ["EX_o2_e", None, "-5,5", "no"],
                 ["# EX_foo", "abc", 1, None],
                 [None, None, None, None],
                 ["BIOMASS", None, None, "x"],
                 ["PGI", "-inf", "inf", True]],
        REACTIONS: [["R_new", "a_c <=> 2 b_c", None, 10]],
        GENERAL: [["objective", "R_new", None], ["Direction", "Maximize", None]],
    })  # no Constraints and Annotations sheets
    d = read_scenario_xlsx(path, MODEL_REACTIONS)
    assert d["fluxes"] == {"EX_glc__D_e": (-10.0, -10.0), "EX_o2_e": (-5.5, -5.5),
                           "PGI": (-float("inf"), float("inf"))}
    assert d["pinned_reactions"] == ["BIOMASS", "PGI"]
    assert d["reactions"] == {"R_new": [{"a_c": -1, "b_c": 2}, cobra.Configuration().lower_bound, 10.0]}
    assert d["objective_coefficients"] == {"R_new": 1.0}
    assert d["objective_direction"] == "max"
    assert d["use_scenario_objective"] is True  # objective given and no explicit setting


def test_errors_are_collected(tmp_path):
    path = make_workbook(tmp_path / "bad.xlsx", {
        FLUXES: [["EX_glc__D_e", "abc", None, None], ["EX_o2_e", 5, 1, None], ["BIOMASS", None, None, "maybe"]],
        REACTIONS: [["R_new", "a_c b_c", None, None], ["R_new", "a_c -->", None, None]],
        CONSTRAINTS: [["unknown_reac >= 1"], ["R_new + PGI"]],
        ANNOTATIONS: [["PGI", None, "value"]],
        GENERAL: [["Direction", "sideways", None]],
    })
    with pytest.raises(ScenarioSpreadsheetError) as e:
        read_scenario_xlsx(path, MODEL_REACTIONS)
    messages = e.value.messages
    for location in ["Fluxes!B2", "Fluxes!B3", "Fluxes!D4", "Reactions!B2", "Reactions!A3",
                     "Constraints!A2", "Constraints!A3", "Annotations!B2", "General!B2"]:
        assert any(m.startswith(location + ":") for m in messages), location
    assert len(messages) == 9


@pytest.fixture
def appdata(qapp):
    appdata = AppData()
    model = cobra.Model("test")
    model.add_reactions([cobra.Reaction(r) for r in MODEL_REACTIONS])
    appdata.project.cobra_py_model = model
    return appdata


def test_scenario_load_and_save(tmp_path, appdata):
    path = str(tmp_path / "scen.xlsx")
    isobutanol_scenario().save(path)
    unknown_ids, incompatible_constraints, skipped = appdata.project.scen_values.load(path, appdata)
    assert unknown_ids == [] and incompatible_constraints == [] and skipped == []
    scen = appdata.project.scen_values  # replaced by a copy when the flux values are set
    assert scen.file_name == path
    expected = isobutanol_scenario()
    assert dict(scen) == dict(expected)
    assert scen.reactions == expected.reactions
    assert scen.constraints == expected.constraints
    assert scen.objective_coefficients == expected.objective_coefficients
    assert scen.pinned_reactions == expected.pinned_reactions


def test_scenario_load_error_keeps_scenario(tmp_path, appdata):
    scen = appdata.project.scen_values
    scen["PGI"] = (1.0, 2.0)
    scen.description = "keep me"
    path = make_workbook(tmp_path / "bad.xlsx", {FLUXES: [["EX_glc__D_e", "abc", None, None]]})
    with pytest.raises(ScenarioSpreadsheetError):
        scen.load(str(path), appdata)
    assert dict(scen) == {"PGI": (1.0, 2.0)} and scen.description == "keep me"
