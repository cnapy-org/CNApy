"""Tests trace_grid_3d / GridAxis.

Reference shape: the 10x10x10 cube with one corner cut off
(X, Y, Z in [0,10], X+Y+Z <= 25), whose exact volume 1000 - 125/6 =
979.1667 is already verified independently in test_trace_polytope_3d.py.

Two ways of reusing it:
  * all three axes RATE: the grid tracer's convex-hull volume should
    match 979.1667. It's an approximate method in general, but for a
    convex polytope whose corner x-values (0, 5, 10) land exactly on the
    scan grid, the sampled boundary points include every true vertex,
    so the match is essentially exact -- and tight enough that a
    collapsed or partial mesh can't hide.
  * Y and Z as YIELDS over a denominator S pinned to a constant (bounds
    [5,5]): Y/S = Y/5 and Z/5 are then plain linear rescalings, so the
    expected hull volume is 979.1667 / 25 = 39.1667.

(An earlier version of this file checked only feasibility and "reaches
> 1.5 at x=0", and passed while a stale-fix-slot bug had collapsed every
x-slice after the first to a single point. These tests are written to
fail on exactly that.)
"""

import unittest

import numpy as np
import scipy.sparse as sp
from scipy.spatial import ConvexHull


from cnapy import highs_lp_cache as hlc
from cnapy import plot_trace_highs as pth

REACTION_IDS = ["X", "Y", "Z", "S"]
RXN_INDEX = {"X": 0, "Y": 1, "Z": 2, "S": 3}
EXACT_VOLUME = 1000.0 - 125.0 / 6.0


def _rate_only_axes():
    col_lower = [0.0, 0.0, 0.0, 5.0]
    col_upper = [10.0, 10.0, 10.0, 5.0]
    lp, fix_rows = hlc._build_rate_lp_arrays(
        sp.lil_matrix((0, 4)), col_lower, col_upper,
        extra_rows=[({0: 1.0, 1: 1.0, 2: 1.0}, float("-inf"), 25.0)], num_fix_slots=2)
    solver = hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_rows)
    return (pth.GridAxis("rate", solver, {"X": 1.0}),
            pth.GridAxis("rate", solver, {"Y": 1.0}),
            pth.GridAxis("rate", solver, {"Z": 1.0}))


def _yield_axes(num_fix_slots_ax1=1, num_fix_slots_ax2=2):
    col_lower = [0.0, 0.0, 0.0, 5.0]
    col_upper = [10.0, 10.0, 10.0, 5.0]  # S pinned to a constant via its bounds
    Smat = sp.lil_matrix((0, 4))
    rate_lp, rate_fix = hlc._build_rate_lp_arrays(
        Smat, col_lower, col_upper,
        extra_rows=[({0: 1.0, 1: 1.0, 2: 1.0}, float("-inf"), 25.0)], num_fix_slots=2)
    rate_solver = hlc.HighsRateSolver(rate_lp, REACTION_IDS, RXN_INDEX, rate_fix)

    def yield_solver(slots):
        lp, den_row, t_col, fix_rows = hlc._build_yopt_lp_arrays(
            Smat, col_lower, col_upper, den_coeffs={3: 1.0},
            extra_rows=[({0: 1.0, 1: 1.0, 2: 1.0}, "<=", 25.0)], num_fix_slots=slots)
        return hlc.HighsYieldSolver(lp, REACTION_IDS, RXN_INDEX, den_row, t_col, fix_rows)

    ax0 = pth.GridAxis("rate", rate_solver, {"X": 1.0})
    # ax1 = Y/S only ever needs slot 0 (pinning ax0); ax2 = Z/S needs 0 AND 1
    ax1 = pth.GridAxis("yield", rate_solver, {"Y": 1.0}, den={"S": 1.0},
                       yield_solver=yield_solver(num_fix_slots_ax1))
    ax2 = pth.GridAxis("yield", rate_solver, {"Z": 1.0}, den={"S": 1.0},
                       yield_solver=yield_solver(num_fix_slots_ax2))
    return ax0, ax1, ax2


def _hull_volume(datapoints):
    return ConvexHull(np.array(datapoints)).volume


