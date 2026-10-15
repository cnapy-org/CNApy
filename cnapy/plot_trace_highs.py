"""cnapy/plot_trace_highs.py (prototype)

HiGHS-native reimplementation of lptools._trace_polygon_rate_rate (exact
convex polygon boundary for two *rate* axes), built on
highs_lp_cache.HighsRateSolver instead of straindesign's fba(). Two
variants:

  - trace_polygon_rate_rate(): sequential, same recursive normal-bisection
    algorithm as lptools.py, same result up to floating-point tie-breaking
    in which vertex HiGHS returns for a degenerate (multi-optimal) face.
    Already benefits from build-once/incremental reuse even with zero
    threading (~13x per the person's own benchmark of the underlying
    optimize() pattern).

  - trace_polygon_rate_rate_parallel(): same algorithm restructured as
    breadth-first "waves" instead of depth-first recursion -- each wave
    refines every currently-too-coarse edge concurrently via a small
    thread pool, then decides which sub-edges need another wave, until
    stable. Each worker thread gets its own HighsRateSolver (built from
    the same read-only HighsLp) via threading.local(), never shares one
    across threads. Produces the same vertex set as the sequential
    version, in the same polygon order.

Both expect the caller to have already built `lp` via
highs_lp_cache.build_rate_lp(cobra_model, constraints=<baseline
constraints for the whole trace>, num_fix_slots=0) -- baseline
constraints are baked into the LP at build time, not passed per call,
since they're constant for the whole trace (this is exactly the
build-once contract highs_lp_cache is designed around).
"""

import math
import threading as th
from typing import Dict, List, Optional, Tuple

import numpy

from cnapy.highs_lp_cache import HighsRateSolver, HighsYieldSolver


def _project(status: str, fluxes: Optional[Dict[str, float]],
             ax0: Dict[str, float], ax1: Dict[str, float]) -> Optional[Tuple[float, float]]:
    if status != "optimal" or fluxes is None:
        return None
    x0 = sum(c * fluxes.get(r, 0.0) for r, c in ax0.items())
    x1 = sum(c * fluxes.get(r, 0.0) for r, c in ax1.items())
    return (round(x0, 9), round(x1, 9))


def _dedupe(points: List[Tuple[float, float]], tol: float) -> List[Tuple[float, float]]:
    unique_pts: List[Tuple[float, float]] = []
    for p in points:
        if not any(abs(p[0] - q[0]) < tol and abs(p[1] - q[1]) < tol for q in unique_pts):
            unique_pts.append(p)
    return unique_pts


