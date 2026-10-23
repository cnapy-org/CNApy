"""Smoke tests for plot_flux_space_highs's rendering layer: confirms it
runs without crashing (matplotlib's Agg backend, no display needed)
across every dispatch branch plot_flux_space_data_highs's own tests
cover. This does NOT verify the figures look right -- only a real look
at real output can do that -- but a rendering crash on any of these
branches would be caught here rather than only on first real use.
"""

import unittest

import cobra
import matplotlib.pyplot as plt

from cnapy import lptools_highs as lh


def FakeModel(reaction_bounds):
    """A real cobra.Model with one metabolite-free reaction per
    (id, lb, ub): no mass-balance rows, so the feasible set is exactly
    the bounds box cut by whatever `constraints` a test passes -- the
    same toy LPs the hand-derived reference shapes (pentagon, cut cube)
    are worked out for. Named after the stand-in it replaces, so the
    test bodies read unchanged."""
    model = cobra.Model("toy")
    reactions = []
    for rid, lb, ub in reaction_bounds:
        r = cobra.Reaction(rid)
        r.bounds = (lb, ub)
        reactions.append(r)
    model.add_reactions(reactions)
    return model


class TestRenderingSmoke(unittest.TestCase):
    # pyplot is switched to Agg only for this class and switched back
    # afterwards, instead of matplotlib.use("Agg") at import time, which
    # would change the backend for the whole pytest session.
    @classmethod
    def setUpClass(cls):
        import matplotlib
        cls._previous_backend = matplotlib.get_backend()
        plt.switch_backend("Agg")

    @classmethod
    def tearDownClass(cls):
        plt.close("all")
        try:
            plt.switch_backend(cls._previous_backend)
        except Exception:  # e.g. a GUI backend that can't be re-selected here
            pass

    def tearDown(self):
        plt.close("all")

    def _run(self, model, axes, **kwargs):
        kwargs.setdefault("show", False)
        return lh.plot_flux_space_highs(model, axes, **kwargs)

    def test_2d_point(self):
        model = FakeModel([("X", 0.0, 10.0), ("Y", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y"], constraints="X = 3, Y = 4")
        self.assertEqual(len(dp), 1)

    def test_2d_line(self):
        model = FakeModel([("X", 0.0, 10.0), ("Y", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y"], constraints="X = 3")
        self.assertEqual(len(dp), 2)

    def test_2d_full_rate_rate(self):
        model = FakeModel([("X", 0.0, 10.0), ("Y", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y"], constraints="X + Y <= 12")
        self.assertGreater(len(dp), 2)
        self.assertEqual(type(plot1).__name__, "Polygon")

    def test_2d_full_mixed(self):
        model = FakeModel([("X", 0.0, 10.0), ("P", 0.0, 10.0), ("S", 1.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", ["P", "S"]], constraints="X + P <= 12")
        self.assertGreater(len(dp), 2)

    def test_3d_point(self):
        model = FakeModel([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y", "Z"], constraints="X = 1, Y = 2, Z = 3")
        self.assertEqual(len(dp), 1)

    def test_3d_line(self):
        model = FakeModel([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y", "Z"], constraints="X = 1, Y = 2")
        self.assertEqual(len(dp), 2)

    def test_3d_plane(self):
        model = FakeModel([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y", "Z"], constraints="X + Y <= 12, Z = 3")
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        self.assertIsInstance(plot1, Poly3DCollection)

    def test_3d_full_0yield(self):
        model = FakeModel([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y", "Z"], constraints="X + Y + Z <= 25")
        self.assertEqual(len(dp), 10)
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        self.assertIsInstance(plot1, Poly3DCollection)

    def test_3d_full_1yield(self):
        model = FakeModel([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("P", 0.0, 10.0), ("S", 1.0, 10.0)])
        dp, triang, plot1 = self._run(model, ["X", "Y", ["P", "S"]],
                                      constraints="X + Y + P <= 20", points=5)
        self.assertGreater(len(dp), 0)


    def test_3d_full_2yield_grid(self):
        model = FakeModel([("X", 0.0, 10.0), ("Y", 0.0, 10.0), ("Z", 0.0, 10.0), ("S", 5.0, 5.0)])
        dp, triang, plot1 = self._run(model, ["X", ["Y", "S"], ["Z", "S"]],
                                      constraints="X + Y + Z <= 25", points=5)
        self.assertGreater(len(dp), 0)
        from mpl_toolkits.mplot3d.art3d import Poly3DCollection
        self.assertIsInstance(plot1, Poly3DCollection)


if __name__ == "__main__":
    unittest.main(verbosity=2)
