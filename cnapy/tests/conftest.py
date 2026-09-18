"""
Shared fixtures for CNApy's FBA/FVA CI tests.

Design notes
------------
CNApy's `MainWindow.fba()` / `MainWindow.fva()` (cnapy/gui_elements/main_window.py)
are thin Qt slots wrapped around real, non-GUI logic:

    fba() -> cnapy.core_gui.model_optimization_with_exceptions(model)  (== model.optimize())
    fva() -> cnapy.core.multi_threaded_HiGHS_FVA(model, constraints)

Rather than re-implementing that logic in tests (which would test our
re-implementation, not CNApy's), or instantiating the full MainWindow (which
drags in menus, the map view, QWebEngineView, the Jupyter console widget,
etc. - heavy and fragile in CI), these tests call the *actual* unbound
`MainWindow.fba` / `MainWindow.fva` methods on a minimal stand-in object
("FakeMainWindow") that only implements the surface those two methods
touch: `.appdata`, `.centralWidget()`, `.statusBar()`,
`.solver_status_display`, and the `set_status_*` helpers.

This exercises the exact shipped slot code (scenario loading, comp_values
population, infinite-bound handling, exception handling) while staying fast
and independent of the rest of the widget tree.

Requires: pytest, pytest-qt, cobra, qtpy (+ a Qt binding), and CNApy itself
importable (`pip install -e .` from the CNApy repo root). Run headless with:

    QT_QPA_PLATFORM=offscreen pytest tests/
"""
import hashlib
import json
import os
import sys
import types
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import cobra

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

DATA_DIR = Path(__file__).parent / "data"
ECC2_SBML = DATA_DIR / "ECC2_model.sbml.gz"
FVA_REFERENCE_JSON = DATA_DIR / "ecc2_fva_reference.json"


# ---------------------------------------------------------------------------
# Qt / import setup
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def qapp():
    """A single headless QApplication for the whole test session."""
    from qtpy.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    yield app