def _order_ccw(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    return sorted(points, key=lambda p: math.atan2(p[1] - cy, p[0] - cx)), cx, cy


def _refine_step(vi, vj, cx, cy, ax0, ax1, opt_fn):
    """One normal-bisection refinement attempt on edge (vi, vj).
    Returns ('done', vi) if the edge is already tight enough / degenerate,
    or ('split', (vi, p_new), (p_new, vj)) if a new vertex was found."""
    dx, dy = vj[0] - vi[0], vj[1] - vi[1]
    nx, ny = dy, -dx  # rotate 90 degrees
    mid_x, mid_y = (vi[0] + vj[0]) / 2, (vi[1] + vj[1]) / 2
    if nx * (mid_x - cx) + ny * (mid_y - cy) < 0:
        nx, ny = -nx, -ny
    obj: Dict[str, float] = {}
    for r, c in ax0.items():
        obj[r] = obj.get(r, 0.0) + nx * c
    for r, c in ax1.items():
        obj[r] = obj.get(r, 0.0) + ny * c
    p_new = opt_fn(obj, "maximize")
    return vi, vj, nx, ny, p_new


def trace_polygon_rate_rate(solver: HighsRateSolver, ax0: Dict[str, float], ax1: Dict[str, float],
                            tol: float = 1e-8, max_depth: int = 50) -> List[Tuple[float, float]]:
    """Sequential, depth-first version -- direct port of
    lptools._trace_polygon_rate_rate onto a build-once HighsRateSolver."""

    def opt(obj, sense):
        status, _, fluxes = solver.optimize(obj, sense)
        return _project(status, fluxes, ax0, ax1)

    extremes = []
    for coeff, sense in [(ax0, "maximize"), (ax0, "minimize"), (ax1, "maximize"), (ax1, "minimize")]:
        p = opt(coeff, sense)
        if p is not None:
            extremes.append(p)

    if len(extremes) < 2:
        return extremes if extremes else [(0.0, 0.0)]

    unique_pts = _dedupe(extremes, tol)
    if len(unique_pts) == 1:
        return unique_pts

    unique_pts, cx, cy = _order_ccw(unique_pts)

    diameter = max(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5 for a in unique_pts for b in unique_pts)
    min_edge = 1e-10 * diameter if diameter > 0 else 1e-10

    def _refine(vi, vj, depth):
        if depth > max_depth:
            return [vi]
        edge_len = ((vi[0] - vj[0]) ** 2 + (vi[1] - vj[1]) ** 2) ** 0.5
        if edge_len < min_edge:
            return [vi]
        vi_, vj_, nx, ny, p_new = _refine_step(vi, vj, cx, cy, ax0, ax1, opt)
        if p_new is None:
            return [vi]
        dist = nx * (p_new[0] - vi[0]) + ny * (p_new[1] - vi[1])
        norm_len = (nx ** 2 + ny ** 2) ** 0.5
        if norm_len > 0:
            dist /= norm_len
        if dist > tol and edge_len > min_edge:
            if ((abs(p_new[0] - vi[0]) < tol and abs(p_new[1] - vi[1]) < tol) or
                    (abs(p_new[0] - vj[0]) < tol and abs(p_new[1] - vj[1]) < tol)):
                return [vi]
            return _refine(vi, p_new, depth + 1) + _refine(p_new, vj, depth + 1)
        return [vi]

    refined = []
    n = len(unique_pts)
    for i in range(n):
        refined.extend(_refine(unique_pts[i], unique_pts[(i + 1) % n], 0))

    if refined and refined[0] != refined[-1]:
        refined.append(refined[0])
    return refined


def trace_polygon_rate_rate_parallel(lp, reaction_ids: List[str], rxn_index: Dict[str, int],
                                     ax0: Dict[str, float], ax1: Dict[str, float],
                                     n_workers: int = 4, tol: float = 1e-8,
                                     max_depth: int = 50) -> List[Tuple[float, float]]:
    """Same algorithm as trace_polygon_rate_rate(), restructured as
    breadth-first waves: every currently-too-coarse edge is refined
    concurrently each pass. `lp` is the shared, read-only HighsLp from
    build_rate_lp() -- each worker thread lazily builds its own
    HighsRateSolver from it the first time that thread is used, and
    reuses it for the rest of the trace (so warm-starting still applies
    within a thread's own sequence of solves, just not across threads)."""
    import concurrent.futures as cf

    thread_local = th.local()

    def get_solver() -> HighsRateSolver:
        s = getattr(thread_local, "solver", None)
        if s is None:
            s = HighsRateSolver(lp, reaction_ids, rxn_index, [])
            thread_local.solver = s
        return s

    def opt(obj, sense):
        status, _, fluxes = get_solver().optimize(obj, sense)
        return _project(status, fluxes, ax0, ax1)

    with cf.ThreadPoolExecutor(max_workers=n_workers) as ex:
        extremes = list(ex.map(
            lambda args: opt(*args),
            [(ax0, "maximize"), (ax0, "minimize"), (ax1, "maximize"), (ax1, "minimize")]))
        extremes = [p for p in extremes if p is not None]

        if len(extremes) < 2:
            return extremes if extremes else [(0.0, 0.0)]

        unique_pts = _dedupe(extremes, tol)
        if len(unique_pts) == 1:
            return unique_pts

        unique_pts, cx, cy = _order_ccw(unique_pts)
        diameter = max(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
                        for a in unique_pts for b in unique_pts)
        min_edge = 1e-10 * diameter if diameter > 0 else 1e-10
        n = len(unique_pts)

        # state: ordered list of ('vertex', v) [finalized] or
        # ('edge', vi, vj) [still needs refining] -- order here IS the
        # polygon traversal order, preserved across waves.
        state = [("edge", unique_pts[i], unique_pts[(i + 1) % n]) for i in range(n)]

        def refine_once(edge):
            vi, vj = edge
            edge_len = ((vi[0] - vj[0]) ** 2 + (vi[1] - vj[1]) ** 2) ** 0.5
            if edge_len < min_edge:
                return ("done", vi)
            vi_, vj_, nx, ny, p_new = _refine_step(vi, vj, cx, cy, ax0, ax1, opt)
            if p_new is None:
                return ("done", vi)
            dist = nx * (p_new[0] - vi[0]) + ny * (p_new[1] - vi[1])
            norm_len = (nx ** 2 + ny ** 2) ** 0.5
            if norm_len > 0:
                dist /= norm_len
            if dist > tol and edge_len > min_edge:
                if ((abs(p_new[0] - vi[0]) < tol and abs(p_new[1] - vi[1]) < tol) or
                        (abs(p_new[0] - vj[0]) < tol and abs(p_new[1] - vj[1]) < tol)):
                    return ("done", vi)
                return ("split", (vi, p_new), (p_new, vj))
            return ("done", vi)

        depth = 0
        while depth <= max_depth and any(s[0] == "edge" for s in state):
            edge_entries = [s for s in state if s[0] == "edge"]
            outcomes = list(ex.map(lambda s: refine_once((s[1], s[2])), edge_entries))
            new_state = []
            oi = 0
            for s in state:
                if s[0] == "vertex":
                    new_state.append(s)
                else:
                    o = outcomes[oi]
                    oi += 1
                    if o[0] == "done":
                        new_state.append(("vertex", o[1]))
                    else:
                        _, e1, e2 = o
                        new_state.append(("edge", e1[0], e1[1]))
                        new_state.append(("edge", e2[0], e2[1]))
            state = new_state
            depth += 1

    refined = [s[1] for s in state]  # 'vertex' -> v ; leftover 'edge' -> vi (matches max_depth fallback)
    if refined and refined[0] != refined[-1]:
        refined.append(refined[0])
    return refined


def polygon_area(vertices: List[Tuple[float, float]]) -> float:
    """Shoelace formula; used for cross-checking traced polygons against
    a known reference area, independent of exact vertex order/count."""
    pts = vertices[:-1] if len(vertices) > 1 and vertices[0] == vertices[-1] else vertices
    n = len(pts)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


# ---------------------------------------------------------------------------
# 3D, one sliced axis (rate or yield) + two rate axes traced per slice.
# ---------------------------------------------------------------------------

def fix_rate_axis(coeffs: Dict[str, float]):
    """make_fix for trace_3d_slice_polygon when the sliced axis is a plain
    rate: pin `coeffs` itself to `value` (coeffs constant across slices,
    only the RHS varies -- one changeRowBounds call per slice, no
    changeCoeff needed after the first)."""
    return lambda value: (coeffs, value)


def fix_yield_axis(num_coeffs: Dict[str, float], den_coeffs: Dict[str, float]):
    """make_fix for trace_3d_slice_polygon when the sliced axis is a
    yield num/den: pinning yield to `value` is the plain linear equality
    `num - value*den = 0` on the rate variables (see
    lptools._make_fix_constraint's 'yield' branch) -- no Charnes-Cooper
    LFP needed for this, only for finding the yield axis's own min/max
    range elsewhere in plot_flux_space."""
    def make_fix(value):
        merged = dict(num_coeffs)
        for r, c in den_coeffs.items():
            merged[r] = merged.get(r, 0.0) - c * value
        return merged, 0.0
    return make_fix


def trace_3d_slice_polygon(lp, reaction_ids: List[str], rxn_index: Dict[str, int],
                           fix_slot_rows: List[int], make_fix, rate_ax0: Dict[str, float],
                           rate_ax1: Dict[str, float], values: List[float],
                           n_workers: int = 4) -> List[Tuple[float, List[Tuple[float, float]]]]:
    """3D surface for 'one sliced axis + two rate axes': for each target
    value in `values`, pin the sliced axis via `make_fix(value) ->
    (coeffs, rhs)` (see fix_rate_axis / fix_yield_axis) using one
    reserved fix-slot row, then trace the 2D rate-rate polygon on
    (rate_ax0, rate_ax1) within that constrained LP.

    Slices are fully independent, so parallelism happens *across slices*,
    each running a complete sequential trace_polygon_rate_rate() (tens of
    solves) -- deliberately not trace_polygon_rate_rate_parallel() nested
    inside, since refining edges *within* one polygon turned out to be
    too fine-grained a unit of work for a thread pool to pay for itself
    (see the real-model benchmark this was built to follow up on).
    `lp` must have been built with at least one fix slot
    (build_rate_lp(..., num_fix_slots=1) or more).

    Returns [(value, polygon_vertices), ...], one entry per input value,
    in the same order as `values` (ex.map preserves input order).
    """
    import concurrent.futures as cf

    if n_workers <= 1 or len(values) <= 1:
        return trace_3d_slice_polygon_sequential(lp, reaction_ids, rxn_index, fix_slot_rows,
                                                 make_fix, rate_ax0, rate_ax1, values)

    # one solver per worker thread, reused across that thread's slices
    # (so it keeps its warm-started basis between neighbouring slices,
    # like the sequential version) rather than one passModel per slice
    thread_local = th.local()

    def one_slice(value):
        solver = getattr(thread_local, "solver", None)
        if solver is None:
            solver = HighsRateSolver(lp, reaction_ids, rxn_index, fix_slot_rows)
            thread_local.solver = solver
        coeffs, rhs = make_fix(value)
        solver.set_fix_row(0, coeffs, rhs)
        return value, trace_polygon_rate_rate(solver, rate_ax0, rate_ax1)

    with cf.ThreadPoolExecutor(max_workers=min(n_workers, len(values))) as ex:
        return list(ex.map(one_slice, values))


def trace_3d_slice_polygon_sequential(lp, reaction_ids: List[str], rxn_index: Dict[str, int],
                                      fix_slot_rows: List[int], make_fix, rate_ax0: Dict[str, float],
                                      rate_ax1: Dict[str, float],
                                      values: List[float]) -> List[Tuple[float, List[Tuple[float, float]]]]:
    """Same as trace_3d_slice_polygon but single-threaded -- the baseline
    to benchmark the threaded version against, reusing one solver (and
    its warm-started basis) across all slices instead of building a fresh
    one per slice."""
    solver = HighsRateSolver(lp, reaction_ids, rxn_index, fix_slot_rows)
    out = []
    for value in values:
        coeffs, rhs = make_fix(value)
        solver.set_fix_row(0, coeffs, rhs)
        out.append((value, trace_polygon_rate_rate(solver, rate_ax0, rate_ax1)))
    return out


# ---------------------------------------------------------------------------
# 2D adaptive boundary tracing for yield / mixed axes (HiGHS-native port of
# lptools._trace_boundary_adaptive). Unlike the all-rate polygon case, the
# boundary isn't traced as an exact convex hull -- the true feasible region
# in yield coordinates needn't be convex or even polygonal, so this instead
# adaptively bisects the x-axis and asks "what's the max/min y achievable at
# this x", refining wherever linear interpolation between known points
# isn't a good enough approximation yet.
# ---------------------------------------------------------------------------

class RateAxis:
    """A plain-rate axis for use with trace_boundary_adaptive. Reads/pins
    values via `rate_solver` -- pass the *same* HighsRateSolver instance
    (with its fix slot 0 reserved for axis 0) to every axis object used in
    one trace_boundary_adaptive() call, so pinning axis 0 is visible to
    whatever axis 1 optimizes against."""

    def __init__(self, rate_solver: HighsRateSolver, coeffs: Dict[str, float]):
        self.rate_solver = rate_solver
        self.coeffs = coeffs

    def optimize(self, sense: str) -> Optional[float]:
        status, value, _ = self.rate_solver.optimize(self.coeffs, sense)
        return value if status == "optimal" else None

    def apply_fix(self, coeffs: Dict[str, float], rhs: float):
        """Only relevant when this axis is used as axis 1: pins axis 0's
        value on every solver this axis reads from. For a plain rate axis
        that's just the shared rate_solver (the same instance the fix was
        already conceptually "on"); this exists mainly so
        trace_boundary_adaptive can treat RateAxis and YieldAxis
        uniformly rather than special-casing which solver(s) need it."""
        self.rate_solver.set_fix_row(0, coeffs, rhs)

    def clear_fix(self):
        """Reset fix slot 0 to inert on every solver this axis touches.
        trace_boundary_adaptive calls this on axis 1 at the very start of
        every run, so calling it repeatedly on the same (reused) solver
        instances is safe -- without this, a solver reused across
        multiple trace_boundary_adaptive() calls (e.g. benchmarking with
        several repeats, or plot_flux_space reusing solvers across
        several plots) would silently start each later run with
        whatever fix value the *previous* run's deepest refinement probe
        happened to leave behind, constraining x_min/x_max to something
        wrong from the very first step."""
        self.rate_solver.clear_fix_row(0)

    def make_fix(self):
        return fix_rate_axis(self.coeffs)


class YieldAxis:
    """A yield (Charnes-Cooper) axis for use with trace_boundary_adaptive.
    `rate_solver` (shared with the rest of the trace, same instance as any
    RateAxis's) is used only to check which denominator sign(s) are
    achievable *under whatever fix is currently active on it* -- that
    check has to be redone at every x, since pinning axis 0 can change
    which signs are reachable, unlike the 3D-slicing case where the
    sliced axis was always plain-rate and this never came up.
    `yield_solver` carries this axis's own Charnes-Cooper structure (built
    with *this* axis's denominator) and must not be shared with a
    different YieldAxis that has a different denominator."""

    def __init__(self, rate_solver: HighsRateSolver, yield_solver, num: Dict[str, float],
                den: Dict[str, float], den_tol: float = 1e-9, yield_lp_bundle=None,
                rate_lp_bundle=None):
        self.rate_solver = rate_solver
        self.yield_solver = yield_solver
        self.num = num
        self.den = den
        self.den_tol = den_tol
        # Diagnostic-only knobs, both None by default (normal behavior:
        # reuse self.yield_solver / self.rate_solver throughout, warm
        # start included). Set either to test whether reusing that
        # particular solver across the many sequential calls one boundary
        # trace makes is where a correctness issue is coming from, as
        # opposed to the achievable-sign logic or the LP construction
        # itself (which a single freshly-built, lightly-used solver --
        # e.g. --boundary-probe-x's -- can't reveal a staleness problem
        # in, since it only ever sees a handful of calls).
        #
        # yield_lp_bundle: optimize() rebuilds a fresh HighsYieldSolver
        # from (lp, reaction_ids, rxn_index, den_row, t_col,
        # fix_slot_rows) on every call instead of reusing self.yield_solver.
        #
        # rate_lp_bundle: _achievable_signs() rebuilds a fresh
        # HighsRateSolver from (lp, reaction_ids, rxn_index,
        # fix_slot_rows) on every call instead of reusing self.rate_solver
        # for the denominator-sign check specifically. This is the one
        # that --boundary-cold did NOT test: that diagnostic only
        # cold-rebuilt the yield solver, leaving the rate solver used for
        # the sign check as the same long-lived, many-times-reused
        # instance in both its "warm" and "cold" runs.
        self.yield_lp_bundle = yield_lp_bundle
        self.rate_lp_bundle = rate_lp_bundle
        self._pending_fix = None

    def _achievable_signs(self) -> List[float]:
        rate_solver = self.rate_solver
        if self.rate_lp_bundle is not None:
            lp, reaction_ids, rxn_index, fix_slot_rows = self.rate_lp_bundle
            rate_solver = HighsRateSolver(lp, reaction_ids, rxn_index, fix_slot_rows)
            if self._pending_fix is not None:
                coeffs, rhs = self._pending_fix
                rate_solver.set_fix_row(0, coeffs, rhs)
        status_min, min_den, _ = rate_solver.optimize(self.den, "minimize")
        status_max, max_den, _ = rate_solver.optimize(self.den, "maximize")
        signs = []
        if status_min == "unbounded" or (status_min == "optimal" and min_den < -self.den_tol):
            signs.append(-1.0)
        if status_max == "unbounded" or (status_max == "optimal" and max_den > self.den_tol):
            signs.append(1.0)
        return signs

    def optimize(self, sense: str) -> Optional[float]:
        signs = self._achievable_signs()
        if not signs:
            return None
        yield_solver = self.yield_solver
        if self.yield_lp_bundle is not None:
            lp, reaction_ids, rxn_index, den_row, t_col, fix_slot_rows = self.yield_lp_bundle
            yield_solver = HighsYieldSolver(lp, reaction_ids, rxn_index, den_row, t_col, fix_slot_rows)
            if self._pending_fix is not None:
                coeffs, rhs = self._pending_fix
                yield_solver.set_fix_row(0, coeffs, rhs)
        best = None
        for sign in signs:
            status, value, fluxes, scalable = yield_solver.optimize(self.num, sense, sign)
            if status == "optimal" and (
                    best is None or
                    (sense == "maximize" and value > best) or
                    (sense == "minimize" and value < best)):
                best = value
        return best

    def apply_fix(self, coeffs: Dict[str, float], rhs: float):
        """Only relevant when this axis is used as axis 1: pins axis 0's
        value on *every* solver this axis reads from -- both the shared
        rate_solver (used for the achievable-denominator-sign check) and
        this axis's own yield_solver (used for the actual optimization).
        Missing the second one would silently optimize over the whole
        feasible region instead of the x-pinned slice of it while the
        sign-check still (correctly) saw the pin -- exactly the kind of
        two-solvers-drifting-out-of-sync bug this method exists to rule
        out by construction."""
        self._pending_fix = (coeffs, rhs)  # used by _achievable_signs() when rate_lp_bundle is set
        if self.rate_lp_bundle is None:
            self.rate_solver.set_fix_row(0, coeffs, rhs)
        if self.yield_lp_bundle is None:
            self.yield_solver.set_fix_row(0, coeffs, rhs)

    def clear_fix(self):
        """See RateAxis.clear_fix -- same reasoning, both solvers this
        axis can touch (only relevant for the non-bundle/reused-solver
        case; a bundle rebuilds fresh and inert every call already)."""
        self._pending_fix = None
        if self.rate_lp_bundle is None:
            self.rate_solver.clear_fix_row(0)
        if self.yield_lp_bundle is None:
            self.yield_solver.clear_fix_row(0)

    def make_fix(self):
        return fix_yield_axis(self.num, self.den)


def trace_boundary_adaptive(rate_solver: HighsRateSolver, ax0, ax1, max_depth: int = 15,
                            tol: float = 1e-8, debug: Optional[dict] = None):
    """HiGHS-native port of lptools._trace_boundary_adaptive: adaptively
    traces the upper and lower boundary of {(x, y) : x = ax0's value, y =
    ax1's value} by bisecting the x-axis wherever linear interpolation
    between known points isn't accurate enough yet. Unlike
    trace_polygon_rate_rate, this is an *approximation* (matching
    plot_flux_space's own "approximate" labelling for any plot involving
    a yield axis) -- it's not guaranteed to find every extreme point of a
    non-convex or non-polygonal feasible region, only to refine until
    linear interpolation between what it has found is within tolerance.

    `ax0`, `ax1`: RateAxis or YieldAxis instances (ax0 provides
    make_fix(), ax1 provides optimize()). `rate_solver` must be the same
    instance every axis object was built against, with fix slot 0
    reserved for pinning axis 0.

    `debug`, if given an empty dict, is filled in with diagnostics
    (corner values, abs_tol used, and how many fix_and_opt calls came
    back None on each boundary) -- pass one when a returned boundary
    looks suspiciously sparse, since a small vertex count is consistent
    with either genuine convergence *or* every refinement probe silently
    failing (returning None, silently treated the same as "this edge is
    already fine"), and those look identical from the return value alone.

    Returns (upper_boundary, lower_boundary), each a list of (x, y)
    tuples ordered by x.
    """

    # Defensive check: both axis objects are documented to share
    # `rate_solver`, but nothing in RateAxis/YieldAxis's own construction
    # enforces that -- a caller could accidentally build ax0 or ax1
    # against a *different* solver instance, which would silently pin
    # axis 0 on one solver while reading it back from another. Fail loudly
    # here instead of producing a quietly-wrong boundary.
    for name, ax in (("ax0", ax0), ("ax1", ax1)):
        if getattr(ax, "rate_solver", None) is not rate_solver:
            raise ValueError(
                f"{name}.rate_solver is not the same instance as the `rate_solver` argument -- "
                f"every axis object passed to trace_boundary_adaptive must share it.")

    ax1.clear_fix()  # start from known-inert state -- see RateAxis/YieldAxis.clear_fix's
                     # docstring for why this matters when a solver is reused across calls

    none_counts = {"upper": 0, "lower": 0}

    def fix_and_opt(x_val, sense, which=None):
        coeffs, rhs = ax0.make_fix()(x_val)
        ax1.apply_fix(coeffs, rhs)
        value = ax1.optimize(sense)
        if value is None and which is not None:
            none_counts[which] += 1
        return value

    x_min = ax0.optimize("minimize")
    x_max = ax0.optimize("maximize")
    if x_min is None or x_max is None:
        if debug is not None:
            debug["error"] = "ax0.optimize() returned None for x_min or x_max"
        return [], []

    y_min_at_xmin = fix_and_opt(x_min, "minimize", "lower")
    y_max_at_xmin = fix_and_opt(x_min, "maximize", "upper")
    y_min_at_xmax = fix_and_opt(x_max, "minimize", "lower")
    y_max_at_xmax = fix_and_opt(x_max, "maximize", "upper")

    upper = [(x, y) for x, y in [(x_min, y_max_at_xmin), (x_max, y_max_at_xmax)] if y is not None]
    lower = [(x, y) for x, y in [(x_min, y_min_at_xmin), (x_max, y_min_at_xmax)] if y is not None]

    if debug is not None:
        debug["x_min"], debug["x_max"] = x_min, x_max
        debug["corners"] = {
            "y_min_at_xmin": y_min_at_xmin, "y_max_at_xmin": y_max_at_xmin,
            "y_min_at_xmax": y_min_at_xmax, "y_max_at_xmax": y_max_at_xmax,
        }

    if not upper and not lower:
        return [], []

    all_y = [y for _, y in upper + lower]
    y_range = max(all_y) - min(all_y) if all_y else 0.0
    abs_tol = max(1e-6, 1e-3 * abs(y_range))
    if debug is not None:
        debug["y_range"] = y_range
        debug["abs_tol"] = abs_tol

    if debug is not None:
        debug["probes_upper"] = []
        debug["probes_lower"] = []

    def refine(boundary, sense, depth, which):
        if depth > max_depth or len(boundary) < 2:
            return boundary
        new_boundary = [boundary[0]]
        changed = False
        for i in range(len(boundary) - 1):
            x_left, y_left = boundary[i]
            x_right, y_right = boundary[i + 1]
            if abs(x_right - x_left) < tol:
                new_boundary.append(boundary[i + 1])
                continue
            x_mid = (x_left + x_right) / 2
            y_actual = fix_and_opt(x_mid, sense, which)
            y_interp = (y_left + y_right) / 2
            if debug is not None:
                debug[f"probes_{which}"].append({
                    "depth": depth, "x_mid": x_mid, "y_actual": y_actual, "y_interp": y_interp,
                    "deviation": None if y_actual is None else abs(y_actual - y_interp),
                    "split": False if y_actual is None else abs(y_actual - y_interp) > abs_tol,
                })
            if y_actual is None:
                new_boundary.append(boundary[i + 1])
                continue
            if abs(y_actual - y_interp) > abs_tol:
                new_boundary.append((x_mid, y_actual))
                changed = True
            new_boundary.append(boundary[i + 1])
        if changed:
            return refine(new_boundary, sense, depth + 1, which)
        return new_boundary

    upper = refine(upper, "maximize", 0, "upper")
    lower = refine(lower, "minimize", 0, "lower")
    if debug is not None:
        debug["none_count_upper"] = none_counts["upper"]
        debug["none_count_lower"] = none_counts["lower"]
    return upper, lower


# ---------------------------------------------------------------------------
# 3D, all-rate polytope via face-normal refinement (HiGHS-native port of
# lptools._trace_polytope_3d_rate / _hull_face_polygons). Exact, like
# trace_polygon_rate_rate -- not an approximation, unlike anything
# involving a yield axis.
# ---------------------------------------------------------------------------

def _ceil_dec(v: float, n: int) -> float:
    """Round v UP to n decimals. Matches lptools.py's own ceil_dec: a
    consistent rounding *direction* (not round-to-nearest) makes two LP
    solutions that are really the same vertex, but differ by tiny
    floating-point noise in either direction, much more likely to land on
    the exact same rounded value and get deduplicated correctly."""
    return math.ceil(v * (10 ** n)) / (10 ** n)


def _project3(fluxes: Dict[str, float], coeffs3) -> Tuple[float, float, float]:
    return tuple(
        _ceil_dec(sum(c * fluxes.get(r, 0.0) for r, c in coeffs.items()), 9)
        for coeffs in coeffs3
    )


def _is_dup3(pt, pts, tol: float) -> bool:
    return any(all(abs(pt[k] - q[k]) < tol for k in range(3)) for q in pts)


def hull_face_polygons(hull):
    """HiGHS-independent port of lptools._hull_face_polygons: merges
    coplanar ConvexHull simplices into polygon faces (vertex-index lists,
    ordered counterclockwise viewed from outside), so a 3D plot can be
    rendered without visible seams along the interior of each flat face.
    """
    from collections import defaultdict

    face_groups = defaultdict(set)
    for i, eq in enumerate(hull.equations):
        key = tuple(round(v, 5) for v in eq)
        for vi in hull.simplices[i]:
            face_groups[key].add(vi)

    faces = []
    for eq_key, vertex_indices in face_groups.items():
        verts = list(vertex_indices)
        if len(verts) < 3:
            continue
        normal = numpy.array(eq_key[:3])
        pts = hull.points[verts]
        centroid = pts.mean(axis=0)
        ref = numpy.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else numpy.array([0.0, 1.0, 0.0])
        u = ref - normal * normal.dot(ref)
        u = u / (u.dot(u) ** 0.5)
        v = numpy.array([
            normal[1] * u[2] - normal[2] * u[1],
            normal[2] * u[0] - normal[0] * u[2],
            normal[0] * u[1] - normal[1] * u[0],
        ])
        angles = [math.atan2((pt - centroid).dot(v), (pt - centroid).dot(u)) for pt in pts]
        order = sorted(range(len(verts)), key=lambda i: angles[i])
        faces.append([verts[i] for i in order])
    return faces


def trace_polytope_3d_rate(solver: HighsRateSolver, ax0: Dict[str, float], ax1: Dict[str, float],
                           ax2: Dict[str, float], tol: float = 1e-8, max_iters: int = 20):
    """Sequential, direct port of lptools._trace_polytope_3d_rate: exact
    3D convex polytope for three rate axes. Finds 6 initial extremes
    (min/max of each axis), builds a convex hull, then repeatedly
    optimizes along each current face's outward normal and adds any
    genuinely new vertex found, until a pass adds nothing.

    Returns (vertices, triangles, face_polygons):
      vertices: list of (x, y, z) tuples
      triangles: hull.simplices as a list of 3-tuples of vertex indices
      face_polygons: merged coplanar faces (see hull_face_polygons), or
        None if fewer than 4 vertices were found (degenerate)
    """
    import scipy.spatial as sp_spatial

    coeffs3 = (ax0, ax1, ax2)

    def opt_point(obj, sense="maximize"):
        status, _, fluxes = solver.optimize(obj, sense)
        return None if status != "optimal" else _project3(fluxes, coeffs3)

    vertices = []
    for coeffs in coeffs3:
        for sense in ("maximize", "minimize"):
            pt = opt_point(coeffs, sense)
            if pt is not None and not _is_dup3(pt, vertices, tol):
                vertices.append(pt)

    if len(vertices) < 4:
        return vertices, [], None

    for _ in range(max_iters):
        try:
            hull = sp_spatial.ConvexHull(numpy.array(vertices))
        except sp_spatial.QhullError:
            break
        new_found = False
        for eq in hull.equations:
            normal = eq[:3]
            obj: Dict[str, float] = {}
            for k in range(3):
                for r, c in coeffs3[k].items():
                    obj[r] = obj.get(r, 0.0) + normal[k] * c
            pt = opt_point(obj, "maximize")
            if pt is not None and not _is_dup3(pt, vertices, tol):
                vertices.append(pt)
                new_found = True
        if not new_found:
            break

    try:
        hull = sp_spatial.ConvexHull(numpy.array(vertices))
        triang = hull.simplices.tolist()
        face_polys = hull_face_polygons(hull)
    except sp_spatial.QhullError:
        triang, face_polys = [], None
    return vertices, triang, face_polys


def trace_polytope_3d_rate_parallel(lp, reaction_ids: List[str], rxn_index: Dict[str, int],
                                    ax0: Dict[str, float], ax1: Dict[str, float],
                                    ax2: Dict[str, float], n_workers: int = 4,
                                    tol: float = 1e-8, max_iters: int = 20):
    """Same as trace_polytope_3d_rate, but each refinement pass solves
    every current hull face concurrently via a thread pool (each worker
    thread lazily builds and reuses its own HighsRateSolver from the
    shared, read-only `lp`). This is the right granularity for threading
    here: a hull's face count grows with vertex count and each face is a
    full LP solve, the same reasoning that made 3D slicing pay off where
    refining edges *within* one 2D polygon didn't (too few, too cheap
    tasks per wave to amortize thread-pool overhead against)."""
    import concurrent.futures as cf

    coeffs3 = (ax0, ax1, ax2)
    thread_local = th.local()

    def get_solver() -> HighsRateSolver:
        s = getattr(thread_local, "solver", None)
        if s is None:
            s = HighsRateSolver(lp, reaction_ids, rxn_index, [])
            thread_local.solver = s
        return s

    def opt_point(obj, sense="maximize"):
        status, _, fluxes = get_solver().optimize(obj, sense)
        return None if status != "optimal" else _project3(fluxes, coeffs3)

    with cf.ThreadPoolExecutor(max_workers=n_workers) as ex:
        extreme_args = [(coeffs, sense) for coeffs in coeffs3 for sense in ("maximize", "minimize")]
        vertices = []
        for pt in ex.map(lambda a: opt_point(*a), extreme_args):
            if pt is not None and not _is_dup3(pt, vertices, tol):
                vertices.append(pt)

        if len(vertices) < 4:
            return vertices, [], None

        import scipy.spatial as sp_spatial
        for _ in range(max_iters):
            try:
                hull = sp_spatial.ConvexHull(numpy.array(vertices))
            except sp_spatial.QhullError:
                break
            objs = []
            for eq in hull.equations:
                normal = eq[:3]
                obj: Dict[str, float] = {}
                for k in range(3):
                    for r, c in coeffs3[k].items():
                        obj[r] = obj.get(r, 0.0) + normal[k] * c
                objs.append(obj)
            new_found = False
            for pt in ex.map(lambda o: opt_point(o, "maximize"), objs):
                if pt is not None and not _is_dup3(pt, vertices, tol):
                    vertices.append(pt)
                    new_found = True
            if not new_found:
                break

        try:
            hull = sp_spatial.ConvexHull(numpy.array(vertices))
            triang = hull.simplices.tolist()
            face_polys = hull_face_polygons(hull)
        except sp_spatial.QhullError:
            triang, face_polys = [], None
    return vertices, triang, face_polys


# ---------------------------------------------------------------------------
# 3D, 2+ yield axes: grid-scanning fallback (HiGHS-native port of
# plot_flux_space's least-precise, least-used 3D case -- used only when
# neither the exact all-rate polytope tracer nor the 1-yield slicing
# tracer applies). Approximate, like everything else touching a yield
# axis, and coarser than either of those: this is plot_flux_space's own
# fallback of last resort, not something to reach for by choice.
# ---------------------------------------------------------------------------

class GridAxis:
    """Generalizes RateAxis/YieldAxis for trace_grid_3d, which (unlike
    trace_boundary_adaptive's 2-axis pattern) needs up to TWO
    simultaneous fixes active at once: axis 0's value AND axis 1's value,
    both pinned when reading axis 2. RateAxis/YieldAxis hardcode fix slot
    0; this takes an explicit slot number on every fix operation instead,
    so the same axis object can have two independent pins applied (one
    per slot) without them overwriting each other.

    For a rate axis: pass ax_type='rate', coeffs=<the axis's own
    coefficients>. For a yield axis: ax_type='yield', coeffs=<numerator>,
    den=<denominator>, yield_solver=<its own HighsYieldSolver, built with
    enough fix slots for however this axis will be used>."""

    def __init__(self, ax_type: str, rate_solver: HighsRateSolver, coeffs: Dict[str, float],
                den: Optional[Dict[str, float]] = None, yield_solver=None, den_tol: float = 1e-9):
        self.ax_type = ax_type
        self.rate_solver = rate_solver
        self.coeffs = coeffs
        self.den = den
        self.yield_solver = yield_solver
        self.den_tol = den_tol

    def make_fix(self):
        if self.ax_type == "rate":
            return fix_rate_axis(self.coeffs)
        return fix_yield_axis(self.coeffs, self.den)

    def apply_fix(self, slot: int, coeffs: Dict[str, float], rhs: float):
        # Applying to a slot that doesn't exist must stay LOUD: silently
        # skipping it would mean this axis quietly optimizes without one
        # of the pins it was supposed to have -- a wrong answer that
        # looks like a right one.
        if self.ax_type == "yield" and slot >= len(self.yield_solver.fix_slot_rows):
            raise ValueError(
                f"GridAxis (yield) was built with only {len(self.yield_solver.fix_slot_rows)} "
                f"fix slot(s) on its yield solver but apply_fix(slot={slot}) was requested -- "
                f"build it with num_fix_slots >= {slot + 1}.")
        self.rate_solver.set_fix_row(slot, coeffs, rhs)
        if self.ax_type == "yield":
            self.yield_solver.set_fix_row(slot, coeffs, rhs)

    def clear_fix(self, slot: int):
        """Unlike apply_fix, tolerant of a slot this axis's yield solver
        doesn't have: nothing could ever have been pinned there, so
        "clearing" it is trivially already true (ax1 in trace_grid_3d
        legitimately has only slot 0 on its yield solver, but shares
        the rate solver -- which does have slot 1 -- with ax2)."""
        self.rate_solver.clear_fix_row(slot)
        if self.ax_type == "yield" and slot < len(self.yield_solver.fix_slot_rows):
            self.yield_solver.clear_fix_row(slot)

    def optimize(self, sense: str) -> Optional[float]:
        if self.ax_type == "rate":
            status, value, _ = self.rate_solver.optimize(self.coeffs, sense)
            return value if status == "optimal" else None
        status_min, min_den, _ = self.rate_solver.optimize(self.den, "minimize")
        status_max, max_den, _ = self.rate_solver.optimize(self.den, "maximize")
        signs = []
        if status_min == "unbounded" or (status_min == "optimal" and min_den < -self.den_tol):
            signs.append(-1.0)
        if status_max == "unbounded" or (status_max == "optimal" and max_den > self.den_tol):
            signs.append(1.0)
        if not signs:
            return None
        best = None
        for sign in signs:
            status, value, fluxes, scalable = self.yield_solver.optimize(self.coeffs, sense, sign)
            if status == "optimal" and (
                    best is None or
                    (sense == "maximize" and value > best) or
                    (sense == "minimize" and value < best)):
                best = value
        return best


def _triangulate_strips(strip_a: List[int], strip_b: List[int], datapoints: List[List[float]],
                        triang: List[List[int]], flip_winding: bool = False):
    """Verbatim port of lptools._triangulate_strips -- pure geometry/
    indexing, no solver dependency at all. Connects two ordered index
    strips (a "top" contour and a "bottom" contour, say) into a triangle
    strip by always advancing whichever side has the shorter diagonal."""
    if len(strip_a) < 1 or len(strip_b) < 1:
        return
    i, j = 0, 0
    while i < len(strip_a) - 1 or j < len(strip_b) - 1:
        if i >= len(strip_a) - 1:
            tri = [strip_a[i], strip_b[j], strip_b[j + 1]]
            j += 1
        elif j >= len(strip_b) - 1:
            tri = [strip_a[i], strip_b[j], strip_a[i + 1]]
            i += 1
        else:
            pa_next, pb_next = datapoints[strip_a[i + 1]], datapoints[strip_b[j + 1]]
            pa_curr, pb_curr = datapoints[strip_a[i]], datapoints[strip_b[j]]
            d1 = sum((pa_next[k] - pb_curr[k]) ** 2 for k in range(len(pa_next)))
            d2 = sum((pa_curr[k] - pb_next[k]) ** 2 for k in range(len(pa_curr)))
            if d1 < d2:
                tri = [strip_a[i], strip_b[j], strip_a[i + 1]]
                i += 1
            else:
                tri = [strip_a[i], strip_b[j], strip_b[j + 1]]
                j += 1
        if flip_winding:
            tri = [tri[0], tri[2], tri[1]]
        triang.append(tri)


def _grid_x_slice(ax0: GridAxis, ax1: GridAxis, ax2: GridAxis, x_val: float,
                  points: int, y_range_global: float):
    """One x-slice of trace_grid_3d: pin ax0 = x_val, find ax1's range,
    sample it, and read ax2's min/max at each sample. Self-contained
    with respect to fix state (clears slot 1, overwrites slot 0), so
    slices can run in any order or on different axis/solver sets.
    Returns (x_val, upper_slice, lower_slice) or None if infeasible."""
    # Slot 1 may still be pinned to the previous slice's last y_val
    # (ax2.apply_fix(1, ...) below); when ax1 and ax2 share a rate
    # solver, ax1's range-finding reads that slot, so clear it first.
    ax1.clear_fix(1)
    ax2.clear_fix(1)

    coeffs0, rhs0 = ax0.make_fix()(x_val)
    ax1.apply_fix(0, coeffs0, rhs0)
    ax2.apply_fix(0, coeffs0, rhs0)

    y_lo = ax1.optimize("minimize")
    y_hi = ax1.optimize("maximize")
    if y_lo is None or y_hi is None:
        return None

    if abs(y_hi - y_lo) < 1e-10:
        y_space = [y_lo]
    else:
        n_pts = max(3, int(points * abs(y_hi - y_lo) / y_range_global))
        n_pts = min(n_pts, points)
        y_space = [y_lo + (y_hi - y_lo) * i / (n_pts - 1) for i in range(n_pts)] if n_pts > 1 else [y_lo]

    upper_slice, lower_slice = [], []
    for y_val in y_space:
        coeffs1, rhs1 = ax1.make_fix()(y_val)
        ax2.apply_fix(1, coeffs1, rhs1)
        z_lo = ax2.optimize("minimize")
        z_hi = ax2.optimize("maximize")
        if z_lo is not None and z_hi is not None:
            upper_slice.append((y_val, z_hi))
            lower_slice.append((y_val, z_lo))
    return (x_val, upper_slice, lower_slice) if upper_slice else None


def trace_grid_3d(ax0: GridAxis, ax1: GridAxis, ax2: GridAxis,
                  x_limits: Tuple[float, float], y_range_global: float,
                  points: int = 25, n_workers: int = 1, make_axes=None):
    """HiGHS-native port of plot_flux_space's 3D 2+-yield grid-scanning
    fallback: scans a grid of ax0 values, finds ax1's achievable range at
    each, samples a grid of ax1 values there, and for each (ax0, ax1)
    pair finds ax2's achievable range -- building top and bottom
    surfaces stitched into a triangle mesh via _triangulate_strips.

    ax1 must accept a fix on slot 0 (for pinning ax0). ax2 must accept
    fixes on slots 0 AND 1 simultaneously (ax0 and ax1 both pinned when
    reading ax2's range) -- so if ax1 and/or ax2 are yield-typed, their
    own HighsYieldSolvers must have been built with num_fix_slots=2 (or
    more), not the single slot trace_boundary_adaptive needs.

    x_limits: ax0's own unconstrained (min, max) range to scan over.
    y_range_global: ax1's own unconstrained value range (max - min),
    used only to scale how many y-points to sample per x-slice (a wide
    x-slice's y-range gets proportionally more points, capped at
    `points`) -- pass max(1e-10, abs(ax1_max - ax1_min)) to avoid a
    division by zero if ax1 happens to be degenerate.

    Threading: x-slices are independent (see _grid_x_slice), so with
    n_workers > 1 and a `make_axes() -> (ax0, ax1, ax2)` factory they
    are scanned concurrently, each worker thread calling make_axes()
    once for its own private solvers (never shared across threads).
    Without make_axes, or with n_workers <= 1, the passed axes are used
    sequentially. Results are returned in x order either way.

    Returns (datapoints, triang) -- datapoints as [x, y, z] lists.
    """
    x_lo, x_hi = x_limits
    x_space = [x_lo] if points <= 1 else [x_lo + (x_hi - x_lo) * i / (points - 1) for i in range(points)]

    # Start from a known-inert state on both slots, for every solver
    # either axis reads from. Strictly redundant with the per-slice reset
    # below (slot 1 is cleared at the top of every iteration and slot 0 is
    # overwritten immediately), so this doesn't change behavior -- it just
    # makes the "starts clean" precondition explicit rather than dependent
    # on the loop body's ordering, matching trace_boundary_adaptive.
    def reset(a1, a2):
        # known-inert fix state on both slots for every solver involved
        for slot in (0, 1):
            a1.clear_fix(slot)
            a2.clear_fix(slot)

    if n_workers > 1 and make_axes is not None and len(x_space) > 1:
        import concurrent.futures as cf
        thread_local = th.local()

        def scan(x_val):
            axs = getattr(thread_local, "axes", None)
            if axs is None:
                axs = make_axes()
                reset(axs[1], axs[2])
                thread_local.axes = axs
            return _grid_x_slice(axs[0], axs[1], axs[2], x_val, points, y_range_global)

        with cf.ThreadPoolExecutor(max_workers=min(n_workers, len(x_space))) as ex:
            results = list(ex.map(scan, x_space))
    else:
        reset(ax1, ax2)
        results = [_grid_x_slice(ax0, ax1, ax2, x_val, points, y_range_global) for x_val in x_space]
    slices = [r for r in results if r is not None]

    if not slices:
        return [], []

    datapoints: List[List[float]] = []
    datapoints_top: List[List[int]] = []
    datapoints_bottom: List[List[int]] = []
    for x_val, upper_slice, lower_slice in slices:
        top_ids, bot_ids = [], []
        for (y_val, z_hi), (_, z_lo) in zip(upper_slice, lower_slice):
            top_ids.append(len(datapoints))
            datapoints.append([x_val, y_val, z_hi])
            bot_ids.append(len(datapoints))
            datapoints.append([x_val, y_val, z_lo])
        datapoints_top.append(top_ids)
        datapoints_bottom.append(bot_ids)

    triang: List[List[int]] = []
    for s in range(len(slices) - 1):
        _triangulate_strips(datapoints_top[s], datapoints_top[s + 1], datapoints, triang)
        _triangulate_strips(datapoints_bottom[s], datapoints_bottom[s + 1], datapoints, triang, flip_winding=True)
    front_top = [t[0] for t in datapoints_top]
    front_bot = [b[0] for b in datapoints_bottom]
    _triangulate_strips(front_top, front_bot, datapoints, triang, flip_winding=True)
    back_top = [t[-1] for t in datapoints_top]
    back_bot = [b[-1] for b in datapoints_bottom]
    _triangulate_strips(back_top, back_bot, datapoints, triang)
    _triangulate_strips(datapoints_top[0], datapoints_bottom[0], datapoints, triang)
    _triangulate_strips(datapoints_top[-1], datapoints_bottom[-1], datapoints, triang, flip_winding=True)

    return datapoints, triang
