import unittest

import cobra

import plot_trace_highs as pth
import lptools_highs as lh


def make_model(reaction_bounds):
    """cobra model with reactions (id, lb, ub) and no metabolites"""
    model = cobra.Model("test")
    model.add_reactions([cobra.Reaction(rid, lower_bound=lb, upper_bound=ub) for rid, lb, ub in reaction_bounds])
    return model


class Test2D(unittest.TestCase):
    def test_full_rate_rate_pentagon(self):
        # X, Y in [0,10], X+Y<=12 -- same pentagon as test_plot_trace_highs.py
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0)])
        data = lh.plot_flux_space_data_highs(model, ["X", "Y"], constraints="X + Y <= 12")
        self.assertEqual(data["ax_type"], ["rate", "rate"])
        # NOT "full" -- see the note in lptools_highs._fill_2d: a fully
        # non-degenerate 2D case is labelled "plane" by _detect_degeneracy
        # (inherited from lptools.py itself), harmlessly, since neither
        # dispatch branch checks for "full" explicitly.
        self.assertEqual(data["degen"], "plane")
        self.assertEqual(data["val_limits"], [[0.0, 10.0], [0.0, 10.0]])
        area = pth.polygon_area(data["datapoints"])
        self.assertAlmostEqual(area, 68.0, places=3)

    def test_degenerate_point(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0)])
        data = lh.plot_flux_space_data_highs(model, ["X", "Y"], constraints="X = 3, Y = 4")
        self.assertEqual(data["degen"], "point")
        self.assertEqual(data["datapoints"], [[3.0, 4.0]])
        self.assertEqual(data["triang"], [])

    def test_degenerate_line(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0)])
        data = lh.plot_flux_space_data_highs(model, ["X", "Y"], constraints="X = 3")
        self.assertEqual(data["degen"], "line")
        self.assertEqual(data["degen_axes"], [True, False])
        pts = data["datapoints"]
        self.assertEqual([p[0] for p in pts], [3.0, 3.0])
        self.assertEqual(sorted(p[1] for p in pts), [0.0, 10.0])

    def test_full_mixed_rate_yield_kinked_boundary(self):
        # same setup as test_trace_boundary_adaptive.py's kinked case:
        # X,P in [0,10], S in [1,10], X+P<=12; x=X (rate), y=P/S (yield)
        model = make_model([("X", 0.0, 10.0), ("P", 0.0, 10.0), ("S", 1.0, 10.0)])
        data = lh.plot_flux_space_data_highs(
            model, ["X", ["P", "S"]], constraints="X + P <= 12")
        self.assertEqual(data["ax_type"], ["rate", "yield"])
        self.assertEqual(data["degen"], "plane")  # see note above -- expected for 2D
        self.assertTrue(data["is_approximate"])
        for x, y in data["datapoints"]:
            expected = min(10.0, 12.0 - x) if x <= 10.0 else 0.0
            # datapoints alternate upper-then-reversed-lower; only check
            # points that came from the upper boundary (y > 0 region is
            # ambiguous at the shared endpoints, so just check the
            # formula holds for every point that matches the upper curve)
            if abs(y - expected) > 1e-3 and abs(y - 0.0) > 1e-3:
                self.fail(f"point (x={x}, y={y}) matches neither upper ({expected}) nor lower (0) curve")


