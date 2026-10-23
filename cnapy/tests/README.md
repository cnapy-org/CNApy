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
(`cnapy.cobra_cnapy`) rather than plain `cobra.io.read_sbml_model`, so that
it matches how CNApy itself loads a project's model. The stoichiometry hash
used for the results caches (`cnapy.cobra_cnapy.stoichiometry_hash`) is
recomputed on every access, so no hash setup is needed at load time.

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

## Flux/yield space plotting (HiGHS path)

Tests for the HiGHS-native replacement of straindesign's `plot_flux_space`
(`cnapy/highs_lp_cache.py`, `cnapy/plot_trace_highs.py`,
`cnapy/lptools_highs.py`), in two layers:

- Small hand-built LPs with exactly known shapes (pentagon, cut cube and
  rescaled versions of it), one file per module:
  `test_highs_lp_cache.py`, `test_plot_trace_highs.py`,
  `test_trace_3d_slice.py`, `test_trace_boundary_adaptive.py`,
  `test_trace_grid_3d.py`, `test_trace_polytope_3d.py`,
  `test_slice_mesh.py`, `test_lptools_highs.py`,
  `test_lptools_highs_render.py`. They include regression tests for bugs
  found while building this: solver fix-row state leaking between repeated
  traces and between grid x-slices, folded slice stitching, and
  threaded-vs-sequential equality.
- `test_flux_space_ecc2.py` on the ECC2 fixture (anaerobic, 8 rate/yield
  axis combinations in 2D and 3D): extents against straindesign's own
  `plot_flux_space`, closed and outward-oriented 3D meshes, threaded runs
  (`n_workers=4` and the default `"auto"`) equal to sequential ones, flat
  faces uniformly coloured, and headless rendering. Also the HiGHS thread
  handling (next section).

Why the ECC2 layer matters: `PlotSpaceDialog.compute()` falls back to
straindesign's `plot_flux_space` on *any* exception from the HiGHS path, so
a broken HiGHS path never shows up in the GUI (plots still appear, just
slowly). These tests call `plot_flux_space_data_highs` directly.

### HiGHS thread scheduler

HiGHS keeps one task scheduler per OS thread. The first `run()` on a thread
creates it, sized by that run's `threads` option (default 0 = half the
cores), and it is never resized: later runs on that thread must use
`threads=0` or exactly that size, otherwise `run()` returns `kError`. FBA,
FVA and cobra/optlang solve with the default on the GUI thread, so
`plot_flux_space_data_highs` runs all its solves on fresh
`highs_lp_cache.worker_pool` threads with `threads=1`, and leaves the GUI
thread's scheduler untouched. That way the plot works after any other solve,
and a later solve on the GUI thread (e.g. a MILP) still gets a
multi-threaded scheduler. Tests: `test_highs_lp_cache.py::TestThreadScheduler`
and section 4 of `test_flux_space_ecc2.py` (no solver on the calling thread,
plotting after a default-threads solve, and an OS-thread count check that
the caller's scheduler is still unset).

No fakes: everything runs against the real cobra, straindesign (only used
for parsing axis/constraint expressions) and highspy. Rendering tests switch
pyplot to Agg only for their own duration (or draw on an explicit Agg
canvas), so the Qt tests' backend is untouched.

### Cached straindesign reference data

straindesign takes ~1 min for all cases (20 s for one 2-yield 3D case, with
~1 GB peak memory at higher resolution), so its results are precomputed into
`tests/data/ecc2_flux_space_reference.json`, the same way as the FVA
reference. The JSON also holds the case definitions (axes, constraints,
points) -- add or change a case in the generator only.

- `tests/generate_flux_space_reference_data.py` (manually run, not part of
  `pytest`) produces it: `python cnapy/tests/generate_flux_space_reference_data.py [--solver ...]`
- It stores a sha256 of the *decompressed* `ECC2_model.sbml.gz` (gzip
  headers carry a timestamp, so re-gzipping an unchanged model doesn't
  invalidate the cache). The `flux_space_reference` fixture fails loudly
  if the model changed without regenerating.
- Extents are compared with a relative tolerance of 1e-5 of each axis range
  (observed differences: <= 5e-8), so regenerating with a different
  straindesign solver is fine.