class TestGrid3DRateOnly(unittest.TestCase):
    def test_volume_matches_exact_polytope(self):
        for points in (5, 9, 17):
            ax0, ax1, ax2 = _rate_only_axes()
            dp, triang = pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), 10.0, points=points)
            self.assertAlmostEqual(_hull_volume(dp), EXACT_VOLUME, places=3,
                                   msg=f"points={points}")

    def test_every_x_slice_spans_full_y_range(self):
        # Regression test for the stale-slot bug: after the first
        # x-slice, ax1's range used to collapse to the previous slice's
        # last y_val. At every x in [0,10], y should span all of [0,10].
        ax0, ax1, ax2 = _rate_only_axes()
        dp, _ = pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), 10.0, points=9)
        by_x = {}
        for x, y, z in dp:
            by_x.setdefault(round(x, 6), []).append(y)
        self.assertEqual(len(by_x), 9)
        for x, ys in by_x.items():
            self.assertAlmostEqual(min(ys), 0.0, places=6, msg=f"x={x}")
            self.assertAlmostEqual(max(ys), 10.0, places=6, msg=f"x={x}")

    def test_repeated_calls_on_same_solvers_give_identical_results(self):
        ax0, ax1, ax2 = _rate_only_axes()
        runs = [pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), 10.0, points=5) for _ in range(3)]
        for dp, triang in runs[1:]:
            self.assertEqual(len(dp), len(runs[0][0]))
            self.assertEqual(triang, runs[0][1])
            for a, b in zip(dp, runs[0][0]):
                for u, v in zip(a, b):
                    self.assertAlmostEqual(u, v, places=6)

    def test_triangles_reference_valid_points(self):
        ax0, ax1, ax2 = _rate_only_axes()
        dp, triang = pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), 10.0, points=5)
        self.assertTrue(triang)
        self.assertLess(max(i for tri in triang for i in tri), len(dp))
        self.assertGreaterEqual(min(i for tri in triang for i in tri), 0)


class TestGrid3DWithYields(unittest.TestCase):
    def test_volume_matches_rescaled_exact_polytope(self):
        ax0, ax1, ax2 = _yield_axes()
        dp, triang = pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), 2.0, points=9)
        self.assertAlmostEqual(_hull_volume(dp), EXACT_VOLUME / 25.0, places=3)

    def test_points_are_feasible_in_original_coordinates(self):
        ax0, ax1, ax2 = _yield_axes()
        dp, _ = pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), 2.0, points=9)
        for x, y, z in dp:
            self.assertGreaterEqual(y, -1e-6)
            self.assertLessEqual(y, 2.0 + 1e-6)
            self.assertGreaterEqual(z, -1e-6)
            self.assertLessEqual(z, 2.0 + 1e-6)
            self.assertLessEqual(x + 5 * y + 5 * z, 25.0 + 1e-3)

    def test_repeated_calls_on_same_solvers_give_identical_results(self):
        ax0, ax1, ax2 = _yield_axes()
        first = pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), 2.0, points=5)
        for _ in range(2):
            again = pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), 2.0, points=5)
            self.assertEqual(len(again[0]), len(first[0]))
            for a, b in zip(again[0], first[0]):
                for u, v in zip(a, b):
                    self.assertAlmostEqual(u, v, places=6)

    def test_missing_fix_slot_fails_loudly(self):
        # ax2 (needs slots 0 AND 1) built with only one slot: pinning
        # ax1's value on it would be silently skipped if this weren't an
        # error, producing a plausible-looking wrong mesh.
        ax0, ax1, ax2 = _yield_axes(num_fix_slots_ax2=1)
        with self.assertRaises(ValueError):
            pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), 2.0, points=5)



class TestGridThreaded(unittest.TestCase):
    """Threaded scan (n_workers > 1 with a make_axes factory giving each
    worker thread its own solvers) must give the sequential result, x
    order included."""

    def _check(self, factory, y_range, points):
        ax0, ax1, ax2 = factory()
        seq = pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), y_range, points=points)
        made = []

        def make_axes():
            axs = factory()
            made.append(axs)
            return axs
        for w in (2, 3, 16):
            ax0, ax1, ax2 = factory()
            par = pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), y_range, points=points,
                                    n_workers=w, make_axes=make_axes)
            # samples identical and in the same order; triangle indices
            # aren't compared (equal-length cell diagonals are a tie that
            # rounding noise can break either way), the hull volume is
            np.testing.assert_allclose(np.array(par[0]), np.array(seq[0]), atol=1e-9)
            self.assertEqual(len(par[1]), len(seq[1]))
            self.assertAlmostEqual(_hull_volume(par[0]), _hull_volume(seq[0]), places=6)
        self.assertTrue(made)          # the factory was really used

    def test_rate_axes(self):
        self._check(_rate_only_axes, 10.0, 9)

    def test_yield_axes(self):
        self._check(_yield_axes, 2.0, 9)

    def test_without_factory_runs_sequentially(self):
        ax0, ax1, ax2 = _rate_only_axes()
        seq = pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), 10.0, points=5)
        ax0, ax1, ax2 = _rate_only_axes()
        par = pth.trace_grid_3d(ax0, ax1, ax2, (0.0, 10.0), 10.0, points=5, n_workers=4)
        self.assertEqual(par, seq)

if __name__ == "__main__":
    unittest.main(verbosity=2)
