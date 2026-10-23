"""Generates tests/data/ecc2_flux_space_reference.json, the straindesign
ground truth for test_flux_space_ecc2.py (manually run, not part of pytest).

Same idea as generate_fva_reference_data.py: straindesign's own
plot_flux_space is the independent reference for CNApy's HiGHS-native
lptools_highs.plot_flux_space_data_highs, but it is slow (and memory-hungry
on the 2-yield grid cases), so it is run once here and cached instead of on
every test run.

The JSON also holds the case definitions themselves (axes, constraints,
points), so this file is the single place to add or change a case; the
test reads them back from the JSON.

What is stored per case, and why:
  bbox         per-axis (min, max) over straindesign's datapoints -- every
               path, exact or approximate, has to reproduce the plot's
               extents (these are LP optima, independent of meshing)
  area         2D rate/rate only: exact polygon, so its area must match too
  hull_volume  3D rate/rate/rate only: exact polytope, convex-hull volume
Facet counts and triangulations are deliberately NOT stored: the two
implementations don't have to mesh the same way.

The fixture hash is taken over the *decompressed* SBML, so re-gzipping the
same model (gzip headers carry a timestamp) doesn't invalidate the cache;
editing the model does.

Run from the repo root:
    python cnapy/tests/generate_flux_space_reference_data.py [--solver glpk|cplex|gurobi|scip]
"""
import argparse
import gzip
import hashlib
import json
import time
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
ECC2_SBML = DATA_DIR / "ECC2_model.sbml.gz"
REFERENCE_JSON = DATA_DIR / "ecc2_flux_space_reference.json"

BM, ETOH, SUCC, GLC = "Ec_biomass_iJO1366_core_53p95M", "EX_etoh_e", "EX_succ_e", "EX_glc_e"
CONSTRAINTS = "EX_o2_e = 0"   # anaerobic, as in the ECC2anaerob benchmarks
POINTS = 12                   # low enough for CI; the dialog default is 20


def _rate(rid):
    return "1.0 " + rid


def _yield(rid):
    return ["1.0 " + rid, "-1.0 " + GLC]   # list, not tuple: survives the JSON round trip unchanged


# axes in the form PlotSpaceDialog passes them: a string for a rate axis,
# a (numerator, denominator) pair for a yield axis
CASES = {
    "2d_rr":  [_rate(BM), _rate(ETOH)],                 # exact polygon
    "2d_ry":  [_rate(BM), _yield(ETOH)],                # adaptive boundary
    "2d_yy":  [_yield(ETOH), _yield(SUCC)],             # adaptive boundary, two yields
    "3d_rrr": [_rate(BM), _rate(ETOH), _rate(SUCC)],    # exact polytope
    "3d_rry": [_rate(BM), _rate(ETOH), _yield(SUCC)],   # slices along the yield axis
    "3d_yrr": [_yield(SUCC), _rate(BM), _rate(ETOH)],   # same, yield as axis 0 (mesh handedness flip)
    "3d_ryy": [_rate(BM), _yield(ETOH), _yield(SUCC)],  # grid scan
    "3d_yry": [_yield(ETOH), _rate(BM), _yield(SUCC)],  # grid scan, axis 0 pinned as a yield
}


def fixture_sha256(path: Path) -> str:
    data = gzip.decompress(path.read_bytes()) if path.suffix == ".gz" else path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def load_model(path: Path):
    try:  # same loader as conftest.py's ecc2_reference_model
        from cnapy.cobra_cnapy import CNApyModel
        return CNApyModel.read_sbml_model(str(path))
    except ImportError:
        import cobra
        return cobra.io.read_sbml_model(str(path))


def bbox(points):
    pts = [[float(v) for v in p] for p in points]
    return [[min(p[k] for p in pts), max(p[k] for p in pts)] for k in range(len(pts[0]))]


def polygon_area(points):
    pts = [(float(p[0]), float(p[1])) for p in points]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1]
                   for i in range(len(pts)))) / 2.0


def _package_version(name):
    try:
        from importlib.metadata import version
        return version(name)
    except Exception:
        return "unknown"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--solver", default=None, help="straindesign solver (default: straindesign's own choice)")
    args = ap.parse_args()

    import matplotlib
    matplotlib.use("Agg")   # standalone script: switching the backend globally is fine here
    import matplotlib.pyplot as plt
    import numpy as np
    from scipy.spatial import ConvexHull
    from straindesign import plot_flux_space, select_solver

    model = load_model(ECC2_SBML)
    solver = select_solver(args.solver, model)
    extra = {"solver": solver}

    out = {
        "source_sbml_sha256": fixture_sha256(ECC2_SBML),
        "straindesign_version": _package_version("straindesign"),
        "straindesign_solver": solver,
        "constraints": CONSTRAINTS,
        "points": POINTS,
        "cases": {},
    }
    for name, axes in CASES.items():
        t0 = time.perf_counter()
        sd_axes = [ax if isinstance(ax, str) else tuple(ax) for ax in axes]
        datapoints, _, _ = plot_flux_space(model, sd_axes, points=POINTS, constraints=CONSTRAINTS,
                                           show=False, **extra)
        plt.close("all")
        entry = {"axes": axes, "bbox": bbox(datapoints)}
        if name == "2d_rr":
            entry["area"] = polygon_area(datapoints)
        if name == "3d_rrr":
            entry["hull_volume"] = float(ConvexHull(np.asarray(datapoints, dtype=float)).volume)
        out["cases"][name] = entry
        print(f"{name}: {time.perf_counter() - t0:.1f}s")

    REFERENCE_JSON.write_text(json.dumps(out, indent=2) + "\n")
    print(f"wrote {REFERENCE_JSON}")


if __name__ == "__main__":
    main()
