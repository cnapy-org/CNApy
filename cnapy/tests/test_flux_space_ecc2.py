"""
Integration tests for CNApy's HiGHS-native flux/yield space plotting
(cnapy.lptools_highs) on the ECC2 fixture model, anaerobic.

Why this layer matters: PlotSpaceDialog.compute() tries
plot_flux_space_highs first and silently falls back to straindesign's
plot_flux_space on *any* exception. A broken HiGHS path is therefore
invisible in the GUI -- plots still appear, just slowly. These tests call
plot_flux_space_data_highs directly, so an exception fails the test.

What is checked, per axis combination (rate/yield, 2D/3D):
  * extents match straindesign's plot_flux_space (cached reference, see
    generate_flux_space_reference_data.py), plus area / hull volume for
    the two exact cases (2D rate/rate polygon, 3D rate/rate/rate polytope)
  * 3D meshes are closed, consistently and outwardly oriented; for the
    slice path the enclosed volume also matches the integral of the slice
    areas -- the check that exposed the folded stitching of slices whose
    rate axes differ ~100x in scale (biomass vs ethanol)
  * threaded results (n_workers=4 and the dialog's default "auto") match
    the sequential ones
  * no HiGHS solve runs on the calling thread (its scheduler stays
    untouched, see "HiGHS thread scheduler handling" in highs_lp_cache.py),
    and every worker-thread Highs() instance gets threads=1 /
    output_flag=False / log_to_console=False *before* passModel()
  * plotting still works after a default-threads HiGHS solve on the
    calling thread (as FBA/FVA/cobra run them in the GUI), and leaves that
    thread's scheduler unset for later solves (e.g. a multi-threaded MILP)
  * plot_flux_space_highs renders every case headlessly

Requires real cobra, straindesign (parsing only) and highspy.
"""
import gzip
import hashlib
import json
import math
import os
import threading as th
from collections import Counter
from pathlib import Path

import numpy as np
import pytest

from cnapy import lptools_highs as lh
from cnapy.lptools_highs import plot_flux_space_data_highs, orient_closed_mesh
from test_highs_lp_cache import default_threads_solve, in_fresh_thread

DATA_DIR = Path(__file__).parent / "data"
ECC2_SBML = DATA_DIR / "ECC2_model.sbml.gz"
REFERENCE_JSON = DATA_DIR / "ecc2_flux_space_reference.json"

CASE_NAMES = ["2d_rr", "2d_ry", "2d_yy", "3d_rrr", "3d_rry", "3d_yrr", "3d_ryy", "3d_yry"]
CASES_3D = [c for c in CASE_NAMES if c.startswith("3d")]
SLICE_CASES = ["3d_rry", "3d_yrr"]   # exactly one yield axis -> per-slice polygons
GRID_CASES = ["3d_ryy", "3d_yry"]    # two yield axes -> grid scan

# Relative to each axis's range. Observed differences on ECC2 are <= 5e-8;
# the margin is for other straindesign solvers / HiGHS versions.
EXTENT_RTOL = 1e-5

REGENERATE = "Regenerate it with:\n    python cnapy/tests/generate_flux_space_reference_data.py"


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------

def _fixture_sha256(path: Path) -> str:
    # over the decompressed SBML, as in the generator (gzip headers carry a
    # timestamp, so re-gzipping an unchanged model must not count as a change)
    data = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    return hashlib.sha256(data).hexdigest()


@pytest.fixture(scope="module")
def flux_space_reference() -> dict:
    """straindesign's plot_flux_space results plus the case definitions,
    cached in ecc2_flux_space_reference.json. Fails loudly (instead of
    comparing against a stale reference) if the fixture model changed."""
    if not REFERENCE_JSON.exists():
        pytest.fail(f"{REFERENCE_JSON} does not exist. {REGENERATE}")
    data = json.loads(REFERENCE_JSON.read_text())
    if data["source_sbml_sha256"] != _fixture_sha256(ECC2_SBML):
        pytest.fail(f"{REFERENCE_JSON.name} was computed from a different version of "
                    f"{ECC2_SBML.name} (sha256 mismatch) - the cached reference is stale. {REGENERATE}")
    missing = [c for c in CASE_NAMES if c not in data["cases"]]
    if missing:
        pytest.fail(f"{REFERENCE_JSON.name} has no entry for {missing}. {REGENERATE}")
    return data


