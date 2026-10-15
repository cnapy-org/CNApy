"""Smoke tests for plot_flux_space_highs's rendering layer: confirms it
runs without crashing (matplotlib's Agg backend, no display needed)
across every dispatch branch plot_flux_space_data_highs's own tests
cover. This does NOT verify the figures look right -- only a real look
at real output can do that -- but a rendering crash on any of these
branches would be caught here rather than only on first real use.
"""

import unittest

import cobra
import matplotlib
matplotlib.use("Agg")

import lptools_highs as lh


def make_model(reaction_bounds):
    """cobra model with reactions (id, lb, ub) and no metabolites"""
    model = cobra.Model("test")
    model.add_reactions([cobra.Reaction(rid, lower_bound=lb, upper_bound=ub) for rid, lb, ub in reaction_bounds])
    return model


class TestRenderingSmoke(unittest.TestCase):
    def _run(self, model, axes, **kwargs):
        kwargs.setdefault("show", False)
        return lh.plot_flux_space_highs(model, axes, **kwargs)

    def test_2d_point(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y"], constraints="X = 3, Y = 4")
        self.assertEqual(len(dp), 1)

    def test_2d_line(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y"], constraints="X = 3")
        self.assertEqual(len(dp), 2)

    def test_2d_full_rate_rate(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y"], constraints="X + Y <= 12")
        self.assertGreater(len(dp), 2)
        self.assertEqual(type(plot1).__name__, "Polygon")

    def test_2d_full_mixed(self):
        model = make_model([("X", 0.0, 10.0), ("P", 0.0, 10.0), ("S", 1.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", ["P", "S"]], constraints="X + P <= 12")
        self.assertGreater(len(dp), 2)

    def test_3d_point(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y", "Z"], constraints="X = 1, Y = 2, Z = 3")
        self.assertEqual(len(dp), 1)

    def test_3d_line(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y", "Z"], constraints="X = 1, Y = 2")
        self.assertEqual(len(dp), 2)

    def test_3d_plane(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y", "Z"], constraints="X + Y <= 12, Z = 3")
        self.assertEqual(type(plot1).__name__, "Poly3DCollection")

    def test_3d_full_0yield(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y", "Z"], constraints="X + Y + Z <= 25")
        self.assertEqual(len(dp), 10)
        self.assertEqual(type(plot1).__name__, "Poly3DCollection")

    def test_3d_full_1yield(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("P", 0.0, 10.0), ("S", 1.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y", ["P", "S"]],
                                      constraints="X + Y + P <= 20", points=5)
        self.assertGreater(len(dp), 0)


    def test_3d_full_2yield_grid(self):
        model = make_model([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0), ("S", 5.0, 5.0)])
        dp, triang, plot1 = self._run(model, ["X", ["Y", "S"], ["Z", "S"]],
                                      constraints="X + Y + Z <= 25", points=5)
        self.assertGreater(len(dp), 0)
        self.assertEqual(type(plot1).__name__, "Poly3DCollection")


if __name__ == "__main__":
    unittest.main(verbosity=2)
