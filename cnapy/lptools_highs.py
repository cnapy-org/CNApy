"""lptools_highs.py (prototype)

HiGHS-native port of lptools.plot_flux_space, dispatching to the
already-validated tracers in plot_trace_highs.py instead of
straindesign's fba()/yopt(). straindesign is kept ONLY for parsing text
axis/constraint expressions (parse_linexpr, parse_constraints,
linexprdict2str) and for the cmp_model/cmp_map compression-ID remapping
(straindesign.networktools) -- neither of those does any LP solving, so
neither is in tension with the point of this rewrite.

Split into two layers, same reasoning as everywhere else in this effort:

  - plot_flux_space_data_highs(): computes everything BUT the actual
    matplotlib rendering -- axis names/types/limits, degeneracy
    classification, and (datapoints, triang, face_polys/slice_outlines).
    Pure data, fully unit-testable without matplotlib or a display.

  - plot_flux_space_highs(): thin wrapper that calls the above and then
    renders it with the *same* matplotlib code plot_flux_space already
    uses (copied essentially unmodified) -- low risk precisely because
    it isn't new logic, just new data feeding proven rendering code.

Covered: 2D point/line/full and 3D point/line/plane/full (0 yield axes:
exact polytope; 1 yield axis: per-slice polygons; 2 or 3 yield axes: the
grid-scanning fallback, ported as trace_grid_3d -- approximate and the
slowest path, exactly as in plot_flux_space itself, and, like the 1-yield
slicing case, a natural target for slice-level threading that isn't done
here).

Everything below the "pure data" line has NOT been run against a real
cobra model or real highspy -- see the module docstring notes at each
untested seam.
"""

import math
import os
from typing import Dict, List, Optional, Tuple

from cnapy.highs_lp_cache import build_rate_lp, build_yopt_lp, HighsRateSolver, HighsYieldSolver
from cnapy.plot_trace_highs import (
    RateAxis, YieldAxis, fix_rate_axis, fix_yield_axis,
    trace_polygon_rate_rate, trace_polygon_rate_rate_parallel,
    trace_boundary_adaptive,
    trace_polytope_3d_rate, trace_polytope_3d_rate_parallel,
    trace_3d_slice_polygon, trace_3d_slice_polygon_sequential,
    GridAxis, trace_grid_3d,
    polygon_area,
)

# Re-used verbatim from lptools.py: pure math, no solver dependency at
# all, so reusing them is not in tension with dropping straindesign for
# solving. Imported lazily inside functions below to avoid a hard
# top-level dependency on lptools.py for anyone unit-testing this module
# in isolation (as the tests in this prototype do).


def _den_key(den: Dict[str, float]) -> Tuple[Tuple[str, float], ...]:
    """Canonical, hashable key for a denominator dict, so two axes that
    happen to share the same denominator (common -- e.g. several
    products' yields relative to the same substrate) share one
    HighsYieldSolver/HighsLp instead of building a redundant duplicate."""
    return tuple(sorted(den.items()))


class _SolverBundle:
    """Everything needed to compute limits/traces for one call's worth of
    axes: one shared rate solver (fix slot 0 reserved for pinning "axis
    0" in whichever 2-axis sub-trace is currently running) plus one
    HighsYieldSolver per distinct denominator among the axes that are
    yield-typed."""

    def __init__(self, model, reaction_ids, base_constraints, num_fix_slots: int = 1):
        rate_lp, rxn_ids, rxn_index, fix_rows = build_rate_lp(
            model, constraints=base_constraints, num_fix_slots=num_fix_slots)
        self.rate_lp = rate_lp
        self.reaction_ids = rxn_ids
        self.rxn_index = rxn_index
        self.rate_fix_rows = fix_rows
        self.rate_solver = HighsRateSolver(rate_lp, rxn_ids, rxn_index, fix_rows)
        self._yield_lps: Dict[Tuple, Tuple] = {}   # den_key -> (lp, den_row, t_col, fix_rows)
        self._yield_solvers: Dict[Tuple, HighsYieldSolver] = {}
        self._model = model
        self._base_constraints = base_constraints
        self._num_fix_slots = num_fix_slots

    def yield_solver_for(self, den: Dict[str, float]) -> HighsYieldSolver:
        key = _den_key(den)
        solver = self._yield_solvers.get(key)
        if solver is None:
            lp, rxn_ids, rxn_index, den_row, t_col, fix_rows = build_yopt_lp(
                self._model, den, constraints=self._base_constraints,
                num_fix_slots=self._num_fix_slots)
            solver = HighsYieldSolver(lp, rxn_ids, rxn_index, den_row, t_col, fix_rows)
            self._yield_lps[key] = (lp, den_row, t_col, fix_rows)
            self._yield_solvers[key] = solver
        return solver

    def clone(self) -> "_SolverBundle":
        """A bundle with its own fresh solvers (for another thread) that
        shares this one's already-built, read-only HighsLp objects --
        one passModel per solver, no re-reading of the cobra model. Yield
        LPs not built yet on this bundle are built lazily by the clone,
        so call yield_solver_for() here first for every denominator the
        workers will need."""
        c = object.__new__(_SolverBundle)
        c.rate_lp, c.reaction_ids, c.rxn_index = self.rate_lp, self.reaction_ids, self.rxn_index
        c.rate_fix_rows = self.rate_fix_rows
        c.rate_solver = HighsRateSolver(self.rate_lp, self.reaction_ids, self.rxn_index, self.rate_fix_rows)
        c._yield_lps = dict(self._yield_lps)
        c._yield_solvers = {
            key: HighsYieldSolver(lp, self.reaction_ids, self.rxn_index, den_row, t_col, fix_rows)
            for key, (lp, den_row, t_col, fix_rows) in self._yield_lps.items()}
        c._model, c._base_constraints = self._model, self._base_constraints
        c._num_fix_slots = self._num_fix_slots
        return c

    def rate_axis(self, coeffs: Dict[str, float]) -> RateAxis:
        return RateAxis(self.rate_solver, coeffs)

    def yield_axis(self, num: Dict[str, float], den: Dict[str, float]) -> YieldAxis:
        return YieldAxis(self.rate_solver, self.yield_solver_for(den), num, den)


