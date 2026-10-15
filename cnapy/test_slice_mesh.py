import unittest
from collections import Counter
from lptools_highs import build_slice_mesh


def square(s, shift=0.0):
    # CCW square of half-width s, deliberately starting at a different vertex per call
    return [(-s + shift, -s), (s + shift, -s), (s + shift, s), (-s + shift, s)]


class TestSliceMesh(unittest.TestCase):
    def test_closed_manifold_for_prism(self):
        # three aligned-but-rotated squares -> closed prism-like surface
        sl = [(0.0, square(1)),
              (1.0, square(1)[2:] + square(1)[:2]),    # start vertex rotated
              (2.0, square(1) + [square(1)[0]])]        # closing duplicate
        dp, tri, outl = build_slice_mesh(sl, [0, 1], 2)
        self.assertEqual(len(outl), 3)
        edges = Counter()
        for t in tri:
            for a, b in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])):
                edges[frozenset((a, b))] += 1
        # closed surface: every edge shared by exactly two triangles
        self.assertTrue(all(c == 2 for c in edges.values()), edges)

    def test_slices_are_connected(self):
        sl = [(0.0, square(1)), (1.0, square(2))]
        dp, tri, _ = build_slice_mesh(sl, [0, 1], 2)
        # at least one triangle must span both z levels (the old fan-only bug had none)
        spans = [t for t in tri if len({dp[i][2] for i in t}) == 2]
        self.assertTrue(spans)

    def test_axis_placement(self):
        sl = [(5.0, square(1))]
        dp, _, _ = build_slice_mesh(sl, [2, 0], 1)
        self.assertTrue(all(p[1] == 5.0 for p in dp))

    def test_skips_degenerate_and_empty(self):
        self.assertEqual(build_slice_mesh([(0, []), (1, [(0, 0)])], [0, 1], 2), ([], [], []))
        dp, tri, outl = build_slice_mesh([(0, []), (1, square(1))], [0, 1], 2)
        self.assertEqual(len(outl), 1)


if __name__ == "__main__":
    unittest.main()
