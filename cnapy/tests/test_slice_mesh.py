"""Tests for the 1-yield slice mesh (build_slice_mesh), the generic
orientation pass (orient_closed_mesh) and back-face culled rendering."""
import math
import unittest
from collections import Counter
from cnapy.lptools_highs import build_slice_mesh, orient_closed_mesh


def square(s, shift=0.0):
    return [(-s + shift, -s), (s + shift, -s), (s + shift, s), (-s + shift, s)]


def edge_stats(tri):
    und = Counter(frozenset(p) for t in tri for p in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])))
    dirc = Counter(p for t in tri for p in ((t[0], t[1]), (t[1], t[2]), (t[2], t[0])))
    return und, sum(1 for v in dirc.values() if v > 1)


def signed_volume(dp, tri):
    v = 0.0
    for a, b, c in tri:
        A, B, C = dp[a], dp[b], dp[c]
        v += (A[0] * (B[1] * C[2] - B[2] * C[1]) - A[1] * (B[0] * C[2] - B[2] * C[0])
              + A[2] * (B[0] * C[1] - B[1] * C[0])) / 6
    return v


def assert_closed_outward(tc, dp, tri):
    und, conflicts = edge_stats(tri)
    tc.assertTrue(all(c == 2 for c in und.values()), dict(Counter(und.values())))
    tc.assertEqual(conflicts, 0)
    tc.assertGreater(signed_volume(dp, tri), 0)


def tapering_slices(n=12, sx=0.03, sy=5.0):
    """Anisotropic, shrinking-to-a-segment stack like the real
    biomass/EtOH/succ-yield case (rate axes ~100x apart in scale)."""
    out = []
    for k in range(n):
        f = 1 - k / (n - 1)
        m = 3 + (k * 5) % 6                      # varying vertex counts
        ring = [(sx * f * math.cos(2 * math.pi * j / m) + sx,
                 sy * max(f, 0.05) * math.sin(2 * math.pi * j / m) + sy) for j in range(m)]
        if k == n - 1:
            ring = [(sx, sy), (sx, sy)]           # collapsed duplicate tip
        out.append((k * 0.1, ring))
    return out


class TestSliceMesh(unittest.TestCase):
    def test_closed_outward_prism(self):
        sl = [(0.0, square(1)),
              (1.0, square(1)[2:] + square(1)[:2]),
              (2.0, square(1) + [square(1)[0]])]
        dp, tri, outl = build_slice_mesh(sl, [0, 1], 2)
        self.assertEqual(len(outl), 3)
        assert_closed_outward(self, dp, tri)
        self.assertAlmostEqual(signed_volume(dp, tri), 8.0, places=9)

    def test_cw_input_rings_still_outward(self):
        sl = [(0.0, square(1)[::-1]), (1.0, square(2)[::-1])]
        dp, tri, _ = build_slice_mesh(sl, [0, 1], 2)
        assert_closed_outward(self, dp, tri)

    def test_anisotropic_taper_no_fold(self):
        # regression: the greedy shortest-diagonal walker folded here
        dp, tri, outl = build_slice_mesh(tapering_slices(), [0, 1], 2)
        assert_closed_outward(self, dp, tri)
        self.assertEqual(len(outl[-1]), 1)       # duplicate tip collapsed

    def test_all_axis_orders_outward(self):
        for ri, yi in (([0, 1], 2), ([1, 2], 0), ([0, 2], 1), ([2, 0], 1), ([1, 0], 2)):
            dp, tri, _ = build_slice_mesh(tapering_slices(), ri, yi)
            with self.subTest(rate_indices=ri, yield_idx=yi):
                assert_closed_outward(self, dp, tri)

    def test_slices_are_connected(self):
        dp, tri, _ = build_slice_mesh([(0.0, square(1)), (1.0, square(2))], [0, 1], 2)
        self.assertTrue([t for t in tri if len({dp[i][2] for i in t}) == 2])

    def test_unsorted_slices(self):
        dp, tri, _ = build_slice_mesh([(1.0, square(2)), (0.0, square(1))], [0, 1], 2)
        assert_closed_outward(self, dp, tri)

    def test_skips_empty(self):
        self.assertEqual(build_slice_mesh([(0, [])], [0, 1], 2), ([], [], []))
        dp, tri, outl = build_slice_mesh([(0, []), (1, square(1))], [0, 1], 2)
        self.assertEqual(len(outl), 1)