def _axis_limits(bundle: _SolverBundle, ax_type: str, ax) -> Tuple[float, float]:
    """Unconstrained min/max of one axis (rate: ax=[coeffs]; yield:
    ax=[num, den]). Raises on unbounded/infeasible, matching
    plot_flux_space's own behavior for that case."""
    if ax_type == "rate":
        axis = bundle.rate_axis(ax[0])
        v_min = axis.optimize("minimize")
        v_max = axis.optimize("maximize")
    else:
        axis = bundle.yield_axis(ax[0], ax[1])
        v_min = axis.optimize("minimize")
        v_max = axis.optimize("maximize")
    if v_min is None or v_max is None:
        raise Exception(
            "One of the specified axes is unbounded, undefined, or the problem is "
            "infeasible. Plot cannot be generated.")
    return v_min, v_max


def _ceil_dec(v: float, n: int) -> float:
    return math.ceil(v * (10 ** n)) / (10 ** n)


def _floor_dec(v: float, n: int) -> float:
    return math.floor(v * (10 ** n)) / (10 ** n)


def _detect_degeneracy(val_limits, num_axes):
    """Verbatim port of lptools._detect_degeneracy -- pure math."""
    degenerate = []
    for vmin, vmax in val_limits:
        scale = max(1.0, abs(vmin), abs(vmax))
        degenerate.append(abs(vmax - vmin) < 1e-8 * scale)
    n_degen = sum(degenerate)
    if n_degen == num_axes:
        return "point", degenerate
    elif n_degen == num_axes - 1:
        return "line", degenerate
    elif n_degen == num_axes - 2:
        return "plane", degenerate
    return "full", degenerate


def _available_cpus() -> int:
    try:
        return len(os.sched_getaffinity(0))  # respects taskset/cgroup limits on Linux
    except AttributeError:
        return os.cpu_count() or 1


