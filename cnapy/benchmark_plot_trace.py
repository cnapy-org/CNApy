#!/usr/bin/env python3
"""benchmark_plot_trace.py (prototype)

Benchmarking/correctness-cross-check driver for the individual tracer
functions in plot_trace_highs.py (component-level testing against a real
cobra model), as distinct from lptools_highs.py, which is the actual
integration layer meant to replace plot_flux_space. This script builds
each HighsLp once, times sequential vs. threaded tracing, and (with
--compare-straindesign) cross-checks results against lptools.py's
existing straindesign-based tracers as a correctness sanity check
independent of the HiGHS reimplementation.

straindesign is used here only for parsing the text axis/constraint
expressions (parse_linexpr / parse_constraints), exactly as
plot_space_dialog.py / lptools.py already do -- not for solving.

Usage:
    python benchmark_plot_trace.py model.xml "1.0 EX_glc__D_e" "1.0 BIOMASS_Ecoli_core_w_GAM"
    python benchmark_plot_trace.py model.xml "EX_ac_e" "BIOMASS_Ecoli_core_w_GAM" \\
        --constraints "EX_o2_e=0" --workers 2 4 8 16 --repeats 7 --compare-straindesign
    python benchmark_plot_trace.py model.xml "1.0 EX_ac_e" "1.0 EX_etoh_e" \\
        --zaxis "1.0 BIOMASS_..." --zmin 0 --zmax 0.5 --slices 25 \\
        --yield-num "1.0 EX_etoh_e" --yield-den "-1.0 EX_glc__D_e" \\
        --boundary --compare-straindesign

model can be .xml/.sbml, .json, or .mat (anything cobra.io can load).
Axis expressions and --constraints use straindesign's own syntax (same
as typed into plot_space_dialog.py's numerator/denominator fields).

--zaxis/--zmin/--zmax/--slices benchmarks the 3D one-sliced-axis tracer;
--yield-num/--yield-den benchmarks yield min/max; --boundary (needs
--yield-num/--yield-den too) benchmarks the adaptive 2D boundary tracer
for the rate/yield mixed-axis case, using ax0 as x and the yield as y.
"""

import argparse
import time


def load_model(path):
    import cobra
    if path.endswith(".xml") or path.endswith(".sbml"):
        return cobra.io.read_sbml_model(path)
    elif path.endswith(".json"):
        return cobra.io.load_json_model(path)
    elif path.endswith(".mat"):
        return cobra.io.load_matlab_model(path)
    else:
        raise ValueError(f"Don't know how to load {path!r} -- expected .xml/.sbml, .json, or .mat")


def parse_axis(expr, reaction_ids):
    from straindesign import parse_linexpr
    d = parse_linexpr(expr, reaction_ids)
    return d[0]


def parse_constraints_arg(constraints_str, reaction_ids):
    if not constraints_str:
        return []
    from straindesign import parse_constraints
    return parse_constraints(constraints_str, reaction_ids)


def axis_label(d):
    from straindesign.parse_constr import linexprdict2str
    return linexprdict2str(d)


