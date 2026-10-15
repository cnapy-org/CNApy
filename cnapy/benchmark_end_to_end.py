#!/usr/bin/env python3
"""benchmark_end_to_end.py

End-to-end timing of lptools_highs.plot_flux_space_highs against
straindesign's lptools.plot_flux_space, the way the PlotSpaceDialog calls
them (axes as strings / (num, den) tuples, points=20 by default), with
no plot window: matplotlib runs on the Agg backend and show=False, so the
time measured is computation + figure building, not time until a window
is closed.

For HiGHS three numbers are reported per case:
  data    plot_flux_space_data_highs only (LP work + meshing)
  full    plot_flux_space_highs with show=False (data + matplotlib)
and, per --workers value, the data time with that thread count.
straindesign is timed with plot_flux_space(show=False).

A cheap correctness cross-check is printed as well: the bounding box
of each result's datapoints (max relative difference of the 6 or 4
extents, relative to the axis range). Mesh/facet differences are
expected; extent differences beyond ~1e-3 are worth a look.

Usage:
    python benchmark_end_to_end.py ECC2anaerob.sbml
    python benchmark_end_to_end.py ECC2anaerob.sbml --points 20 30 --repeats 5 --workers 1 2 4 8
    python benchmark_end_to_end.py textbook --anaerobic        # cobra's bundled E. coli core
    python benchmark_end_to_end.py model.xml --cases 3d_rry 3d_ryy --skip-straindesign

Default reaction IDs are the ECC2 ones; for the bundled 'textbook'
model the E. coli core IDs are substituted automatically. Override with
--bm/--p1/--p2/--sub.
"""

import argparse
import gc
import statistics
import time

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


ECC2_IDS = dict(bm="Ec_biomass_iJO1366_core_53p95M", p1="EX_etoh_e", p2="EX_succ_e", sub="EX_glc_e")
TEXTBOOK_IDS = dict(bm="Biomass_Ecoli_core", p1="EX_etoh_e", p2="EX_succ_e", sub="EX_glc__D_e")


def make_cases(bm, p1, p2, sub):
    r = lambda x: f"1.0 {x}"
    y = lambda x: (f"1.0 {x}", f"-1.0 {sub}")
    return {
        "2d_rr":  [r(bm), r(p1)],
        "2d_ry":  [r(bm), y(p1)],
        "2d_yy":  [y(p1), y(p2)],
        "3d_rrr": [r(bm), r(p1), r(p2)],
        "3d_rry": [r(bm), r(p1), y(p2)],
        "3d_ryy": [r(bm), y(p1), y(p2)],
    }


def load_model(path, anaerobic):
    import cobra
    if path == "textbook":
        from cobra.io import load_model as lm
        m = lm("textbook")
    elif path.endswith((".xml", ".sbml")):
        m = cobra.io.read_sbml_model(path)
    elif path.endswith(".json"):
        m = cobra.io.load_json_model(path)
    elif path.endswith(".mat"):
        m = cobra.io.load_matlab_model(path)
    else:
        raise ValueError(f"don't know how to load {path!r}")
    if anaerobic:
        m.reactions.get_by_id("EX_o2_e").lower_bound = 0.0
    return m


def timed(fn, repeats):
    """Median wall time of `repeats` calls (after one untimed warm-up
    call, so imports / first-use costs don't land in the first case),
    plus the last result."""
    fn()
    plt.close("all")
    times, res = [], None
    for _ in range(repeats):
        gc.collect()
        t = time.perf_counter()
        res = fn()
        times.append(time.perf_counter() - t)
        plt.close("all")
    return statistics.median(times), res


def bbox(points):
    pts = [list(map(float, p)) for p in points]
    if not pts:
        return None
    n = len(pts[0])
    return [(min(p[k] for p in pts), max(p[k] for p in pts)) for k in range(n)]


def bbox_diff(a, b):
    if a is None or b is None or len(a) != len(b):
        return float("nan")
    worst = 0.0
    for (alo, ahi), (blo, bhi) in zip(a, b):
        rng = max(abs(ahi - alo), abs(bhi - blo), 1e-9)
        worst = max(worst, abs(alo - blo) / rng, abs(ahi - bhi) / rng)
    return worst


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("model", help="model file, or 'textbook' for cobra's bundled E. coli core")
    ap.add_argument("--cases", nargs="+", default=None, help="subset of: 2d_rr 2d_ry 2d_yy 3d_rrr 3d_rry 3d_ryy")
    ap.add_argument("--points", type=int, nargs="+", default=[20], help="resolution(s); dialog default is 20")
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--workers", type=int, nargs="+", default=[1, 4],
                    help="n_workers values for the HiGHS data timing, 0 means 'auto'")
    ap.add_argument("--constraints", default="", help="passed to both, straindesign syntax")
    ap.add_argument("--solver", default=None, help="straindesign solver (glpk, cplex, gurobi, scip)")
    ap.add_argument("--skip-straindesign", action="store_true")
    ap.add_argument("--anaerobic", action="store_true", help="set EX_o2_e lower bound to 0")
    for k in ("bm", "p1", "p2", "sub"):
        ap.add_argument(f"--{k}", default=None)
    args = ap.parse_args()

    ids = dict(TEXTBOOK_IDS if args.model == "textbook" else ECC2_IDS)
    ids.update({k: getattr(args, k) for k in ids if getattr(args, k)})
    model = load_model(args.model, args.anaerobic)
    missing = [v for v in ids.values() if v not in model.reactions]
    if missing:
        raise SystemExit(f"reaction(s) not in model: {missing} -- use --bm/--p1/--p2/--sub")

    from lptools_highs import plot_flux_space_data_highs, plot_flux_space_highs
    if not args.skip_straindesign:
        from straindesign.lptools import plot_flux_space

    cases = make_cases(**ids)
    names = args.cases or list(cases)
    extra = {"constraints": args.constraints} if args.constraints else {}
    sd_extra = dict(extra, **({"solver": args.solver} if args.solver else {}))

    args.workers = [w if w > 0 else "auto" for w in args.workers]
    wcols = "".join(f"  data w={w:<3}" if w != "auto" else "  data auto " for w in args.workers)
    print(f"model={args.model}  repeats={args.repeats} (median)  times in s")
    print(f"{'case':8} {'pts':>4}{wcols}  {'full':>8}  {'straindesign':>12}  {'speedup':>7}  {'bbox Δ':>8}")
    for pts in args.points:
        for name in names:
            axes = cases[name]
            row = f"{name:8} {pts:>4}"
            try:
                d = None
                for w in args.workers:
                    t, d = timed(lambda: plot_flux_space_data_highs(model, axes, points=pts, n_workers=w, **extra),
                                 args.repeats)
                    row += f"  {t:11.3f}"
                t_full, _ = timed(lambda: plot_flux_space_highs(model, axes, points=pts, show=False,
                                                                n_workers=args.workers[0], **extra), args.repeats)
                row += f"  {t_full:8.3f}"
                hb = bbox(d["datapoints"])
            except Exception as e:  # report and keep going
                print(row + f"  HiGHS FAILED: {e!r}")
                continue
            if args.skip_straindesign:
                print(row)
                continue
            try:
                t_sd, res = timed(lambda: plot_flux_space(model, axes, points=pts, show=False, **sd_extra),
                                  args.repeats)
                diff = bbox_diff(hb, bbox(res[0]))
                row += f"  {t_sd:12.3f}  {t_sd / t_full:6.1f}x  {diff:8.1e}"
            except Exception as e:
                row += f"  straindesign FAILED: {e!r}"
            print(row, flush=True)


if __name__ == "__main__":
    main()