@pytest.fixture(autouse=True)
def no_blocking_dialogs(monkeypatch):
    """Prevent any QMessageBox from popping up (and hanging) during tests."""
    from qtpy.QtWidgets import QMessageBox
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "exec", lambda *a, **k: None)
    monkeypatch.setattr(QMessageBox, "exec_", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# Model fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def ecc2_reference_model() -> cobra.Model:
    """
    A pristine model, loaded once per session, used both as the model
    CNApy's slots operate on and as the basis for computing ground-truth
    FBA/FVA values to check them against.

    Loaded via `CNApyModel.read_sbml_model` (optlang_enumerator.cobra_cnapy)
    rather than plain `cobra.io.read_sbml_model`, matching how CNApy itself
    loads a project's model - this also runs `set_reaction_hashes()` /
    `set_stoichiometry_hash_object()` at load time, so the model arrives at
    fba()/fva() in the same state a real CNApy project's model would.
    Importing this module has the side effect of monkeypatching
    `set_hash_value()` onto `cobra.Reaction` itself, which is what lets
    `ProjectData.load_scenario_into_model()` call it unconditionally even
    though it isn't gated behind `use_results_cache` (see README).

    Never mutated directly by tests - use ecc2_reference_model.copy() if a
    test needs to change bounds.
    """
    from optlang_enumerator.cobra_cnapy import CNApyModel
    return CNApyModel.read_sbml_model(str(ECC2_SBML))


@pytest.fixture
def ecc2_model(ecc2_reference_model) -> cobra.Model:
    """A fresh copy of the ECC2 model for a test to mutate freely."""
    return ecc2_reference_model.copy()


# ---------------------------------------------------------------------------
# Cached FVA ground truth
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def fva_reference() -> dict:
    """
    Cobrapy's own FVA, precomputed once (via generate_fva_reference_data.py)
    and cached in tests/data/ecc2_fva_reference.json, rather than recomputed
    on every test run - full FVA on a 500-reaction model is ~1-2s per call
    and this file's fixture model never changes, so recomputing it every run
    (twice - unconstrained and growth-coupled) was pure waste.

    Returns a dict with keys: source_sbml_sha256, biomass_reaction_id,
    biomass_objective_value, unconstrained (rxn_id -> [min, max]),
    growth_coupled (rxn_id -> [min, max]).

    The cached file embeds a sha256 of the SBML fixture it was computed
    from; if that no longer matches the live fixture, this fails loudly
    (rather than silently comparing new code against a stale reference)
    with instructions to regenerate it.
    """
    if not FVA_REFERENCE_JSON.exists():
        pytest.fail(
            f"{FVA_REFERENCE_JSON} does not exist. Generate it once with:\n"
            f"    python tests/generate_fva_reference_data.py"
        )

    data = json.loads(FVA_REFERENCE_JSON.read_text())
    live_hash = hashlib.sha256(ECC2_SBML.read_bytes()).hexdigest()
    if data["source_sbml_sha256"] != live_hash:
        pytest.fail(
            f"{FVA_REFERENCE_JSON} was computed from a different version of "
            f"{ECC2_SBML.name} (sha256 mismatch) - the cached FVA reference "
            "is stale. Regenerate it with:\n"
            f"    python tests/generate_fva_reference_data.py"
        )
    return data


# ---------------------------------------------------------------------------
# Minimal AppData / ProjectData harness
# ---------------------------------------------------------------------------

@pytest.fixture
def appdata(qapp, ecc2_model):
    """
    A real `cnapy.appdata.AppData` + `ProjectData`, with `cobra_py_model`
    swapped for our loaded ECC2 (CNApyModel) instance. Caching is disabled
    (use_results_cache = False); this only affects whether FVA results get
    read from / written to disk, not whether reactions have hash values
    available (see ecc2_reference_model's docstring).
    """
    from cnapy.appdata import AppData

    data = AppData()
    data.project.cobra_py_model = ecc2_model
    data.project.reaction_ids.set_ids(
        ecc2_model.reactions.list_attr("id"),
        data.project.scen_values.reactions.keys(),
    )
    data.use_results_cache = False
    return data


@pytest.fixture
def mainwindow_cls():
    """The real MainWindow class, imported lazily so importing it (which
    pulls in the full cnapy.gui_elements package) only happens for tests
    that actually need it."""
    from cnapy.gui_elements.main_window import MainWindow
    return MainWindow


@pytest.fixture
def fake_main_window(appdata, mainwindow_cls):
    """
    A duck-typed stand-in for MainWindow, implementing only the attributes
    that MainWindow.fba() / MainWindow.fva() touch:

        self.appdata
        self.centralWidget()          -> object with .console, .update()
        self.statusBar()              -> object with .showMessage()
        self.solver_status_display    -> object with .setText()
        self.set_status_optimal() / set_status_infeasible() / set_status_unknown()

    Everything is a MagicMock except .appdata, so assertions can check
    `appdata.project.comp_values` (the real effect of these slots) while
    ignoring pure-UI side effects (console text, cursor, status bar).

    One important wrinkle: fba() (and fba_optimize_reaction()) don't
    populate comp_values themselves - they delegate to
    `self.process_fba_solution()`. Since `self` here is a bare MagicMock
    rather than a real MainWindow instance, leaving that attribute
    auto-mocked would make `self.process_fba_solution()` a silent no-op:
    fba() would appear to "run" and set appdata.project.solution correctly,
    but the comp_values-populating logic (which lives in
    process_fba_solution, not fba itself) would never execute. fva(), by
    contrast, populates comp_values inline and has no such delegation, which
    is why it works against a plain MagicMock without this.

    So the real, unbound `process_fba_solution` is explicitly bound onto
    this fake via `types.MethodType` - it only touches `self.appdata` (real)
    and the mocked UI attributes above, so it's safe to run for real here.
    Any other MainWindow method that a slot under test calls via
    `self.<method>()` rather than inlining its own logic needs the same
    treatment; check the slot's source before assuming a bare MagicMock is
    enough.
    """
    fake = MagicMock(name="FakeMainWindow")
    fake.appdata = appdata

    central_widget = MagicMock(name="CentralWidget")
    central_widget.console = MagicMock(name="console")
    fake.centralWidget.return_value = central_widget

    fake.statusBar.return_value = MagicMock(name="statusBar")
    fake.solver_status_display = MagicMock(name="solver_status_display")

    fake.process_fba_solution = types.MethodType(mainwindow_cls.process_fba_solution, fake)

    return fake