class Test3D(unittest.TestCase):
    def test_full_0yield_cut_cube(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0)])
        data = lh.plot_flux_space_data_highs(
            model, ["X", "Y", "Z"], constraints="X + Y + Z <= 25")
        self.assertEqual(data["ax_type"], ["rate", "rate", "rate"])
        self.assertEqual(data["degen"], "full")
        self.assertEqual(len(data["datapoints"]), 10)
        self.assertIsNotNone(data["face_polys"])
        self.assertEqual(len(data["face_polys"]), 7)
        self.assertNotIn("is_approximate", data)  # exact, unlike the yield cases

    def test_degenerate_point_3d(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0)])
        data = lh.plot_flux_space_data_highs(
            model, ["X", "Y", "Z"], constraints="X = 1, Y = 2, Z = 3")
        self.assertEqual(data["degen"], "point")
        self.assertEqual(data["datapoints"], [[1.0, 2.0, 3.0]])

    def test_degenerate_line_3d(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0)])
        data = lh.plot_flux_space_data_highs(
            model, ["X", "Y", "Z"], constraints="X = 1, Y = 2")
        self.assertEqual(data["degen"], "line")
        self.assertEqual(len(data["datapoints"]), 2)
        for p in data["datapoints"]:
            self.assertAlmostEqual(p[0], 1.0)
            self.assertAlmostEqual(p[1], 2.0)
        self.assertEqual(sorted(p[2] for p in data["datapoints"]), [0.0, 10.0])

    def test_degenerate_plane_3d_matches_2d_pentagon(self):
        # X,Y in [0,10], X+Y<=12 (the pentagon again), Z pinned to 3 ->
        # plane case should reduce to exactly the same pentagon, offset
        # into the Z=3 plane.
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0)])
        data = lh.plot_flux_space_data_highs(
            model, ["X", "Y", "Z"], constraints="X + Y <= 12, Z = 3")
        self.assertEqual(data["degen"], "plane")
        for p in data["datapoints"]:
            self.assertAlmostEqual(p[2], 3.0, places=6)
        pts_2d = [(p[0], p[1]) for p in data["datapoints"]]
        area = pth.polygon_area(pts_2d)
        self.assertAlmostEqual(area, 68.0, places=3)

    def test_full_1yield_structural(self):
        # X, Y rate; yield = P/S as the third (sliced) axis
        model = make_model([
            ("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("P", 0.0, 10.0), ("S", 1.0, 10.0),
        ])
        data = lh.plot_flux_space_data_highs(
            model, ["X", "Y", ["P", "S"]], constraints="X + Y + P <= 20", points=5)
        self.assertEqual(data["ax_type"], ["rate", "rate", "yield"])
        self.assertEqual(data["degen"], "full")
        self.assertTrue(data["is_approximate"])
        self.assertIsNotNone(data["slice_outlines"])
        self.assertGreater(len(data["slice_outlines"]), 0)
        self.assertGreater(len(data["datapoints"]), 0)
        # every datapoint's 3rd coordinate (the yield value) should fall
        # within the axis's own computed val_limits
        y_lo, y_hi = data["val_limits"][2]
        for p in data["datapoints"]:
            self.assertGreaterEqual(p[2], y_lo - 1e-6)
            self.assertLessEqual(p[2], y_hi + 1e-6)

    # --- 2+ yield axes: grid-scanning fallback -------------------------
    # Denominator S pinned to a constant (bounds [5,5]) makes Y/S, Z/S (and
    # X/S) plain linear rescalings of the already-verified cut cube
    # (X,Y,Z in [0,10], X+Y+Z<=25, exact volume 1000 - 125/6), so the
    # expected hull volume of the grid mesh is that volume divided by
    # 5 per rescaled axis.
    CUT_CUBE_VOLUME = 1000.0 - 125.0 / 6.0

    def _hull_volume(self, datapoints):
        import numpy as np
        from scipy.spatial import ConvexHull
        return ConvexHull(np.array(datapoints)).volume

    def test_two_yield_axes_grid_matches_rescaled_cut_cube(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0), ("S", 5.0, 5.0)])
        data = lh.plot_flux_space_data_highs(
            model, ["X", ["Y", "S"], ["Z", "S"]], constraints="X + Y + Z <= 25", points=9)
        self.assertEqual(data["ax_type"], ["rate", "yield", "yield"])
        self.assertTrue(data["is_approximate"])
        self.assertIsNone(data["face_polys"])
        self.assertTrue(data["triang"])
        self.assertAlmostEqual(self._hull_volume(data["datapoints"]),
                               self.CUT_CUBE_VOLUME / 25.0, places=3)
        # every triangle index must refer to a real datapoint
        self.assertLess(max(i for t in data["triang"] for i in t), len(data["datapoints"]))

    def test_three_yield_axes_grid_matches_rescaled_cut_cube(self):
        # all three axes yields over the same constant denominator: also
        # exercises axis 0 being a yield, i.e. its pin going through
        # fix_yield_axis (X - x*S = 0) rather than a plain rate pin.
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0), ("S", 5.0, 5.0)])
        data = lh.plot_flux_space_data_highs(
            model, [["X", "S"], ["Y", "S"], ["Z", "S"]], constraints="X + Y + Z <= 25", points=9)
        self.assertEqual(data["ax_type"], ["yield", "yield", "yield"])
        self.assertAlmostEqual(self._hull_volume(data["datapoints"]),
                               self.CUT_CUBE_VOLUME / 125.0, places=3)

    # --- threading: n_workers must not change the result -----------------
    def test_grid_path_threaded_matches_sequential(self):
        import numpy as np
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0), ("S", 5.0, 5.0)])
        args = (model, ["X", ["Y", "S"], ["Z", "S"]])
        kw = dict(constraints="X + Y + Z <= 25", points=7)
        ref = lh.plot_flux_space_data_highs(*args, n_workers=1, **kw)
        for w in (2, 4):
            d = lh.plot_flux_space_data_highs(*args, n_workers=w, **kw)
            self.assertEqual(d["triang"], ref["triang"])
            np.testing.assert_allclose(np.array(d["datapoints"]), np.array(ref["datapoints"]), atol=1e-9)

    def test_slice_path_threaded_matches_sequential(self):
        model = make_model([
            ("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("P", 0.0, 10.0), ("S", 1.0, 10.0),
        ])
        args = (model, ["X", "Y", ["P", "S"]])
        kw = dict(constraints="X + Y + P <= 20", points=6)
        ref = lh.plot_flux_space_data_highs(*args, n_workers=1, **kw)
        for w in (2, 4):
            d = lh.plot_flux_space_data_highs(*args, n_workers=w, **kw)
            self.assertEqual(len(d["slice_outlines"]), len(ref["slice_outlines"]))
            for a, b in zip(d["slice_outlines"], ref["slice_outlines"]):
                pa = [d["datapoints"][i] for i in a]
                pb = [ref["datapoints"][i] for i in b]
                self.assertAlmostEqual(pth.polygon_area([(p[0], p[1]) for p in pa]),
                                       pth.polygon_area([(p[0], p[1]) for p in pb]), places=9)
                self.assertAlmostEqual(pa[0][2], pb[0][2], places=12)

    def test_two_yield_axes_infeasible_slices_raise(self):
        # X + Y + Z <= -1 with all three >= 0 is infeasible, so the axis
        # limits themselves already fail -- the point is it surfaces as an
        # error rather than an empty/garbage mesh.
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0), ("S", 5.0, 5.0)])
        with self.assertRaises(Exception):
            lh.plot_flux_space_data_highs(
                model, ["X", ["Y", "S"], ["Z", "S"]], constraints="X + Y + Z <= -1", points=5)


