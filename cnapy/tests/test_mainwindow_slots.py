"""
Tests that exercise the real, shipped `MainWindow.fba()` and
`MainWindow.fva()` slot implementations (cnapy/gui_elements/main_window.py),
rather than the bare computational functions they wrap (see
test_core_units.py for that layer).

Approach: call the *unbound* method with a minimal "FakeMainWindow" object
(see conftest.py's `fake_main_window` fixture) that implements only the
attributes these two methods touch. This runs CNApy's actual scenario
handling / comp_values population / infinite-bound conversion / exception
handling exactly as shipped, without constructing the full MainWindow
(menus, map view, embedded Jupyter console, QWebEngineView, ...), which is
both slow and drags in optional dependencies unrelated to FBA/FVA.

If your CI environment can afford it, `test_mainwindow_slots_real_window.py`
(sketched at the bottom of this file, skipped by default) shows how to do
the same thing against a fully constructed MainWindow instead, for a
higher-fidelity (but much heavier and more fragile) end-to-end check.
"""
import pytest
import qtpy.QtWebEngineWidgets 

def test_fba_slot_populates_comp_values(fake_main_window, mainwindow_cls):
    mainwindow_cls.fba(fake_main_window)

    appdata = fake_main_window.appdata
    reference = appdata.project.cobra_py_model.copy().optimize()

    assert appdata.project.solution is not None, (
        "appdata.project.solution is None - model_optimization_with_exceptions() "
        "swallowed an exception from model.optimize() (see cnapy/core_gui.py: it "
        "catches Exception broadly and only re-surfaces community-license errors; "
        "any other solver exception is silently discarded). Temporarily patch "
        "cnapy.gui_elements.main_window.model_optimization_with_exceptions with "
        "a version that re-raises to see the real traceback."
    )
    assert appdata.project.solution.status == "optimal", (
        f"unexpected solver status: {appdata.project.solution.status}"
    )
    assert appdata.project.comp_values, "fba() left comp_values empty"
    for rxn_id, flux in reference.fluxes.items():
        lo, hi = appdata.project.comp_values[rxn_id]
        assert lo == hi == pytest.approx(flux, abs=1e-6)

    # process_fba_solution() is expected to trigger exactly one redraw
    fake_main_window.centralWidget().update.assert_called()


def test_fba_slot_surfaces_optimize_exception(fake_main_window, mainwindow_cls, monkeypatch):
    """
    Diagnostic test: bypasses model_optimization_with_exceptions()'s broad
    except-and-swallow (cnapy/core_gui.py) so that if model.optimize() is
    actually raising in this environment, the real traceback shows up here
    instead of silently producing an empty comp_values later.

    If this test fails, the printed traceback is the true root cause of any
    other fba()-related failures in this file - fix that first, independent
    of anything scenario- or comp_values-related.
    """
    import cnapy.gui_elements.main_window as mw

    def reraising_optimize(model):
        return model.optimize()  # no try/except - let it raise

    monkeypatch.setattr(mw, "model_optimization_with_exceptions", reraising_optimize)

    mainwindow_cls.fba(fake_main_window)  # should not raise if optimize() truly succeeds
    assert fake_main_window.appdata.project.solution.status == "optimal"


def test_fba_slot_reports_infeasible_scenario(fake_main_window, mainwindow_cls):
    appdata = fake_main_window.appdata
    biomass = next(
        r for r in appdata.project.cobra_py_model.reactions
        if r.objective_coefficient != 0
    )
    # An infeasible scenario: force growth but block every exchange.
    appdata.project.scen_values[biomass.id] = (1.0, 1000.0)
    for ex in appdata.project.cobra_py_model.exchanges:
        appdata.project.scen_values[ex.id] = (0.0, 0.0)

    mainwindow_cls.fba(fake_main_window)

    assert appdata.project.comp_values == {}, (
        "fba() should clear comp_values on an infeasible scenario"
    )


