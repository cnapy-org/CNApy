"""Tests trace_3d_slice_polygon / trace_3d_slice_polygon_sequential
against a known family of cross-sections:

    X, Y, Z in [0, 10],  X + Y + Z <= 15

Slicing on Z = z fixes X + Y <= 15 - z =: C, giving:
    C in (0, 10]:  a triangle,        area = C^2 / 2
    C in [10, 20): a clipped pentagon, area = 100 - (20 - C)^2 / 2
(both derived independently; C=12 i.e. z=3 reduces to the pentagon
already used in test_plot_trace_highs.py, area 68, as a cross-check).
"""

import unittest

import scipy.sparse as sp


from cnapy import highs_lp_cache as hlc
from cnapy import plot_trace_highs as pth

REACTION_IDS = ["X", "Y", "Z"]
RXN_INDEX = {"X": 0, "Y": 1, "Z": 2}
COL_LOWER = [0.0, 0.0, 0.0]
COL_UPPER = [10.0, 10.0, 10.0]


def expected_area(z):
    C = 15.0 - z
    if C <= 0:
        return 0.0
    if C <= 10:
        return C ** 2 / 2.0
    return 100.0 - (20.0 - C) ** 2 / 2.0


def toy_lp(num_fix_slots=1):
    S = sp.lil_matrix((0, 3))
    extra_rows = [({0: 1.0, 1: 1.0, 2: 1.0}, float("-inf"), 15.0)]  # X+Y+Z <= 15
    return hlc._build_rate_lp_arrays(S, COL_LOWER, COL_UPPER, extra_rows=extra_rows,
                                     num_fix_slots=num_fix_slots)


class TestSlicePolygon(unittest.TestCase):
    def test_sequential_matches_formula(self):
        lp, fix_rows = toy_lp()
        z_values = [1.0, 3.0, 5.0, 7.0, 9.0]
        results = pth.trace_3d_slice_polygon_sequential(
            lp, REACTION_IDS, RXN_INDEX, fix_rows,
            pth.fix_rate_axis({"Z": 1.0}), {"X": 1.0}, {"Y": 1.0}, z_values)
        self.assertEqual([z for z, _ in results], z_values)  # order preserved
        for z, polygon in results:
            area = pth.polygon_area(polygon)
            self.assertAlmostEqual(area, expected_area(z), places=3, msg=f"z={z}, polygon={polygon}")

    def test_parallel_matches_formula_and_sequential(self):
        lp, fix_rows = toy_lp()
        z_values = [0.5, 2.0, 4.0, 6.0, 8.0, 9.5]
        seq = pth.trace_3d_slice_polygon_sequential(
            lp, REACTION_IDS, RXN_INDEX, fix_rows,
            pth.fix_rate_axis({"Z": 1.0}), {"X": 1.0}, {"Y": 1.0}, z_values)
        par = pth.trace_3d_slice_polygon(
            lp, REACTION_IDS, RXN_INDEX, fix_rows,
            pth.fix_rate_axis({"Z": 1.0}), {"X": 1.0}, {"Y": 1.0}, z_values, n_workers=3)
        self.assertEqual([z for z, _ in par], z_values)
        for (z_s, poly_s), (z_p, poly_p) in zip(seq, par):
            self.assertEqual(z_s, z_p)
            area_s, area_p = pth.polygon_area(poly_s), pth.polygon_area(poly_p)
            self.assertAlmostEqual(area_p, expected_area(z_p), places=3)
            self.assertAlmostEqual(area_s, area_p, places=6, msg=f"z={z_s}: seq={poly_s} par={poly_p}")

    def test_fix_yield_axis_formula(self):
        # pure arithmetic check of fix_yield_axis's (coeffs, rhs) output
        # against the merged = num - value*den formula directly, since
        # exercising it through an actual yield-ratio LP needs a 4th
        # reaction to serve as a real denominator flux -- not worth the
        # extra toy-network complexity when the formula itself is a
        # direct, easily-checked port of lptools._make_fix_constraint's
        # 'yield' branch.
        make_fix = pth.fix_yield_axis({"P": 2.0}, {"S": -3.0})
        coeffs, rhs = make_fix(0.5)
        self.assertAlmostEqual(coeffs["P"], 2.0)
        self.assertAlmostEqual(coeffs["S"], 1.5)  # 0 - 0.5*(-3.0)
        self.assertEqual(rhs, 0.0)

        coeffs0, rhs0 = make_fix(0.0)
        self.assertAlmostEqual(coeffs0["P"], 2.0)
        self.assertAlmostEqual(coeffs0.get("S", 0.0), 0.0)
        self.assertEqual(rhs0, 0.0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