def auto_n_workers(n_units: int, min_units_per_worker: int, max_workers: Optional[int] = None) -> int:
    """thread count for n_units independent work items: every worker gets at least
    min_units_per_worker items, and there are never more workers than available CPUs
    (or max_workers)"""
    cap = _available_cpus() if max_workers is None else min(max_workers, _available_cpus())
    return max(1, min(cap, n_units // min_units_per_worker))


def plot_flux_space_data_highs(model, axes, **kwargs) -> dict:
    """Computes everything plot_flux_space needs except the matplotlib
    rendering itself. See the module docstring for what's ported and
    what's not (the 3D 2+-yield case).

    kwargs accepted (subset of plot_flux_space's, plotting-only ones
    like plt_backend/show/cmap are collected here and passed through
    untouched for the rendering layer to use):
        constraints, points, n_workers (thread count for the parallel
        tracers of the 3D cases with yield axes; default "auto" chooses it
        from the problem type and the number of slices/grid rows, see
        _fill_3d), show, cmap.

    Returns a dict with everything plot_flux_space_highs needs to
    reproduce the original's exact plotting branches: ax_name, ax_limits,
    val_limits, ax_type, num_axes, degen, degen_axes, datapoints, triang,
    face_polys, slice_outlines, show, cmap.
    """
    from straindesign import parse_linexpr, parse_constraints
    from straindesign.parse_constr import linexprdict2str

    n_workers = kwargs.get("n_workers", "auto")
    reaction_ids = model.reactions.list_attr("id")

    constraints_in = kwargs.get("constraints", "")
    constraints = parse_constraints(constraints_in, reaction_ids) if constraints_in else []

    axes = [list(ax) if not isinstance(ax, str) else [ax] for ax in axes]
    num_axes = len(axes)
    if num_axes not in (2, 3):
        raise Exception(
            "Please define 2 or 3 axes as a list of tuples [ax1, ax2, (optional) ax3] "
            'with ax1 = (den,num). "den" and "num" being linear expressions.')

    points = kwargs.get("points", 40 if num_axes == 2 else 25)

    ax_name = ["" for _ in range(num_axes)]
    ax_type = ["" for _ in range(num_axes)]
    for i, ax in enumerate(axes):
        if len(ax) == 1:
            ax_type[i] = "rate"
            ax[0] = parse_linexpr(ax[0], reaction_ids)[0]
            ax_name[i] = linexprdict2str(ax[0])
        elif len(ax) == 2:
            ax_type[i] = "yield"
            ax[0] = parse_linexpr(ax[0], reaction_ids)[0]
            ax[1] = parse_linexpr(ax[1], reaction_ids)[0]
            ax_name[i] = "(" + linexprdict2str(ax[0]) + ") / (" + linexprdict2str(ax[1]) + ")"
        else:
            raise Exception(f"Axis {i} must be a single expression (rate) or a "
                            f"[numerator, denominator] pair (yield), got {ax!r}")

    # one shared solver bundle for everything that doesn't need the
    # "plane" case's extra fixed-axis constraint
    bundle = _SolverBundle(model, reaction_ids, constraints, num_fix_slots=1)

    val_limits = [(math.nan, math.nan) for _ in range(num_axes)]
    ax_limits = [(math.nan, math.nan) for _ in range(num_axes)]
    for i, ax in enumerate(axes):
        v_min, v_max = _axis_limits(bundle, ax_type[i], ax)
        val_limits[i] = [_ceil_dec(v_min, 8), _floor_dec(v_max, 8)]
        ax_limits[i] = [min(0, val_limits[i][0]), max(0, val_limits[i][1])]
        if ax_limits[i][0] == ax_limits[i][1]:
            pad = max(0.5, abs(ax_limits[i][0]) * 0.1)
            ax_limits[i] = [ax_limits[i][0] - pad, ax_limits[i][1] + pad]

    degen, degen_axes = _detect_degeneracy(val_limits, num_axes)

    result = {
        "ax_name": ax_name, "ax_type": ax_type, "ax_limits": ax_limits,
        "val_limits": val_limits, "num_axes": num_axes, "degen": degen,
        "degen_axes": degen_axes, "show": kwargs.get("show", True),
        "cmap": kwargs.get("cmap", "managua"),
        "datapoints": None, "triang": None, "face_polys": None, "slice_outlines": None,
    }

    if num_axes == 2:
        _fill_2d(result, bundle, axes, ax_type, val_limits, points, n_workers)
    else:
        _fill_3d(result, model, reaction_ids, constraints, bundle, axes, ax_type,
                 val_limits, points, n_workers)

    return result


def _fill_2d(result, bundle, axes, ax_type, val_limits, points, n_workers):
    # NOTE: _detect_degeneracy's 'plane' label (n_degen == num_axes - 2)
    # is only meaningful for num_axes == 3. For num_axes == 2 it
    # triggers on n_degen == 0 -- i.e. a perfectly ordinary, fully
    # non-degenerate 2D case gets labelled 'plane' here, not 'full'.
    # This is inherited from lptools.py's own _detect_degeneracy and is
    # harmless there (and here) only because neither dispatch branch
    # checks for an explicit 'full' -- both just handle 'point' and
    # 'line' and let anything else, including this mislabeled 'plane',
    # fall through to full treatment. Don't rely on degen == 'full' for 2D.
    degen = result["degen"]
    if degen == "point":
        result["datapoints"] = [[val_limits[0][0], val_limits[1][0]]]
        result["triang"] = []
        return
    if degen == "line":
        if result["degen_axes"][0]:
            x_pts = [val_limits[0][0], val_limits[0][0]]
            y_pts = [val_limits[1][0], val_limits[1][1]]
        else:
            x_pts = [val_limits[0][0], val_limits[0][1]]
            y_pts = [val_limits[1][0], val_limits[1][0]]
        result["datapoints"] = [[x, y] for x, y in zip(x_pts, y_pts)]
        result["triang"] = []
        return

    # full
    if all(t == "rate" for t in ax_type):
        solver = HighsRateSolver(bundle.rate_lp, bundle.reaction_ids, bundle.rxn_index, [])
        vertices = trace_polygon_rate_rate(solver, axes[0][0], axes[1][0])
    else:
        ax0_obj = bundle.rate_axis(axes[0][0]) if ax_type[0] == "rate" \
            else bundle.yield_axis(axes[0][0], axes[0][1])
        ax1_obj = bundle.rate_axis(axes[1][0]) if ax_type[1] == "rate" \
            else bundle.yield_axis(axes[1][0], axes[1][1])
        upper, lower = trace_boundary_adaptive(bundle.rate_solver, ax0_obj, ax1_obj, max_depth=max(5, int(math.log2(max(points, 2)))))
        vertices = (upper + list(reversed(lower))) if upper and lower else (upper or lower)
        if len(vertices) > 1 and vertices[0] != vertices[-1]:
            vertices.append(vertices[0])

    if not vertices:
        raise Exception("Could not trace any boundary. Problem may be infeasible.")

    n_v = len(vertices)
    if n_v > 2 and vertices[0] == vertices[-1]:
        n_v -= 1
    result["triang"] = [[0, i, i + 1] for i in range(1, n_v - 1)] if n_v >= 3 else []
    result["datapoints"] = [[v[0], v[1]] for v in vertices]
    result["is_approximate"] = any(t == "yield" for t in ax_type)


def _ring_cleanup(ring, scale, tol=1e-9):
    """Drop consecutive (and wrap-around) duplicates, measured in
    axis-normalized coordinates, and return the ring counter-clockwise."""
    out = []
    for p in ring:
        if not out or (abs(p[0] - out[-1][0]) / scale[0] > tol or abs(p[1] - out[-1][1]) / scale[1] > tol):
            out.append(p)
    while len(out) > 1 and abs(out[0][0] - out[-1][0]) / scale[0] <= tol \
            and abs(out[0][1] - out[-1][1]) / scale[1] <= tol:
        out.pop()
    if len(out) >= 3:
        a2 = sum(out[k][0] * out[(k + 1) % len(out)][1] - out[(k + 1) % len(out)][0] * out[k][1]
                 for k in range(len(out)))
        if a2 < 0:
            out.reverse()
    return out


def _ring_angles(ring, scale):
    """Angle in [0, 2pi) of each vertex around the ring's vertex centroid,
    in axis-normalized coordinates. Monotone around a convex ring."""
    cx = sum(p[0] for p in ring) / len(ring)
    cy = sum(p[1] for p in ring) / len(ring)
    return [math.atan2((p[1] - cy) / scale[1], (p[0] - cx) / scale[0]) % (2 * math.pi) for p in ring]


def _stitch_rings(A, B, tA, tB, triang):
    """Join two closed convex rings (index lists, CCW, A below B) into an
    outward-facing triangle band, merging vertices by angle. Robust to
    rings with very different vertex counts and to degenerate rings
    (1 or 2 vertices), unlike the greedy shortest-diagonal walker."""
    # rotate each ring to start at its smallest angle
    ia = min(range(len(A)), key=lambda k: tA[k])
    ib = min(range(len(B)), key=lambda k: tB[k])
    A, tA = A[ia:] + A[:ia], tA[ia:] + tA[:ia]
    B, tB = B[ib:] + B[:ib], tB[ib:] + tB[:ib]
    # make angles non-decreasing along the ring, then close it at +2pi
    def unwrap(t):
        u = [t[0]]
        for v in t[1:]:
            while v < u[-1]:
                v += 2 * math.pi
            u.append(v)
        return u
    tA, tB = unwrap(tA), unwrap(tB)
    A2, tA2 = A + [A[0]], tA + [tA[0] + 2 * math.pi]
    B2, tB2 = B + [B[0]], tB + [tB[0] + 2 * math.pi]
    i = j = 0
    while i < len(A2) - 1 or j < len(B2) - 1:
        adv_a = j >= len(B2) - 1 or (i < len(A2) - 1 and tA2[i + 1] <= tB2[j + 1])
        if adv_a:
            if A2[i] != A2[i + 1]:
                triang.append([A2[i], A2[i + 1], B2[j]])
            i += 1
        else:
            if B2[j] != B2[j + 1]:
                triang.append([A2[i], B2[j + 1], B2[j]])
            j += 1


def build_slice_mesh(slices, rate_indices, yield_idx):
    """Turn per-slice 2D polygons into a closed, consistently outward-
    oriented 3D triangle mesh.

    Replaces the stitching of lptools._trace_3d_slice_polygon, whose
    greedy shortest-diagonal walker (_triangulate_strips) compares raw
    distances: when the two rate axes differ in scale it can run around
    one ring before the other, folding triangles through the interior
    and leaving parts of the side uncovered (visible as see-through
    gaps from some view angles). Here, rings are de-duplicated and made
    CCW, and adjacent rings are merged by angle around their centroids
    in axis-normalized coordinates -- correct because each slice is a
    convex polygon (rate/rate projection at a fixed yield).

    slices: iterable of (y_val, polygon_2d). Empty slices are skipped.
    Returns (datapoints, triang, slice_outlines).
    """
    slices = sorted(((y, list(p)) for y, p in slices if p), key=lambda s: s[0])
    allp = [pt for _, p in slices for pt in p]
    if not allp:
        return [], [], []
    scale = [max(1e-12, max(p[k] for p in allp) - min(p[k] for p in allp)) for k in (0, 1)]

    datapoints: List[List[float]] = []
    slice_outlines: List[List[int]] = []
    angles: List[List[float]] = []
    for y_val, poly in slices:
        ring = _ring_cleanup(poly, scale)
        if not ring:
            continue
        idx_list = []
        for pt in ring:
            p3d = [0.0, 0.0, 0.0]
            p3d[rate_indices[0]] = pt[0]
            p3d[rate_indices[1]] = pt[1]
            p3d[yield_idx] = y_val
            idx_list.append(len(datapoints))
            datapoints.append(p3d)
        slice_outlines.append(idx_list)
        angles.append(_ring_angles(ring, scale))

    if not slice_outlines:
        return [], [], []

    triang: List[List[int]] = []
    for s in range(len(slice_outlines) - 1):
        _stitch_rings(slice_outlines[s], slice_outlines[s + 1], angles[s], angles[s + 1], triang)

    first, last = slice_outlines[0], slice_outlines[-1]
    if len(first) >= 3:                       # bottom cap faces -yield
        for k in range(1, len(first) - 1):
            triang.append([first[0], first[k + 1], first[k]])
    if len(last) >= 3 and len(slice_outlines) > 1:   # top cap faces +yield
        for k in range(1, len(last) - 1):
            triang.append([last[0], last[k], last[k + 1]])

    # orientation above assumes (rate0, rate1, yield) is a right-handed
    # ordering of the plot axes; flip everything for an odd permutation
    perm = [rate_indices[0], rate_indices[1], yield_idx]
    inversions = sum(1 for a in range(3) for b in range(a + 1, 3) if perm[a] > perm[b])
    if inversions % 2:
        triang = [[t[0], t[2], t[1]] for t in triang]
    return datapoints, triang, slice_outlines


def _fill_3d(result, model, reaction_ids, constraints, bundle, axes, ax_type,
            val_limits, points, n_workers):
    degen = result["degen"]
    degen_axes = result["degen_axes"]

    if degen == "point":
        result["datapoints"] = [[val_limits[i][0] for i in range(3)]]
        result["triang"] = []
        return

    if degen == "line":
        free_ax = [i for i, d in enumerate(degen_axes) if not d][0]
        pts_3d = []
        for val in (val_limits[free_ax][0], val_limits[free_ax][1]):
            pt = [val_limits[i][0] for i in range(3)]
            pt[free_ax] = val
            pts_3d.append(pt)
        result["datapoints"] = pts_3d
        result["triang"] = []
        return

    if degen == "plane":
        free_axes = [i for i, d in enumerate(degen_axes) if not d]
        fixed_axis = [i for i, d in enumerate(degen_axes) if d][0]
        fixed_val = val_limits[fixed_axis][0]
        make_fix = fix_rate_axis(axes[fixed_axis][0]) if ax_type[fixed_axis] == "rate" \
            else fix_yield_axis(axes[fixed_axis][0], axes[fixed_axis][1])
        plane_constraints = list(constraints)
        # the fixed axis is constant for the WHOLE 2D sub-trace, so bake
        # it into the sub-trace's own baseline constraints rather than
        # using a per-value fix slot (unlike trace_boundary_adaptive's
        # axis 0, which varies).
        fix_coeffs, fix_rhs = make_fix(fixed_val)
        plane_constraints.append([fix_coeffs, "=", fix_rhs])

        sub_axes = [axes[free_axes[0]], axes[free_axes[1]]]
        sub_types = [ax_type[free_axes[0]], ax_type[free_axes[1]]]
        plane_bundle = _SolverBundle(model, reaction_ids, plane_constraints, num_fix_slots=1)

        if all(t == "rate" for t in sub_types):
            solver = HighsRateSolver(plane_bundle.rate_lp, plane_bundle.reaction_ids,
                                     plane_bundle.rxn_index, [])
            polygon_2d = trace_polygon_rate_rate(solver, sub_axes[0][0], sub_axes[1][0])
        else:
            a0 = plane_bundle.rate_axis(sub_axes[0][0]) if sub_types[0] == "rate" \
                else plane_bundle.yield_axis(sub_axes[0][0], sub_axes[0][1])
            a1 = plane_bundle.rate_axis(sub_axes[1][0]) if sub_types[1] == "rate" \
                else plane_bundle.yield_axis(sub_axes[1][0], sub_axes[1][1])
            upper, lower = trace_boundary_adaptive(plane_bundle.rate_solver, a0, a1)
            polygon_2d = (upper + list(reversed(lower))) if upper and lower else (upper or lower)
            if len(polygon_2d) > 1 and polygon_2d[0] != polygon_2d[-1]:
                polygon_2d.append(polygon_2d[0])

        datapoints = []
        for pt in polygon_2d:
            p3d = [0.0, 0.0, 0.0]
            p3d[free_axes[0]] = pt[0]
            p3d[free_axes[1]] = pt[1]
            p3d[fixed_axis] = fixed_val
            datapoints.append(p3d)
        n_pts = len(datapoints)
        if n_pts > 1 and all(abs(datapoints[0][k] - datapoints[-1][k]) < 1e-8 for k in range(3)):
            n_pts -= 1
        result["triang"] = [[0, i, i + 1] for i in range(1, n_pts - 1)] if n_pts >= 3 else []
        result["datapoints"] = datapoints
        return

    # full 3D
    n_yields = sum(1 for t in ax_type if t == "yield")
    if n_yields == 0:
        solver = HighsRateSolver(bundle.rate_lp, bundle.reaction_ids, bundle.rxn_index, [])
        vertices, triang, face_polys = trace_polytope_3d_rate(
            solver, axes[0][0], axes[1][0], axes[2][0])
        result["datapoints"] = [list(v) for v in vertices]
        result["triang"] = triang
        result["face_polys"] = face_polys
    elif n_yields == 1:
        yield_idx = next(i for i, t in enumerate(ax_type) if t == "yield")
        rate_indices = [i for i, t in enumerate(ax_type) if t == "rate"]
        y_lo, y_hi = val_limits[yield_idx]
        y_space = [y_lo + (y_hi - y_lo) * i / (points - 1) for i in range(points)] if points > 1 else [y_lo]
        make_fix = fix_yield_axis(axes[yield_idx][0], axes[yield_idx][1])
        if n_workers == "auto":
            # each slice is a cheap 2D rate-rate trace whose Python bookkeeping holds the GIL,
            # so the speedup levels off at about 4 threads (benchmarked on ECC2); threads already
            # pay off with only one or two slices per worker
            n_workers = auto_n_workers(len(y_space), min_units_per_worker=1, max_workers=4)

        # slices are independent; trace_3d_slice_polygon falls back to the
        # sequential version itself for n_workers <= 1
        slices = trace_3d_slice_polygon(
            bundle.rate_lp, bundle.reaction_ids, bundle.rxn_index, bundle.rate_fix_rows,
            make_fix, axes[rate_indices[0]][0], axes[rate_indices[1]][0], y_space,
            n_workers=n_workers)

        datapoints, triang, slice_outlines = build_slice_mesh(slices, rate_indices, yield_idx)
        result["datapoints"] = datapoints
        result["triang"] = triang
        result["slice_outlines"] = slice_outlines
        result["is_approximate"] = True
    else:
        # 2 or 3 yield axes: grid-scanning fallback. Unlike every other
        # branch this needs TWO simultaneous fix slots (axis 0's value and
        # axis 1's value both pinned when reading axis 2), so it gets its
        # own bundle built with num_fix_slots=2 rather than reusing the
        # single-slot `bundle` used for the axis limits above.
        grid_bundle = _SolverBundle(model, reaction_ids, constraints, num_fix_slots=2)

        def grid_axes(b):
            def grid_axis(i, needs_own_solver):
                if ax_type[i] == "rate":
                    return GridAxis("rate", b.rate_solver, axes[i][0])
                # axis 0 is only ever pinned (make_fix), never optimized, so
                # it doesn't need a yield solver of its own
                ys = b.yield_solver_for(axes[i][1]) if needs_own_solver else None
                return GridAxis("yield", b.rate_solver, axes[i][0],
                                den=axes[i][1], yield_solver=ys)
            return grid_axis(0, False), grid_axis(1, True), grid_axis(2, True)

        # builds every yield LP the workers need, on this thread, before any
        # clone() is taken -- so workers only ever passModel shared LPs
        g0, g1, g2 = grid_axes(grid_bundle)
        if n_workers == "auto":
            # grid rows are expensive (many yield LPs each), scales almost linearly with the threads
            n_workers = auto_n_workers(points, min_units_per_worker=1)
        y_range_global = max(1e-10, abs(val_limits[1][1] - val_limits[1][0]))
        datapoints, triang = trace_grid_3d(
            g0, g1, g2, (val_limits[0][0], val_limits[0][1]), y_range_global, points=points,
            n_workers=n_workers, make_axes=lambda: grid_axes(grid_bundle.clone()))
        if not datapoints:
            raise Exception("No feasible slices found. Problem may be infeasible.")
        result["datapoints"] = datapoints
        result["triang"] = triang
        result["is_approximate"] = True


def orient_closed_mesh(datapoints, triang):
    """Make a triangle mesh consistently oriented with outward normals.

    Flood-fills orientation across shared edges (a neighbour must
    traverse a shared edge in the opposite direction), then flips the
    whole mesh if its signed volume is negative. Returns
    (triang, is_closed); is_closed is True only if every edge is
    shared by exactly two triangles and the fill succeeded without
    contradiction -- the precondition for back-face culling. Meshes
    that aren't closed are returned unchanged with is_closed=False.
    Degenerate triangles (repeated vertex index) are dropped.
    """
    from collections import defaultdict, deque
    tris = [list(t) for t in triang if len({t[0], t[1], t[2]}) == 3]
    edge_tris = defaultdict(list)
    for ti, t in enumerate(tris):
        for k in range(3):
            edge_tris[frozenset((t[k], t[(k + 1) % 3]))].append(ti)
    if not tris or any(len(v) != 2 for v in edge_tris.values()):
        return [list(t) for t in triang], False

    def directed(t):
        return {(t[k], t[(k + 1) % 3]) for k in range(3)}

    done = [False] * len(tris)
    for seed in range(len(tris)):
        if done[seed]:
            continue
        done[seed] = True
        queue = deque([seed])
        while queue:
            ti = queue.popleft()
            dt = directed(tris[ti])
            for (a, b) in dt:
                for nj in edge_tris[frozenset((a, b))]:
                    if nj == ti:
                        continue
                    if not done[nj]:
                        if (a, b) in directed(tris[nj]):
                            tris[nj] = [tris[nj][0], tris[nj][2], tris[nj][1]]
                        done[nj] = True
                        queue.append(nj)
                    elif (a, b) in directed(tris[nj]):
                        return [list(t) for t in triang], False   # non-orientable

    vol = 0.0
    for a, b, c in tris:
        A, B, C = datapoints[a], datapoints[b], datapoints[c]
        vol += (A[0] * (B[1] * C[2] - B[2] * C[1]) - A[1] * (B[0] * C[2] - B[2] * C[0])
                + A[2] * (B[0] * C[1] - B[1] * C[0]))
    if vol < 0:
        tris = [[t[0], t[2], t[1]] for t in tris]
    return tris, True


def _ensure_plotting():
    global plt, Poly3DCollection, CulledTriCollection
    import matplotlib.pyplot as _plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection as _poly3d
    plt = _plt
    Poly3DCollection = _poly3d
    CulledTriCollection = _make_culled_collection_class(_poly3d)


def _make_culled_collection_class(base):
    """Poly3DCollection for a closed, outward-oriented triangle mesh that
    hides back-facing triangles on every redraw. mplot3d has no
    z-buffer and depth-sorts whole triangles, so on a closed surface
    back faces regularly win the sort and the "inside" shows through;
    culling them removes that whole class of artifacts. Front-facing
    is decided from the triangle's winding after projection to screen
    space, so it follows rotation, zoom and axis aspect automatically.
    If anything about the projection fails (e.g. a future mplot3d
    internals change), it silently draws all triangles."""
    import numpy as np
    from mpl_toolkits.mplot3d import proj3d

    class _Culled(base):
        def __init__(self, tri_verts, facecolors, **kw):
            self._all_verts = np.asarray(tri_verts, dtype=float)      # (n, 3, 3)
            self._all_fc = np.asarray(facecolors)
            super().__init__(list(self._all_verts), facecolors=self._all_fc,
                             edgecolors=self._all_fc, **kw)

        def do_3d_projection(self):
            try:
                v = self._all_verts.reshape(-1, 3)
                xs, ys, _ = proj3d.proj_transform(v[:, 0], v[:, 1], v[:, 2], self.axes.M)
                xs = np.asarray(xs).reshape(-1, 3)
                ys = np.asarray(ys).reshape(-1, 3)
                area2 = ((xs[:, 1] - xs[:, 0]) * (ys[:, 2] - ys[:, 0])
                         - (xs[:, 2] - xs[:, 0]) * (ys[:, 1] - ys[:, 0]))
                vis = area2 > 0
                if not vis.any():
                    vis[:] = True
            except Exception:
                vis = np.ones(len(self._all_verts), dtype=bool)
            base.set_verts(self, list(self._all_verts[vis]))
            base.set_facecolor(self, self._all_fc[vis])
            base.set_edgecolor(self, self._all_fc[vis])
            return super().do_3d_projection()

    return _Culled


plt = None
Poly3DCollection = None
CulledTriCollection = None


def plot_flux_space_highs(model, axes, **kwargs) -> Tuple[list, list, object]:
    """Thin rendering wrapper around plot_flux_space_data_highs: computes
    the data (see that function's docstring for what's covered and what
    isn't), then renders it with matplotlib calls copied essentially
    unmodified from plot_flux_space itself -- this layer is intentionally
    almost no new logic, just new (already-validated) data feeding proven
    rendering code. NOT run against a real display/model here; only
    checked for not crashing headlessly (matplotlib's Agg backend) across
    the same scenarios plot_flux_space_data_highs's own tests cover --
    visual correctness of the actual figures still needs a real look.

    Returns (datapoints, triang, plot1) -- same contract as
    plot_flux_space itself.
    """
    _ensure_plotting()
    d = plot_flux_space_data_highs(model, axes, **kwargs)
    num_axes = d["num_axes"]
    ax_name = d["ax_name"]
    ax_limits = d["ax_limits"]
    degen = d["degen"]
    datapoints = d["datapoints"]
    triang = d["triang"]
    show = d["show"]
    cmap = d["cmap"]
    is_approx = d.get("is_approximate", False)

    def _maybe_show():
        if show:
            try:
                plt.show()
            except UserWarning:
                pass

    if num_axes == 2:
        if degen == "point" or len(datapoints) == 1:
            plot1 = plt.plot([datapoints[0][0]], [datapoints[0][1]], "o")[0]
        elif degen == "line" or not triang:
            x = [p[0] for p in datapoints]
            y = [p[1] for p in datapoints]
            plot1 = plt.plot(x, y, linewidth=1.5)[0]
        else:
            x = [p[0] for p in datapoints]
            y = [p[1] for p in datapoints]
            plot1 = plt.fill(x, y, linewidth=0.5)[0]
            if is_approx:
                plot1.axes.set_title("approximate", fontsize=8, color="gray")
        plot1.axes.set_xlabel(ax_name[0])
        plot1.axes.set_ylabel(ax_name[1])
        plot1.axes.set_xlim(ax_limits[0][0] * 1.05, ax_limits[0][1] * 1.05)
        plot1.axes.set_ylim(ax_limits[1][0] * 1.05, ax_limits[1][1] * 1.05)
        _maybe_show()
        return datapoints, triang, plot1

    # 3D
    ax3 = plt.figure().add_subplot(projection="3d")
    ax3.set_xlim(ax_limits[0])
    ax3.set_ylim(ax_limits[1])
    ax3.set_zlim(ax_limits[2])
    ax3.set_xlabel(ax_name[0])
    ax3.set_ylabel(ax_name[1])
    ax3.set_zlabel(ax_name[2])

    if degen == "point" or (len(datapoints) == 1):
        ax3.scatter([datapoints[0][0]], [datapoints[0][1]], [datapoints[0][2]], s=50)
        _maybe_show()
        return datapoints, triang, ax3
    if degen == "line" or (not triang and len(datapoints) <= 2):
        xs = [p[0] for p in datapoints]
        ys = [p[1] for p in datapoints]
        zs = [p[2] for p in datapoints]
        ax3.plot3D(xs, ys, zs, linewidth=1.5)
        _maybe_show()
        return datapoints, triang, ax3

    if is_approx:
        ax3.set_title("approximate", fontsize=8, color="gray")

    face_polys = d.get("face_polys")
    slice_outlines = d.get("slice_outlines")

    def _normal_color(face_pts):
        import numpy as _np
        pts = _np.array(face_pts)
        if len(pts) < 3:
            return 0.5
        e1, e2 = pts[1] - pts[0], pts[2] - pts[0]
        normal = _np.array([
            e1[1] * e2[2] - e1[2] * e2[1],
            e1[2] * e2[0] - e1[0] * e2[2],
            e1[0] * e2[1] - e1[1] * e2[0],
        ])
        length = (normal.dot(normal)) ** 0.5
        if length > 0:
            normal = normal / length
        # atan2 term weighted by the horizontal part of the normal: same
        # colours as lptools on side faces, but continuous towards
        # horizontal faces, where atan2 of rounding noise would
        # otherwise give random colours (speckled flat faces)
        h = math.hypot(normal[0], normal[1])
        ang = math.atan2(normal[1], normal[0]) if h > 1e-6 else 0.0
        return ang * h + 1.5 * normal[2]

    if face_polys is not None and face_polys:
        poly_verts = [[datapoints[i] for i in face] for face in face_polys]
        color_vals = [_normal_color(v) for v in poly_verts]
        mn, mx = min(color_vals), max(color_vals)
        rng = mx - mn if mx > mn else 1
        face_colors = plt.get_cmap(cmap)([(c - mn) / rng for c in color_vals])
        face_colors[:, 3] = 1.0
        collection = Poly3DCollection(poly_verts, facecolors=face_colors, edgecolors="black", linewidths=1.0)
        ax3.add_collection3d(collection)
        plot1 = collection
    elif triang:
        # orient outward + detect closedness; closed meshes get back-face
        # culling and face-coloured edges (closes antialiasing cracks)
        draw_triang, closed = orient_closed_mesh(datapoints, triang)
        if closed:
            # drop zero-area slivers from what is drawn (only after the
            # closedness check, which needs them): their normals, colour
            # and front/back test are all numerical noise
            import numpy as _np
            _P = _np.asarray(datapoints, float)
            _P = (_P - _P.min(0)) / _np.maximum(_np.ptp(_P, axis=0), 1e-12)
            _T = _np.asarray(draw_triang)
            _a = _np.linalg.norm(_np.cross(_P[_T[:, 1]] - _P[_T[:, 0]], _P[_T[:, 2]] - _P[_T[:, 0]]), axis=1)
            if (_a > 1e-9).any():
                draw_triang = [t for t, keep in zip(draw_triang, _a > 1e-9) if keep]
        tri_verts = [[datapoints[i] for i in t] for t in draw_triang]
        color_vals = [_normal_color(v) for v in tri_verts]
        mn, mx = min(color_vals), max(color_vals)
        rng = mx - mn if mx > mn else 1
        face_colors = plt.get_cmap(cmap)([(c - mn) / rng for c in color_vals])
        face_colors[:, 3] = 1.0
        if closed:
            collection = CulledTriCollection(tri_verts, face_colors, linewidths=0.3)
        else:
            collection = Poly3DCollection(tri_verts, facecolors=face_colors, edgecolors="none", linewidths=0)
        ax3.add_collection3d(collection)
        if slice_outlines:
            for idx_list in slice_outlines:
                pts = [datapoints[i] for i in idx_list] + [datapoints[idx_list[0]]]
                ax3.plot([p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts],
                         color="gray", linewidth=0.4)
        plot1 = collection
    else:
        plot1 = ax3.scatter([p[0] for p in datapoints], [p[1] for p in datapoints],
                            [p[2] for p in datapoints], s=20)

    _maybe_show()
    return datapoints, triang, plot1