@pytest.fixture(scope="module")
def flux_model(ecc2_reference_model):
    """One private copy for this module: the functions under test don't
    mutate the model (anaerobiosis is passed as a constraint string), but
    the session-wide reference model must never be at risk."""
    return ecc2_reference_model.copy()


@pytest.fixture(scope="module")
def compute(flux_model, flux_space_reference):
    """compute(case, n_workers=1) -> plot_flux_space_data_highs result,
    memoized per (case, n_workers) for the whole module."""
    cache = {}

    def _compute(case, n_workers=1):
        key = (case, n_workers)
        if key not in cache:
            cache[key] = plot_flux_space_data_highs(
                flux_model, _dialog_axes(flux_space_reference["cases"][case]["axes"]),
                points=flux_space_reference["points"],
                constraints=flux_space_reference["constraints"],
                n_workers=n_workers)
        return cache[key]
    return _compute


def _dialog_axes(axes):
    # JSON stores yield axes as [num, den] lists; the dialog passes tuples
    return [ax if isinstance(ax, str) else tuple(ax) for ax in axes]


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _bbox(points):
    p = np.asarray(points, dtype=float)
    return np.stack([p.min(axis=0), p.max(axis=0)], axis=1)


def _polygon_area(points):
    p = np.asarray(points, dtype=float)[:, :2]
    if len(p) > 1 and np.allclose(p[0], p[-1]):
        p = p[:-1]
    x, y = p[:, 0], p[:, 1]
    return 0.5 * abs(np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1)))


def _signed_volume(datapoints, triang):
    p = np.asarray(datapoints, dtype=float)
    t = np.asarray(triang)
    a, b, c = p[t[:, 0]], p[t[:, 1]], p[t[:, 2]]
    return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)


def _edge_stats(triang):
    undirected = Counter(frozenset(e) for t in triang for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])))
    directed = Counter(e for t in triang for e in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])))
    return undirected, sum(1 for v in directed.values() if v > 1)


def _slices(d):
    """[(yield value, ring area)] of a slice-path result, in slice order."""
    p = np.asarray(d["datapoints"], dtype=float)
    yi = d["ax_type"].index("yield")
    ri = [i for i in range(3) if i != yi]
    return [(p[ring[0], yi], _polygon_area(p[ring][:, ri])) for ring in d["slice_outlines"]]


# ---------------------------------------------------------------------------
# 1. agreement with straindesign
# ---------------------------------------------------------------------------

def _assert_extents_match(case, d, flux_space_reference):
    ref = flux_space_reference["cases"][case]
    assert d["datapoints"], f"{case}: no datapoints"
    ours, theirs = _bbox(d["datapoints"]), np.asarray(ref["bbox"], dtype=float)
    assert ours.shape == theirs.shape
    scale = np.maximum(np.abs(theirs[:, 1] - theirs[:, 0]), 1e-9)[:, None]
    worst = float(np.max(np.abs(ours - theirs) / scale))
    assert worst <= EXTENT_RTOL, (
        f"{case}: extents differ from straindesign's by up to {worst:.2e} of the axis range\n"
        f"  HiGHS:        {ours.tolist()}\n  straindesign: {theirs.tolist()}")


@pytest.mark.parametrize("case", CASE_NAMES)
def test_extents_match_straindesign(case, compute, flux_space_reference):
    _assert_extents_match(case, compute(case), flux_space_reference)


def test_rate_rate_polygon_area_matches_straindesign(compute, flux_space_reference):
    ref = flux_space_reference["cases"]["2d_rr"]["area"]
    assert _polygon_area(compute("2d_rr")["datapoints"]) == pytest.approx(ref, rel=1e-6)