class TestAutoNWorkers(unittest.TestCase):
    def setUp(self):
        self._available_cpus = lh._available_cpus
        lh._available_cpus = lambda: 6

    def tearDown(self):
        lh._available_cpus = self._available_cpus

    def test_slices(self):  # at most 4 workers
        self.assertEqual([lh.auto_n_workers(n, 1, max_workers=4) for n in (1, 3, 5, 20)], [1, 3, 4, 4])

    def test_grid_rows(self):  # at most the available CPUs
        self.assertEqual([lh.auto_n_workers(n, 1) for n in (0, 1, 5, 10, 30)], [1, 1, 5, 6, 6])

    def test_min_units_per_worker(self):
        self.assertEqual([lh.auto_n_workers(n, 3) for n in (2, 6, 10, 30)], [1, 2, 3, 6])

    def test_max_workers_above_cpus(self):
        self.assertEqual(lh.auto_n_workers(100, 1, max_workers=16), 6)

    def test_auto_gives_same_result_as_explicit(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0), ("S", 1.0, 1.0)])
        axes = ["X", "Y", ["Z", "S"]]
        auto = lh.plot_flux_space_data_highs(model, axes, constraints="X + Y + Z <= 15", points=7)
        single = lh.plot_flux_space_data_highs(model, axes, constraints="X + Y + Z <= 15", points=7, n_workers=1)
        self.assertEqual(auto["datapoints"], single["datapoints"])
        self.assertEqual(auto["triang"], single["triang"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
