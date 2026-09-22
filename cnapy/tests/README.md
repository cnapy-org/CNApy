# CNApy FBA/FVA CI tests

Two layers of coverage for `MainWindow.fba()` / `MainWindow.fva()`
(cnapy/gui_elements/main_window.py):

- `test_core_units.py` — fast, Qt-free unit tests of the actual functions
  those slots delegate to (`cnapy.core_gui.model_optimization_with_exceptions`,
  `cnapy.core.multi_threaded_HiGHS_FVA`), checked against cobrapy's own
  `optimize()` / `flux_variability_analysis()` as ground truth on the ECC2
  model.
- `test_mainwindow_slots.py` — calls the real, unbound `MainWindow.fba` /
  `MainWindow.fva` methods against a minimal duck-typed stand-in object
  (`fake_main_window` fixture) that only implements the attributes those
  methods touch (`.appdata`, `.centralWidget()`, `.statusBar()`,
  `.solver_status_display`). This exercises the actual shipped scenario
  handling / comp_values population / infinite-bound conversion without
  constructing the full MainWindow (menus, map view, embedded console,
  QWebEngineView, ...).

## Setup

These tests assume CNApy's own dependencies (per `pyproject.toml`) are
installed — `cobra`, `gurobipy`, `optlang_enumerator`, `efmtool_link`,
`straindesign`, `highspy`, `qtpy` + a Qt binding, etc. — plus `pytest` and
`pytest-qt`:

```bash
pip install -e /path/to/CNApy   # cnapy itself, editable
pip install pytest pytest-qt
QT_QPA_PLATFORM=offscreen pytest tests/ -v
```

## A design detail worth knowing

The ECC2 fixture is loaded via `CNApyModel.read_sbml_model`
(`optlang_enumerator.cobra_cnapy`) rather than plain
`cobra.io.read_sbml_model`, for two reasons:

1. It matches how CNApy itself loads a project's model, so the model
   arrives at `fba()`/`fva()` in realistic state (reaction/stoichiometry
   hashes already set).
2. Importing `optlang_enumerator.cobra_cnapy` has the side effect of
   monkeypatching `set_hash_value()` onto `cobra.Reaction` itself (see that
   module's source) — which is what lets
   `ProjectData.load_scenario_into_model()` call
   `reaction.set_hash_value()` unconditionally on any scenario-touched
   reaction, even with `use_results_cache=False`. Since `cnapy.appdata`
   already imports `CNApyModel` at module level, this patch is in effect
   as soon as any test imports anything from `cnapy`, but using
   `CNApyModel.read_sbml_model` directly keeps the fixture's provenance
   explicit rather than relying on that import-order side effect implicitly.

## Extending

- `test_mainwindow_slots.py` ends with a skipped
  `test_fba_via_real_main_window` sketch for a full end-to-end test against
  an actual constructed `MainWindow` — un-skip and fill in the constructor
  call if you want that heavier layer too; I didn't have `MainWindow.__init__`
  in front of me to get the signature right.
- The bundled fixture (`tests/data/ECC2_model.sbml`) is the SBML model from
  `cnapy-org/CNApy-projects`' ECC2 release asset (500 reactions, 487
  metabolites) — a genome-scale-ish model, good for catching real numerical
  issues that a toy 3-reaction model would miss.

## Cached FVA reference data

`test_fva_unconstrained_matches_cobrapy` and
`test_fva_with_growth_constraint_matches_cobrapy` check
`multi_threaded_HiGHS_FVA` against cobrapy's own `flux_variability_analysis`
as ground truth. Since the ECC2 fixture model never changes, that reference
is precomputed once and cached in `tests/data/ecc2_fva_reference.json`
(~1–2s of cobrapy FVA, twice, saved on every test run) rather than
recomputed by the tests themselves.

- `tests/generate_fva_reference_data.py` is the (manually run, not part of
  `pytest`) script that produced it.
- The cached JSON embeds a sha256 of `ECC2_model.sbml`. The `fva_reference`
  fixture in `conftest.py` checks that hash on every test run and fails
  loudly — rather than silently comparing against a stale reference — if
  the fixture model has changed without regenerating the cache.
- If you ever swap in a different/updated fixture model, regenerate with:

  ```bash
  python tests/generate_fva_reference_data.py
  ```