def test_rate_polytope_volume_matches_straindesign(compute, flux_space_reference):
    from scipy.spatial import ConvexHull
    ref = flux_space_reference["cases"]["3d_rrr"]["hull_volume"]
    vol = ConvexHull(np.asarray(compute("3d_rrr")["datapoints"], dtype=float)).volume
    assert vol == pytest.approx(ref, rel=1e-6)


# ---------------------------------------------------------------------------
# 2. 3D mesh invariants on real output
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("case", CASES_3D)
def test_mesh_is_closed_and_outward(case, compute):
    d = compute(case)
    assert d["degen"] == "full"
    triang, closed = orient_closed_mesh(d["datapoints"], d["triang"])
    assert closed, f"{case}: mesh is not a closed surface (rendering would fall back to no culling)"
    undirected, conflicts = _edge_stats(triang)
    assert set(undirected.values()) == {2}
    assert conflicts == 0
    assert _signed_volume(d["datapoints"], triang) > 0


@pytest.mark.parametrize("case", SLICE_CASES)
def test_slice_mesh_needs_no_reorientation_and_has_no_folds(case, compute):
    """build_slice_mesh must produce the closed, outward mesh by itself
    (in either axis order) -- and its volume must match the trapezoid
    integral of the slice areas. A fold through the interior keeps the
    surface closed but breaks this volume balance."""
    d = compute(case)
    undirected, conflicts = _edge_stats(d["triang"])
    assert set(undirected.values()) == {2}, f"{case}: open or non-manifold edges"
    assert conflicts == 0, f"{case}: inconsistent winding straight out of build_slice_mesh"
    volume = _signed_volume(d["datapoints"], d["triang"])
    assert volume > 0, f"{case}: mesh faces inward"
    s = _slices(d)
    integral = sum((s[k + 1][0] - s[k][0]) * (s[k][1] + s[k + 1][1]) / 2 for k in range(len(s) - 1))
    assert volume == pytest.approx(integral, rel=0.01)


# ---------------------------------------------------------------------------
# 3. threading must not change the result
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("n_workers", [4, "auto"])
@pytest.mark.parametrize("case", GRID_CASES)
def test_grid_threaded_matches_sequential(case, n_workers, compute):
    """Same grid samples in the same order; the surface compared by
    triangle count, closedness and enclosed volume, not by triangle
    indices: the strip triangulation chooses each cell's diagonal by
    comparing two distances that are often exactly equal on a regular
    grid, so ~1e-11 noise from a different warm-start basis can flip a
    diagonal without changing the surface."""
    seq, par = compute(case, 1), compute(case, n_workers)
    np.testing.assert_allclose(np.asarray(par["datapoints"], dtype=float),
                               np.asarray(seq["datapoints"], dtype=float), rtol=0, atol=1e-8)
    assert len(par["triang"]) == len(seq["triang"])
    (t_par, closed_par), (t_seq, closed_seq) = (orient_closed_mesh(d["datapoints"], d["triang"])
                                                for d in (par, seq))
    assert closed_par and closed_seq
    assert _signed_volume(par["datapoints"], t_par) == pytest.approx(
        _signed_volume(seq["datapoints"], t_seq), rel=1e-6)


@pytest.mark.parametrize("n_workers", [4, "auto"])
@pytest.mark.parametrize("case", SLICE_CASES)
def test_slices_threaded_match_sequential(case, n_workers, compute):
    """Compared per slice by yield value and area, not vertex lists: which
    optimal vertex HiGHS returns on a tied face depends on the warm-start
    basis, so a slice can gain or lose a collinear point on an edge while
    being exactly the same polygon."""
    seq, par = _slices(compute(case, 1)), _slices(compute(case, n_workers))
    assert len(par) == len(seq)
    for (y_par, a_par), (y_seq, a_seq) in zip(par, seq):
        assert y_par == pytest.approx(y_seq, abs=1e-12)
        assert a_par == pytest.approx(a_seq, rel=1e-9, abs=1e-12)