def median(values):
    s = sorted(values)
    return s[len(s) // 2]


def straindesign_reference(model, ax0_str, ax1_str, constraints_str):
    """Run lptools.py's existing sequential straindesign-based tracer on
    the same axes/constraints, for a correctness cross-check independent
    of the HiGHS reimplementation. Returns (vertices, elapsed_seconds),
    or None if lptools/straindesign aren't usable here (missing/
    unlicensed solver, import error, etc.) -- reported, not raised, since
    the HiGHS-side benchmark is still useful without this cross-check."""
    try:
        from straindesign import lptools
        reaction_ids = model.reactions.list_attr("id")
        ax0 = [parse_axis(ax0_str, reaction_ids)]
        ax1 = [parse_axis(ax1_str, reaction_ids)]
        constraints = parse_constraints_arg(constraints_str, reaction_ids)
        solver = lptools.select_solver(None, model)
        t0 = time.perf_counter()
        vertices = lptools._trace_polygon_rate_rate(model, [ax0, ax1], constraints, solver)
        elapsed = time.perf_counter() - t0
        return vertices, elapsed
    except Exception as exc:  # pragma: no cover -- environment-dependent
        print(f"[straindesign cross-check skipped: {exc!r}]")
        return None


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("model", help="path to a cobra-loadable model (.xml/.sbml, .json, .mat)")
    parser.add_argument("ax0", help="x-axis linear expression, e.g. '1.0 EX_glc__D_e'")
    parser.add_argument("ax1", help="y-axis linear expression, e.g. '1.0 BIOMASS_Ecoli_core_w_GAM'")
    parser.add_argument("--constraints", default="",
                        help="extra constraints, straindesign syntax, e.g. 'EX_o2_e=0'")
    parser.add_argument("--workers", type=int, nargs="+", default=[2, 4, 8],
                        help="thread counts to benchmark (default: 2 4 8)")
    parser.add_argument("--repeats", type=int, default=5,
                        help="repeats per timing, median reported (default: 5)")
    parser.add_argument("--compare-straindesign", action="store_true",
                        help="also run lptools.py's existing straindesign-based tracer, "
                             "for a correctness cross-check")
    parser.add_argument("--zaxis", default=None,
                        help="third (sliced) axis expression, e.g. 'EX_etoh_e' -- if given, "
                             "also benchmarks the 3D one-sliced-axis tracer (independent "
                             "slices in a thread pool) instead of just the 2D polygon")
    parser.add_argument("--zmin", type=float, default=None,
                        help="lower end of the sliced axis range (default: that reaction's "
                             "own lower_bound, if --zaxis names a single reaction)")
    parser.add_argument("--zmax", type=float, default=None,
                        help="upper end of the sliced axis range (default: that reaction's "
                             "own upper_bound, if --zaxis names a single reaction)")
    parser.add_argument("--slices", type=int, default=25,
                        help="number of slices along the z-axis (default: 25)")
    parser.add_argument("--yield-num", default=None,
                        help="yield numerator expression, e.g. '1.0 EX_etoh_e' -- if given "
                             "together with --yield-den, benchmarks/cross-checks "
                             "HighsYieldSolver's max and min yield against lptools.yopt()")
    parser.add_argument("--yield-den", default=None,
                        help="yield denominator expression, e.g. '-1.0 EX_glc__D_e'")
    parser.add_argument("--boundary", action="store_true",
                        help="also benchmark/cross-check trace_boundary_adaptive, using ax0 "
                             "(positional, as a rate axis) for x and --yield-num/--yield-den "
                             "for y -- the rate/yield mixed-axis case")
    args = parser.parse_args()

    print(f"loading {args.model} ...")
    model = load_model(args.model)
    print(f"{len(model.reactions)} reactions, {len(model.metabolites)} metabolites")

    from highs_lp_cache import build_rate_lp, HighsRateSolver
    from plot_trace_highs import trace_polygon_rate_rate, trace_polygon_rate_rate_parallel, polygon_area

    reaction_ids = model.reactions.list_attr("id")
    ax0 = parse_axis(args.ax0, reaction_ids)
    ax1 = parse_axis(args.ax1, reaction_ids)
    constraints = parse_constraints_arg(args.constraints, reaction_ids)
    print(f"x-axis: {axis_label(ax0)}")
    print(f"y-axis: {axis_label(ax1)}")
    if constraints:
        print(f"constraints: {args.constraints}")

    t0 = time.perf_counter()
    lp, rxn_ids, rxn_index, fix_slot_rows = build_rate_lp(model, constraints=constraints)
    t_build = time.perf_counter() - t0
    print(f"\nbuild_rate_lp: {t_build * 1000:.1f}ms (built once, shared by every trace below)")

    seq_times = []
    seq_vertices = None
    for _ in range(args.repeats):
        solver = HighsRateSolver(lp, rxn_ids, rxn_index, fix_slot_rows)
        t0 = time.perf_counter()
        seq_vertices = trace_polygon_rate_rate(solver, ax0, ax1)
        seq_times.append(time.perf_counter() - t0)
    seq_median = median(seq_times)
    seq_area = polygon_area(seq_vertices)
    print(f"\nsequential:  {len(seq_vertices):3d} vertices, area={seq_area:.6g}, "
          f"median {seq_median * 1000:.2f}ms over {args.repeats} runs "
          f"(min {min(seq_times) * 1000:.2f}ms, max {max(seq_times) * 1000:.2f}ms)")

    def area_ok(a, b):
        return abs(a - b) < 1e-4 * max(1.0, abs(b))

    for n_workers in args.workers:
        par_times = []
        par_vertices = None
        for _ in range(args.repeats):
            t0 = time.perf_counter()
            par_vertices = trace_polygon_rate_rate_parallel(
                lp, rxn_ids, rxn_index, ax0, ax1, n_workers=n_workers)
            par_times.append(time.perf_counter() - t0)
        par_median = median(par_times)
        par_area = polygon_area(par_vertices)
        speedup = seq_median / par_median if par_median > 0 else float("nan")
        tag = "OK" if area_ok(par_area, seq_area) else "MISMATCH"
        print(f"{n_workers:>2} threads: {len(par_vertices):3d} vertices, area={par_area:.6g} [{tag}], "
              f"median {par_median * 1000:.2f}ms, speedup vs sequential: {speedup:.2f}x")

    if args.compare_straindesign:
        print("\ncross-checking against lptools.py's straindesign-based tracer ...")
        ref = straindesign_reference(model, args.ax0, args.ax1, args.constraints)
        if ref is not None:
            ref_vertices, ref_elapsed = ref
            ref_area = polygon_area(ref_vertices)
            tag = "OK" if area_ok(ref_area, seq_area) else "MISMATCH"
            print(f"straindesign: {len(ref_vertices):3d} vertices, area={ref_area:.6g} "
                  f"[{tag} vs highs], {ref_elapsed * 1000:.2f}ms "
                  f"({ref_elapsed / seq_median:.1f}x the HiGHS sequential time)")

    if args.zaxis:
        print(f"\n--- 3D one-sliced-axis benchmark: z = {args.zaxis!r} ---")
        from plot_trace_highs import (trace_3d_slice_polygon, trace_3d_slice_polygon_sequential,
                                      fix_rate_axis)

        z_coeffs = parse_axis(args.zaxis, reaction_ids)
        zmin, zmax = args.zmin, args.zmax
        if zmin is None or zmax is None:
            if len(z_coeffs) == 1:
                (only_rid, only_coeff), = z_coeffs.items()
                rxn = model.reactions.get_by_id(only_rid)
                zmin = zmin if zmin is not None else min(only_coeff * rxn.lower_bound, only_coeff * rxn.upper_bound)
                zmax = zmax if zmax is not None else max(only_coeff * rxn.lower_bound, only_coeff * rxn.upper_bound)
            else:
                raise SystemExit("--zaxis is a multi-reaction expression -- pass --zmin/--zmax explicitly")
        print(f"z range: [{zmin:.6g}, {zmax:.6g}], {args.slices} slices")

        z_values = [zmin + (zmax - zmin) * i / (args.slices - 1) for i in range(args.slices)]

        lp3, rxn_ids3, rxn_index3, fix_slot_rows3 = build_rate_lp(
            model, constraints=constraints, num_fix_slots=1)
        make_fix = fix_rate_axis(z_coeffs)

        t0 = time.perf_counter()
        seq_slices = trace_3d_slice_polygon_sequential(
            lp3, rxn_ids3, rxn_index3, fix_slot_rows3, make_fix, ax0, ax1, z_values)
        t_seq3 = time.perf_counter() - t0
        total_vertices = sum(len(p) for _, p in seq_slices)
        print(f"sequential (1 solver, warm-started across slices): {t_seq3 * 1000:.1f}ms total, "
              f"{total_vertices} vertices across {args.slices} slices "
              f"({t_seq3 / args.slices * 1000:.2f}ms/slice avg)")

        for n_workers in args.workers:
            t0 = time.perf_counter()
            par_slices = trace_3d_slice_polygon(
                lp3, rxn_ids3, rxn_index3, fix_slot_rows3, make_fix, ax0, ax1, z_values,
                n_workers=n_workers)
            t_par3 = time.perf_counter() - t0
            areas_match = all(
                area_ok(polygon_area(p1), polygon_area(p2))
                for (_, p1), (_, p2) in zip(seq_slices, par_slices))
            tag = "OK" if areas_match else "MISMATCH"
            speedup = t_seq3 / t_par3 if t_par3 > 0 else float("nan")
            print(f"{n_workers:>2} threads: {t_par3 * 1000:.1f}ms total [{tag} vs sequential], "
                  f"speedup: {speedup:.2f}x")

    if args.yield_num and args.yield_den:
        print(f"\n--- yield benchmark: ({args.yield_num}) / ({args.yield_den}) ---")
        from highs_lp_cache import build_yopt_lp, HighsYieldSolver

        num_coeffs = parse_axis(args.yield_num, reaction_ids)
        den_coeffs = parse_axis(args.yield_den, reaction_ids)

        t0 = time.perf_counter()
        lp_y, rxn_ids_y, rxn_index_y, den_row, t_col, fix_rows_y = build_yopt_lp(
            model, den_coeffs, constraints=constraints)
        t_build_y = time.perf_counter() - t0
        print(f"build_yopt_lp: {t_build_y * 1000:.1f}ms")

        # which sign(s) can the denominator actually take? same check as
        # core.highs_yopt, done here on the plain rate LP already built above.
        den_tol = 1e-9
        rate_solver = HighsRateSolver(lp, rxn_ids, rxn_index, fix_slot_rows)
        status_min, min_den, _ = rate_solver.optimize(den_coeffs, "minimize")
        status_max, max_den, _ = rate_solver.optimize(den_coeffs, "maximize")
        achievable_signs = []
        if status_min == "unbounded" or (status_min == "optimal" and min_den < -den_tol):
            achievable_signs.append(-1.0)
        if status_max == "unbounded" or (status_max == "optimal" and max_den > den_tol):
            achievable_signs.append(1.0)

        if not achievable_signs:
            print("denominator is forced to 0 everywhere on the feasible region -- yield undefined")
        else:
            solver_y = HighsYieldSolver(lp_y, rxn_ids_y, rxn_index_y, den_row, t_col, fix_rows_y)
            highs_results = {}
            for sense in ("maximize", "minimize"):
                best = None
                t0 = time.perf_counter()
                for sign in achievable_signs:
                    status, value, fluxes, scalable = solver_y.optimize(num_coeffs, sense, sign)
                    if status == "optimal" and (
                            best is None or
                            (sense == "maximize" and value > best[0]) or
                            (sense == "minimize" and value < best[0])):
                        best = (value, status)
                dt = time.perf_counter() - t0
                value, status = best if best else (float("nan"), "infeasible")
                highs_results[sense] = value
                print(f"HiGHS yopt {sense}: {value:.6g} [{status}] ({dt * 1000:.2f}ms)")

            if args.compare_straindesign:
                try:
                    from straindesign import lptools
                    solver_name = lptools.select_solver(None, model)
                    for sense in ("maximize", "minimize"):
                        t0 = time.perf_counter()
                        sol = lptools.yopt(model, obj_num=num_coeffs, obj_den=den_coeffs,
                                           constraints=constraints, solver=solver_name, obj_sense=sense)
                        dt = time.perf_counter() - t0
                        tag = "OK" if area_ok(sol.objective_value, highs_results[sense]) else "MISMATCH"
                        print(f"straindesign yopt {sense}: {sol.objective_value:.6g} [{sol.status}, "
                              f"{tag} vs highs] ({dt * 1000:.2f}ms)")
                except Exception as exc:
                    print(f"[straindesign yield cross-check skipped: {exc!r}]")

    if args.boundary:
        if not (args.yield_num and args.yield_den):
            raise SystemExit("--boundary needs --yield-num and --yield-den too")
        print(f"\n--- adaptive boundary benchmark: x = ({args.ax0}) [rate], "
              f"y = ({args.yield_num})/({args.yield_den}) [yield] ---")
        from highs_lp_cache import build_rate_lp, build_yopt_lp, HighsRateSolver, HighsYieldSolver
        from plot_trace_highs import RateAxis, YieldAxis, trace_boundary_adaptive

        num_coeffs = parse_axis(args.yield_num, reaction_ids)
        den_coeffs = parse_axis(args.yield_den, reaction_ids)

        rate_lp_b, rxn_ids_b, rxn_index_b, fix_rows_b = build_rate_lp(
            model, constraints=constraints, num_fix_slots=1)
        rate_solver_b = HighsRateSolver(rate_lp_b, rxn_ids_b, rxn_index_b, fix_rows_b)

        yield_lp_b, _, _, den_row_b, t_col_b, yfix_rows_b = build_yopt_lp(
            model, den_coeffs, constraints=constraints, num_fix_slots=1)
        yield_solver_b = HighsYieldSolver(yield_lp_b, rxn_ids_b, rxn_index_b, den_row_b, t_col_b, yfix_rows_b)

        ax0_b = RateAxis(rate_solver_b, ax0)
        ax1_b = YieldAxis(rate_solver_b, yield_solver_b, num_coeffs, den_coeffs)

        b_times = []
        upper = lower = None
        for _ in range(args.repeats):
            t0 = time.perf_counter()
            upper, lower = trace_boundary_adaptive(rate_solver_b, ax0_b, ax1_b)
            b_times.append(time.perf_counter() - t0)
        b_median = median(b_times)
        print(f"HiGHS: {len(upper)} upper + {len(lower)} lower points, "
              f"median {b_median * 1000:.2f}ms over {args.repeats} runs")

        if args.compare_straindesign:
            try:
                from straindesign import lptools
                solver_name = lptools.select_solver(None, model)
                axes_sd = [[ax0], [num_coeffs, den_coeffs]]
                t0 = time.perf_counter()
                ref_upper, ref_lower = lptools._trace_boundary_adaptive(
                    model, axes_sd, ['rate', 'yield'], constraints, solver_name)
                t_sd = time.perf_counter() - t0

                def interp(boundary, x):
                    pts = sorted(boundary)
                    if not pts:
                        return None
                    if x <= pts[0][0]:
                        return pts[0][1]
                    if x >= pts[-1][0]:
                        return pts[-1][1]
                    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
                        if x0 <= x <= x1:
                            if x1 == x0:
                                return y0
                            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
                    return None

                # Direction 1: HiGHS's own x's against straindesign's curve.
                # This direction ALONE proves nothing about under-refinement:
                # with only 2 points (its own endpoints), a boundary passes
                # this check by construction even if it missed real
                # curvature everywhere in between -- it only confirms the
                # endpoints agree.
                err_1 = max((abs(y - interp(ref_upper, x)) for x, y in upper
                            if interp(ref_upper, x) is not None), default=0.0)

                # Direction 2 (the one that actually matters): straindesign's
                # x's against HiGHS's curve. If HiGHS under-refined (too few
                # points to represent real curvature), THIS is where a sparse
                # boundary shows a large error -- straindesign's interior
                # points land far from HiGHS's straight-line interpolation
                # between its own two widely-spaced points.
                err_2 = max((abs(y - interp(upper, x)) for x, y in ref_upper
                            if interp(upper, x) is not None), default=0.0)

                tag = "OK" if max(err_1, err_2) < 1e-3 else "MISMATCH (or HiGHS under-refined)"
                print(f"straindesign: {len(ref_upper)} upper + {len(ref_lower)} lower points, "
                      f"{t_sd * 1000:.2f}ms ({t_sd / b_median:.1f}x the HiGHS time)")
                print(f"  HiGHS points checked against straindesign's curve:   max error {err_1:.3g}")
                print(f"  straindesign points checked against HiGHS's curve:   max error {err_2:.3g}  <-- "
                      f"this is the one that catches under-refinement")
                print(f"  [{tag}]")
            except Exception as exc:
                print(f"[straindesign boundary cross-check skipped: {exc!r}]")


if __name__ == "__main__":
    main()
