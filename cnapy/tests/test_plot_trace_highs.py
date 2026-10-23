"""Tests plot_trace_highs.py against a hand-verifiable 2D pentagon:

    X, Y in [0, 10], X + Y <= 12

Vertices (0,0), (10,0), (10,2), (2,10), (0,10); shoelace area = 68
(100 for the full square minus the 32 for the corner triangle cut off
by X+Y<=12 -- both computed independently as a cross-check on the
traced result, since matching a shoelace-formula area is far more
robust than trying to match exact vertex order/positions when HiGHS's
choice of optimal vertex on a degenerate face isn't fully determined).
"""

import unittest

import scipy.sparse as sp


from cnapy import highs_lp_cache as hlc
from cnapy import plot_trace_highs as pth

REACTION_IDS = ["X", "Y"]
RXN_INDEX = {"X": 0, "Y": 1}
COL_LOWER = [0.0, 0.0]
COL_UPPER = [10.0, 10.0]
TRUE_AREA = 68.0


def pentagon_lp():
    S = sp.lil_matrix((0, 2))  # no mass-balance rows needed for this toy case
    extra_rows = [({0: 1.0, 1: 1.0}, float("-inf"), 12.0)]  # X + Y <= 12
    lp, fix_rows = hlc._build_rate_lp_arrays(S, COL_LOWER, COL_UPPER, extra_rows=extra_rows)
    return lp, fix_rows


class TestPolygonTracer(unittest.TestCase):
    def test_sequential_area_matches_reference(self):
        lp, fix_rows = pentagon_lp()
        solver = hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_rows)
        vertices = pth.trace_polygon_rate_rate(solver, {"X": 1.0}, {"Y": 1.0})
        area = pth.polygon_area(vertices)
        self.assertAlmostEqual(area, TRUE_AREA, places=3, msg=f"vertices={vertices}")

    def test_parallel_area_matches_reference(self):
        lp, fix_rows = pentagon_lp()
        vertices = pth.trace_polygon_rate_rate_parallel(
            lp, REACTION_IDS, RXN_INDEX, {"X": 1.0}, {"Y": 1.0}, n_workers=3)
        area = pth.polygon_area(vertices)
        self.assertAlmostEqual(area, TRUE_AREA, places=3, msg=f"vertices={vertices}")

    def test_sequential_and_parallel_agree(self):
        lp, fix_rows = pentagon_lp()
        solver = hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_rows)
        seq = pth.trace_polygon_rate_rate(solver, {"X": 1.0}, {"Y": 1.0})
        par = pth.trace_polygon_rate_rate_parallel(
            lp, REACTION_IDS, RXN_INDEX, {"X": 1.0}, {"Y": 1.0}, n_workers=4)
        self.assertAlmostEqual(pth.polygon_area(seq), pth.polygon_area(par), places=6)
        # same vertex *set* (order/starting point may legitimately differ)
        seq_set = {tuple(round(c, 6) for c in p) for p in seq}
        par_set = {tuple(round(c, 6) for c in p) for p in par}
        self.assertEqual(seq_set, par_set, msg=f"seq={seq}\npar={par}")

    def test_all_vertices_feasible(self):
        lp, fix_rows = pentagon_lp()
        solver = hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_rows)
        vertices = pth.trace_polygon_rate_rate(solver, {"X": 1.0}, {"Y": 1.0})
        for x, y in vertices:
            self.assertGreaterEqual(x, -1e-6)
            self.assertGreaterEqual(y, -1e-6)
            self.assertLessEqual(x, 10 + 1e-6)
            self.assertLessEqual(y, 10 + 1e-6)
            self.assertLessEqual(x + y, 12 + 1e-6)

    def test_expected_vertex_set(self):
        lp, fix_rows = pentagon_lp()
        solver = hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_rows)
        vertices = pth.trace_polygon_rate_rate(solver, {"X": 1.0}, {"Y": 1.0})
        expected = {(0.0, 0.0), (10.0, 0.0), (10.0, 2.0), (2.0, 10.0), (0.0, 10.0)}
        got = {tuple(round(c, 6) for c in p) for p in vertices}
        self.assertEqual(got, expected, msg=f"vertices={vertices}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