# ---------------------------------------------------------------------------
# 4. HiGHS threads: calling thread untouched, workers threads=1 and silent
# ---------------------------------------------------------------------------

def test_every_highs_instance_configured_before_pass_model(flux_model, flux_space_reference, monkeypatch):
    """No solver may run on the calling thread (a threads=1 solve there
    would fix its HiGHS scheduler at one thread). Worker-thread solvers use
    threads=1 (the default 0 oversubscribes badly under N worker threads),
    and the logging options have to be set before passModel(). Records the
    options at the moment of every passModel() call across a sequential and
    a threaded run of the 2D, the slice and the grid path."""
    import highspy
    caller = th.current_thread()
    seen = []
    original = highspy.Highs.passModel

    def option(h, name):
        value = h.getOptionValue(name)
        return value[1] if isinstance(value, tuple) else value   # (status, value) in newer highspy

    def recording_pass_model(self, *args, **kwargs):
        seen.append((id(self), th.current_thread() is caller, option(self, "threads"),
                     option(self, "output_flag"), option(self, "log_to_console")))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(highspy.Highs, "passModel", recording_pass_model)
    ref = flux_space_reference
    for case in ("2d_ry", "3d_rry", "3d_ryy"):
        for n_workers in (1, 4):
            plot_flux_space_data_highs(flux_model, _dialog_axes(ref["cases"][case]["axes"]),
                                       points=5, constraints=ref["constraints"], n_workers=n_workers)

    assert seen, "passModel was never called -- did highspy.Highs move?"
    assert len({s[0] for s in seen}) > 6, "expected per-thread solver instances in the threaded runs"
    on_caller = [s for s in seen if s[1]]
    assert not on_caller, f"{len(on_caller)} of {len(seen)} Highs instances built on the calling thread"
    bad = [s for s in seen if s[2:] != (1, False, False)]
    assert not bad, f"{len(bad)} of {len(seen)} Highs instances not configured before passModel: {bad[:3]}"


@pytest.mark.parametrize("n_workers", [1, 4])
@pytest.mark.parametrize("case", ["2d_ry", "3d_rry"])
def test_plot_after_default_threads_solve_on_same_thread(case, n_workers, flux_model, flux_space_reference):
    """In the GUI, FBA/FVA/cobra solve with default threads on the GUI
    thread, which creates its HiGHS scheduler with the default size. The
    plot afterwards must not fail (it used to build threads=1 solvers
    there, whose runs then returned kError)."""
    ref = flux_space_reference

    def scenario():
        default_threads_solve()
        return plot_flux_space_data_highs(
            flux_model, _dialog_axes(ref["cases"][case]["axes"]), points=ref["points"],
            constraints=ref["constraints"], n_workers=n_workers)
    _assert_extents_match(case, in_fresh_thread(scenario), ref)


@pytest.mark.skipif(not os.path.isdir("/proc/self/task") or (os.cpu_count() or 1) < 4,
                    reason="counts OS threads via /proc; needs >= 4 cores for a multi-threaded default scheduler")
def test_plot_leaves_caller_scheduler_untouched(flux_model, flux_space_reference):
    """After a plot, the first default-threads solve on the calling thread
    must still create a multi-threaded scheduler (HiGHS starts its worker
    threads then). If the plot had already created a one-thread scheduler
    there, later solves on that thread (e.g. a MILP) would stay single-threaded."""
    ref = flux_space_reference

    def scenario():
        plot_flux_space_data_highs(flux_model, _dialog_axes(ref["cases"]["3d_rry"]["axes"]),
                                   points=5, constraints=ref["constraints"], n_workers=1)
        before = len(os.listdir("/proc/self/task"))
        default_threads_solve()
        return before, len(os.listdir("/proc/self/task"))
    before, after = in_fresh_thread(scenario)
    assert after > before, f"no HiGHS worker threads started ({before} -> {after} OS threads)"