class TestOrientClosedMesh(unittest.TestCase):
    CUBE = [[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)]
    QUADS = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]

    def cube_tris(self):
        return [t for a, b, c, d in self.QUADS for t in ([a, b, c], [a, c, d])]

    def test_scrambled_cube_fixed(self):
        tri = [t if k % 3 else [t[0], t[2], t[1]] for k, t in enumerate(self.cube_tris())]
        out, closed = orient_closed_mesh(self.CUBE, tri)
        self.assertTrue(closed)
        assert_closed_outward(self, self.CUBE, out)

    def test_inward_cube_flipped(self):
        tri = [[t[0], t[2], t[1]] for t in self.cube_tris()]
        out, closed = orient_closed_mesh(self.CUBE, tri)
        self.assertTrue(closed)
        self.assertGreater(signed_volume(self.CUBE, out), 0)

    def test_open_mesh_untouched(self):
        tri = self.cube_tris()[:-2]
        out, closed = orient_closed_mesh(self.CUBE, tri)
        self.assertFalse(closed)
        self.assertEqual(out, tri)


class TestCulledRender(unittest.TestCase):
    def test_culling_hides_back_faces(self):
        # Rendered on an explicit Agg canvas rather than via
        # matplotlib.use("Agg"), so this doesn't switch the global backend
        # for the rest of the pytest session (Qt tests share it).
        try:
            import numpy as np
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_agg import FigureCanvasAgg
        except ImportError:
            self.skipTest("matplotlib not available")
        from cnapy import lptools_highs as L
        L._ensure_plotting()
        cube = TestOrientClosedMesh.CUBE
        tri, _ = orient_closed_mesh(cube, TestOrientClosedMesh().cube_tris())

        # one distinct colour per cube face, keyed by its outward normal
        face_colours = {(0, 0, -1): (1, 0, 0), (0, 0, 1): (0, 1, 0), (0, -1, 0): (0, 0, 1),
                        (0, 1, 0): (1, 1, 0), (-1, 0, 0): (1, 0, 1), (1, 0, 0): (0, 1, 1)}
        normals = []
        for t in tri:
            a, b, c = (np.array(cube[i], float) for i in t)
            n = np.cross(b - a, c - a)
            normals.append(tuple(int(v) for v in np.sign(n)))
        colours = [list(face_colours[n]) + [1.0] for n in normals]

        fig = Figure(figsize=(3, 3), dpi=100)
        FigureCanvasAgg(fig)
        ax = fig.add_subplot(projection="3d")
        ax.set_axis_off()
        coll = L.CulledTriCollection([[cube[i] for i in t] for t in tri], colours, linewidths=0)
        ax.add_collection3d(coll)
        ax.view_init(30, 45)   # camera on the +x, +y, +z side
        fig.canvas.draw()
        # 3 faces = 6 triangles; 12 would mean culling silently fell back to
        # drawing everything (e.g. a matplotlib upgrade changed the mplot3d
        # internals it hooks)
        self.assertEqual(len(coll.get_paths()), 6)

        # ...and they must be the right 3: front faces present in the
        # image, back faces absent (catches a flipped front/back test,
        # which would also leave exactly 6 triangles)
        img = np.asarray(fig.canvas.buffer_rgba())[:, :, :3].astype(int)

        def pixels(rgb):
            return int((np.abs(img - np.array(rgb) * 255).max(axis=2) <= 3).sum())
        for normal, rgb in face_colours.items():
            front = sum(normal) > 0
            with self.subTest(face=normal, front=front):
                if front:
                    self.assertGreater(pixels(rgb), 200)
                else:
                    self.assertEqual(pixels(rgb), 0)

if __name__ == "__main__":
    unittest.main()