def test_fba_slot_respects_scenario_bounds(fake_main_window, mainwindow_cls):
    """A scenario that fixes one exchange reaction's flux should be
    reflected in the optimized solution CNApy reports."""
    appdata = fake_main_window.appdata
    model = appdata.project.cobra_py_model
    glc_ex = next((r for r in model.exchanges if "glc" in r.id.lower()), None)
    if glc_ex is None:
        pytest.skip("ECC2 fixture has no glucose exchange reaction to pin")

    fixed_uptake = -5.0
    appdata.project.scen_values[glc_ex.id] = (fixed_uptake, fixed_uptake)

    mainwindow_cls.fba(fake_main_window)

    assert appdata.project.comp_values, (
        "comp_values is empty - fba() did not produce a solution at all "
        "(see test_fba_slot_surfaces_optimize_exception for why)"
    )
    lo, hi = appdata.project.comp_values[glc_ex.id]
    assert lo == hi == pytest.approx(fixed_uptake, abs=1e-6)


def test_fva_slot_populates_comp_values_as_bounds(fake_main_window, mainwindow_cls):
    mainwindow_cls.fva(fake_main_window)

    appdata = fake_main_window.appdata
    assert appdata.project.comp_values_type == 1  # 1 == bounds/FVA result
    assert appdata.project.comp_values, "fva() left comp_values empty"

    for rxn in appdata.project.cobra_py_model.reactions:
        lo, hi = appdata.project.comp_values[rxn.id]
        assert lo <= hi + 1e-7

    # fva_values is documented to be a persisted copy of the FVA comp_values
    assert appdata.project.fva_values == appdata.project.comp_values


def test_fva_slot_matches_core_units_reference(fake_main_window, mainwindow_cls, ecc2_reference_model):
    """Cross-check the slot's output against the same cobrapy ground truth
    used in test_core_units.py, closing the loop between the two test
    layers on at least one model."""
    import cobra
    from test_core_units import _finite_bounds_model

    mainwindow_cls.fva(fake_main_window)
    appdata = fake_main_window.appdata

    ref_model = _finite_bounds_model(ecc2_reference_model)
    reference = cobra.flux_analysis.flux_variability_analysis(
        ref_model, fraction_of_optimum=0.0, processes=1
    )

    for rxn_id in reference.index:
        lo, hi = appdata.project.comp_values[rxn_id]
        assert lo == pytest.approx(reference.loc[rxn_id, "minimum"], abs=1e-4)
        assert hi == pytest.approx(reference.loc[rxn_id, "maximum"], abs=1e-4)


def test_fva_slot_reports_infeasible_scenario(fake_main_window, mainwindow_cls):
    appdata = fake_main_window.appdata
    biomass = next(
        r for r in appdata.project.cobra_py_model.reactions
        if r.objective_coefficient != 0
    )
    appdata.project.scen_values.constraints.append(
        ({biomass.id: 1.0}, ">=", 1e6)  # unachievable
    )

    # Should not raise out of the slot - fva() is expected to catch
    # cobra.exceptions.Infeasible internally and show a QMessageBox instead
    # (suppressed by the no_blocking_dialogs autouse fixture).
    mainwindow_cls.fva(fake_main_window)

    assert appdata.project.comp_values == {}


# ---------------------------------------------------------------------------
# Optional, heavier end-to-end variant against a real MainWindow instance.
# Skipped by default: constructing MainWindow pulls in the full gui_elements
# package (menus, MapView, EscherMapView/QWebEngineView, the embedded
# Jupyter console, StrainDesign dialogs, ...) and its constructor signature
# isn't reproduced here. Un-skip and fill in the constructor call once you
# know what MainWindow.__init__ needs in your checked-out version (it takes
# at least an AppData; check the current signature in main_window.py).
# ---------------------------------------------------------------------------

@pytest.mark.skip(reason="requires the full MainWindow constructor call to be filled in")
def test_fba_via_real_main_window(qapp, appdata):
    from cnapy.gui_elements.main_window import MainWindow

    window = MainWindow(appdata)  # <- adjust to the real constructor signature
    window.fba()
    reference = appdata.project.cobra_py_model.copy().optimize()
    for rxn_id, flux in reference.fluxes.items():
        lo, hi = appdata.project.comp_values[rxn_id]
        assert lo == hi == pytest.approx(flux, abs=1e-6)