def test_auto_n_workers_bounds():
    assert lh.auto_n_workers(0, 1) == 1
    assert lh.auto_n_workers(1, 1) == 1
    assert lh.auto_n_workers(100, 1, max_workers=4) <= 4
    assert lh.auto_n_workers(100, 1) <= lh._available_cpus()
    assert lh.auto_n_workers(10, 5, max_workers=64) <= 2


# ---------------------------------------------------------------------------
# 5. rendering smoke test on real data
# ---------------------------------------------------------------------------

@pytest.fixture
def agg_pyplot():
    """pyplot on Agg for one test, previous backend restored afterwards."""
    import matplotlib
    import matplotlib.pyplot as plt
    previous = matplotlib.get_backend()
    plt.switch_backend("Agg")
    yield plt
    plt.close("all")
    try:
        plt.switch_backend(previous)
    except Exception:
        pass


@pytest.mark.parametrize("case", CASE_NAMES)
def test_plot_flux_space_highs_renders(case, flux_model, flux_space_reference, agg_pyplot):
    ref = flux_space_reference
    datapoints, _, artist = lh.plot_flux_space_highs(
        flux_model, _dialog_axes(ref["cases"][case]["axes"]), points=ref["points"],
        constraints=ref["constraints"], show=False)
    assert datapoints
    artist.axes.figure.canvas.draw()   # actually rasterize, incl. the culled 3D collections
    if case.startswith("3d"):
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        meshes = [c for c in artist.axes.collections if isinstance(c, Poly3DCollection)]
        assert meshes, f"{case}: no 3D surface drawn"
    if case in SLICE_CASES + GRID_CASES:
        # closed triangle meshes are drawn with back-face culling: some, not
        # all, triangles visible (3d_rrr is drawn from its hull's face
        # polygons instead, without culling)
        culled = [c for c in meshes if hasattr(c, "_all_verts")]
        assert culled, f"{case}: closed mesh not drawn with the culled collection"
        assert 0 < len(culled[0].get_paths()) < len(culled[0]._all_verts)


@pytest.mark.parametrize("case", GRID_CASES)
def test_flat_faces_are_uniformly_coloured(case, flux_model, flux_space_reference, agg_pyplot):
    """The 2-yield meshes have a large flat bottom (yield axis at 0).
    Its normals are (0, 0, -1) up to ~1e-17 noise; a face colour built
    on atan2(n_y, n_x) turned that noise into random hues (a speckled
    face). All triangles of one flat face must get the same colour."""
    ref = flux_space_reference
    _, _, coll = lh.plot_flux_space_highs(
        flux_model, _dialog_axes(ref["cases"][case]["axes"]), points=ref["points"],
        constraints=ref["constraints"], show=False)
    verts = np.asarray(coll._all_verts, dtype=float)    # (n, 3, 3), culled collection
    colours = np.asarray(coll._all_fc, dtype=float)
    span = np.ptp(verts.reshape(-1, 3), axis=0)
    n = np.cross(verts[:, 1] - verts[:, 0], verts[:, 2] - verts[:, 0]) / np.maximum(span, 1e-12)[[1, 2, 0]] \
        / np.maximum(span, 1e-12)[[2, 0, 1]]           # normals in axis-normalized coordinates
    length = np.linalg.norm(n, axis=1)
    n = n[length > 0] / length[length > 0, None]
    colours = colours[length > 0]
    checked = 0
    for k in range(3):
        for sign in (-1, 1):
            flat = sign * n[:, k] > 1 - 1e-9
            if flat.sum() >= 10:
                checked += 1
                spread = np.ptp(colours[flat, :3], axis=0).max()
                assert spread < 1e-6, (f"{case}: {flat.sum()} triangles of the flat face normal to axis {k} "
                                       f"({'+' if sign > 0 else '-'}) span colours by {spread:.3f}")
    assert checked, f"{case}: expected at least one large flat face"

