"""Tests for the scenario undo/redo history: AppData's scen_values_* methods record the history,
MainWindow.undo_scenario_edit/redo_scenario_edit/update_undo_redo_actions (called unbound on the
fake_main_window from conftest.py) move through it and enable the toolbar actions.

run: pytest cnapy/tests/test_scenario_undo_redo.py
"""
import types

import pytest

from cnapy.appdata import Scenario


@pytest.fixture
def window(fake_main_window, mainwindow_cls):
    fake = fake_main_window
    for name in ("undo_scenario_edit", "redo_scenario_edit", "update_undo_redo_actions",
                 "discard_failed_scenario_load"):
        setattr(fake, name, types.MethodType(getattr(mainwindow_cls, name), fake))
    # like MainWindow.__init__ and reset_gui_for_new_project
    fake.appdata.scenarioHistoryChanged.connect(fake.update_undo_redo_actions)
    fake.appdata.clear_scenario_history()
    fake.appdata.add_scenario_to_history(fake.appdata.project.scen_values)
    return fake


def scen(window):
    return dict(window.appdata.project.scen_values)


def actions_enabled(window):
    return (window.undo_scenario_action.setEnabled.call_args.args[0],
            window.redo_scenario_action.setEnabled.call_args.args[0])


def test_fresh_history_has_nothing_to_undo(window):
    assert actions_enabled(window) == (False, False)
    window.undo_scenario_edit()
    window.redo_scenario_edit()
    assert scen(window) == {}
    assert window.appdata.current_scenario_index == 0


def test_undo_redo_restore_exact_states(window):
    appdata = window.appdata
    appdata.scen_values_set("EX_glc_e", (-10.0, -10.0))
    appdata.scen_values_set_multiple(["EX_o2_e", "EX_glc_e"], [(-5.0, 0.0), (-8.0, -8.0)])
    appdata.scen_values_pop("EX_o2_e")
    states = [{}, {"EX_glc_e": (-10.0, -10.0)},
              {"EX_glc_e": (-8.0, -8.0), "EX_o2_e": (-5.0, 0.0)}, {"EX_glc_e": (-8.0, -8.0)}]
    assert scen(window) == states[3]
    assert actions_enabled(window) == (True, False)

    for expected in reversed(states[:3]):
        window.undo_scenario_edit()
        assert scen(window) == expected
    assert actions_enabled(window) == (False, True)
    window.undo_scenario_edit()  # nothing left to undo
    assert scen(window) == {}

    for expected in states[1:]:
        window.redo_scenario_edit()
        assert scen(window) == expected
    assert actions_enabled(window) == (True, False)
    window.redo_scenario_edit()  # nothing left to redo
    assert scen(window) == states[3]

    central = window.centralWidget()
    central.scenario_tab.recreate_scenario_items.assert_called()
    window.fba.assert_not_called()  # auto_fba is off


def test_undo_keeps_hash_and_metadata(window):
    appdata = window.appdata
    appdata.project.scen_values.description = "before"
    appdata.scen_values_set("EX_glc_e", (-10.0, -10.0))
    hash_after = appdata.project.scen_values.hash_value
    appdata.project.scen_values.description = "after"  # in-place edit of the current entry
    window.undo_scenario_edit()
    assert appdata.project.scen_values.description == "before"
    assert appdata.project.scen_values.hash_value == Scenario().hash_value
    window.redo_scenario_edit()
    assert appdata.project.scen_values.description == "after"
    assert appdata.project.scen_values.hash_value == hash_after


def test_new_edit_after_undo_drops_redo_tail(window):
    appdata = window.appdata
    appdata.scen_values_set("EX_glc_e", (-10.0, -10.0))
    appdata.scen_values_set("EX_o2_e", (-5.0, 0.0))
    window.undo_scenario_edit()
    window.undo_scenario_edit()
    assert actions_enabled(window) == (False, True)
    appdata.scen_values_set("EX_ac_e", (1.0, 1.0))
    assert scen(window) == {"EX_ac_e": (1.0, 1.0)}
    assert len(appdata.scenario_history) == 2
    assert actions_enabled(window) == (True, False)
    window.redo_scenario_edit()
    assert scen(window) == {"EX_ac_e": (1.0, 1.0)}
    window.undo_scenario_edit()
    assert scen(window) == {}


def test_clear_is_undoable(window):
    appdata = window.appdata
    appdata.scen_values_set_multiple(["EX_glc_e", "EX_o2_e"], [(-10.0, -10.0), (-5.0, 0.0)])
    appdata.scen_values_clear()
    assert scen(window) == {}
    window.undo_scenario_edit()
    assert scen(window) == {"EX_glc_e": (-10.0, -10.0), "EX_o2_e": (-5.0, 0.0)}


def test_auto_fba_runs_after_undo_and_redo(window):
    window.appdata.auto_fba = True
    window.appdata.scen_values_set("EX_glc_e", (-10.0, -10.0))
    window.undo_scenario_edit()
    window.redo_scenario_edit()
    assert window.fba.call_count == 2


def test_clear_history_disables_actions(window):
    window.appdata.scen_values_set("EX_glc_e", (-10.0, -10.0))
    window.undo_scenario_edit()
    assert actions_enabled(window) == (False, True)
    window.appdata.clear_scenario_history()
    assert actions_enabled(window) == (False, False)


def test_discard_failed_scenario_load(window):
    appdata = window.appdata
    appdata.scen_values_set("EX_glc_e", (-10.0, -10.0))
    # what load_scenario_file does before a load that then fails
    appdata.record_current_scenario()
    appdata.project.scen_values.clear()
    window.discard_failed_scenario_load()
    assert scen(window) == {"EX_glc_e": (-10.0, -10.0)}
    assert len(appdata.scenario_history) == 2
    assert actions_enabled(window) == (True, False)
