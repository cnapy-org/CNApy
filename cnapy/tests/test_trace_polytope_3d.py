"""Tests trace_polytope_3d_rate / trace_polytope_3d_rate_parallel against
a hand-derivable shape: a 10x10x10 cube with one corner cut off.

    X, Y, Z in [0, 10],  X + Y + Z <= 25

The cube alone has volume 1000 and 8 corners. The plane X+Y+Z=25 slices
through the single corner (10,10,10) (since 10+10+10=30 > 25), cutting
it into a triangular face and replacing that one vertex with three new
ones along the edges leading to it:

    edge (10,10,10)-(0,10,10):  X+20=25 -> X=5  -> (5,10,10)
    edge (10,10,10)-(10,0,10):  Y+20=25 -> Y=5  -> (10,5,10)
    edge (10,10,10)-(10,10,0):  Z+20=25 -> Z=5  -> (10,10,5)

giving 10 vertices total (7 original cube corners + 3 new ones). The
cut-off piece is a right tetrahedron with three mutually perpendicular
edges of length 5 from (10,10,10), volume = 5*5*5/6 = 125/6, so the
remaining polytope's volume is 1000 - 125/6 = 5875/6 ~= 979.1667.
"""

import unittest

import numpy as np
import scipy.sparse as sp
from scipy.spatial import ConvexHull


from cnapy import highs_lp_cache as hlc
from cnapy import plot_trace_highs as pth

REACTION_IDS = ["X", "Y", "Z"]
RXN_INDEX = {"X": 0, "Y": 1, "Z": 2}
COL_LOWER = [0.0, 0.0, 0.0]
COL_UPPER = [10.0, 10.0, 10.0]

EXPECTED_VERTICES = {
    (0.0, 0.0, 0.0), (10.0, 0.0, 0.0), (0.0, 10.0, 0.0), (0.0, 0.0, 10.0),
    (10.0, 10.0, 0.0), (10.0, 0.0, 10.0), (0.0, 10.0, 10.0),
    (5.0, 10.0, 10.0), (10.0, 5.0, 10.0), (10.0, 10.0, 5.0),
}
EXPECTED_VOLUME = 1000.0 - 125.0 / 6.0


def cut_cube_lp(num_fix_slots=0):
    Smat = sp.lil_matrix((0, 3))
    extra_rows = [({0: 1.0, 1: 1.0, 2: 1.0}, float("-inf"), 25.0)]  # X+Y+Z <= 25
    return hlc._build_rate_lp_arrays(Smat, COL_LOWER, COL_UPPER, extra_rows=extra_rows,
                                     num_fix_slots=num_fix_slots)


AX0, AX1, AX2 = {"X": 1.0}, {"Y": 1.0}, {"Z": 1.0}


class TestPolytope3D(unittest.TestCase):
    def test_sequential_finds_exact_vertex_set(self):
        lp, fix_rows = cut_cube_lp()
        solver = hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_rows)
        vertices, triang, face_polys = pth.trace_polytope_3d_rate(solver, AX0, AX1, AX2)
        got = {tuple(round(c, 6) for c in v) for v in vertices}
        self.assertEqual(got, EXPECTED_VERTICES, msg=f"vertices={vertices}")

    def test_sequential_volume_matches_formula(self):
        lp, fix_rows = cut_cube_lp()
        solver = hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_rows)
        vertices, triang, face_polys = pth.trace_polytope_3d_rate(solver, AX0, AX1, AX2)
        hull = ConvexHull(np.array(vertices))
        self.assertAlmostEqual(hull.volume, EXPECTED_VOLUME, places=4)

    def test_parallel_matches_sequential(self):
        lp, fix_rows = cut_cube_lp()
        solver = hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_rows)
        seq_vertices, _, _ = pth.trace_polytope_3d_rate(solver, AX0, AX1, AX2)

        par_vertices, par_triang, par_face_polys = pth.trace_polytope_3d_rate_parallel(
            lp, REACTION_IDS, RXN_INDEX, AX0, AX1, AX2, n_workers=3)

        seq_set = {tuple(round(c, 6) for c in v) for v in seq_vertices}
        par_set = {tuple(round(c, 6) for c in v) for v in par_vertices}
        self.assertEqual(seq_set, par_set, msg=f"seq={seq_vertices}\npar={par_vertices}")

        hull_par = ConvexHull(np.array(par_vertices))
        self.assertAlmostEqual(hull_par.volume, EXPECTED_VOLUME, places=4)

    def test_triangulation_and_face_polygons_cover_all_vertices(self):
        lp, fix_rows = cut_cube_lp()
        solver = hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_rows)
        vertices, triang, face_polys = pth.trace_polytope_3d_rate(solver, AX0, AX1, AX2)

        self.assertTrue(len(triang) > 0)
        tri_vertex_ids = set(i for tri in triang for i in tri)
        self.assertEqual(tri_vertex_ids, set(range(len(vertices))))

        self.assertIsNotNone(face_polys)
        # a cut cube has 6 faces (3 full squares, 3 pentagons where the
        # corner was cut) + 1 new triangular face from the cut = 7 faces
        self.assertEqual(len(face_polys), 7, msg=f"face_polys={face_polys}")
        face_vertex_ids = set(i for face in face_polys for i in face)
        self.assertEqual(face_vertex_ids, set(range(len(vertices))))
        # every merged face should be a simple polygon with no repeats
        for face in face_polys:
            self.assertEqual(len(face), len(set(face)), msg=f"face={face}")

    def test_degenerate_too_few_vertices(self):
        # a single point: pin all three axes to force volume 0
        Smat = sp.lil_matrix((0, 3))
        extra_rows = [
            ({0: 1.0}, 3.0, 3.0), ({1: 1.0}, 3.0, 3.0), ({2: 1.0}, 3.0, 3.0),
        ]
        lp, fix_rows = hlc._build_rate_lp_arrays(Smat, COL_LOWER, COL_UPPER, extra_rows=extra_rows)
        solver = hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_rows)
        vertices, triang, face_polys = pth.trace_polytope_3d_rate(solver, AX0, AX1, AX2)
        self.assertEqual(len(vertices), 1)
        self.assertEqual(triang, [])
        self.assertIsNone(face_polys)


if __name__ == "__main__":
    unittest.main(verbosity=2)
