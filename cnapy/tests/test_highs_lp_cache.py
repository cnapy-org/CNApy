"""Correctness tests for highs_lp_cache.py, run against the real highspy package.

Toy network (steady state, S * v = 0):

    EX_A --r0--> A --r1--> B --r2--> C --r3--> EX_C
    (r0 bounds (-10, 0): negative = import of A)
    (r1, r2, r3 bounds (0, 1000))

Mass balance forces v0 = -v1 = -v2 = -v3 at every feasible point (not
just the optimum), which makes hand-verifiable reference values easy to
write down for both the rate and yield tests.

Run: pytest tests/test_highs_lp_cache.py
"""

import threading as th
import unittest

import numpy as np
import scipy.sparse as sp


from cnapy import highs_lp_cache as hlc


REACTION_IDS = ["r0", "r1", "r2", "r3"]
RXN_INDEX = {rid: i for i, rid in enumerate(REACTION_IDS)}
COL_LOWER = [-10.0, 0.0, 0.0, 0.0]
COL_UPPER = [0.0, 1000.0, 1000.0, 1000.0]


def toy_S():
    # rows: A, B, C ; cols: r0, r1, r2, r3
    S = sp.lil_matrix((3, 4))
    S[0, 0] = -1  # A: -r0
    S[0, 1] = -1  # A: -r1
    S[1, 1] = 1   # B: +r1
    S[1, 2] = -1  # B: -r2
    S[2, 2] = 1   # C: +r2
    S[2, 3] = -1  # C: -r3
    return S


class TestRateSolver(unittest.TestCase):
    def _fresh_solver(self, num_fix_slots=0):
        lp, fix_slot_rows = hlc._build_rate_lp_arrays(
            toy_S(), COL_LOWER, COL_UPPER, num_fix_slots=num_fix_slots)
        return hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_slot_rows)

    def test_max_output_matches_hand_solution(self):
        solver = self._fresh_solver()
        status, value, fluxes = solver.optimize({"r3": 1.0}, "maximize")
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(value, 10.0, places=6)
        self.assertAlmostEqual(fluxes["r0"], -10.0, places=6)
        self.assertAlmostEqual(fluxes["r3"], 10.0, places=6)

    def test_min_matches_hand_solution(self):
        solver = self._fresh_solver()
        status, value, fluxes = solver.optimize({"r3": 1.0}, "minimize")
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(value, 0.0, places=6)

    def test_fix_row_matches_manual_rebuild(self):
        # build-once + set_fix_row(rhs varying) vs. a fresh solver built
        # with the fix baked in as an ordinary constraint every time --
        # results must agree for every rhs.
        solver = self._fresh_solver(num_fix_slots=1)
        for rhs in (-1.0, -3.5, -7.0, -10.0, 0.0):
            solver.set_fix_row(0, {"r0": 1.0}, rhs)
            status, value, fluxes = solver.optimize({"r3": 1.0}, "maximize")

            lp_ref, fix_rows_ref = hlc._build_rate_lp_arrays(
                toy_S(), COL_LOWER, COL_UPPER,
                extra_rows=[({0: 1.0}, rhs, rhs)])
            ref_solver = hlc.HighsRateSolver(lp_ref, REACTION_IDS, RXN_INDEX, fix_rows_ref)
            ref_status, ref_value, ref_fluxes = ref_solver.optimize({"r3": 1.0}, "maximize")

            self.assertEqual(status, ref_status)
            self.assertAlmostEqual(value, ref_value, places=6, msg=f"mismatch at rhs={rhs}")
            self.assertAlmostEqual(value, -rhs, places=6)  # r3 == -r0 at every feasible point

    def test_fix_row_retargeted_to_different_expression(self):
        # exercise the support-diffing path in set_fix_row: point the same
        # slot at r0 first, then re-point it at r1 -- the old r0 coefficient
        # must actually get cleared (changeCoeff back to 0), not just
        # "shadowed" by an unrelated new nonzero somewhere.
        solver = self._fresh_solver(num_fix_slots=1)
        solver.set_fix_row(0, {"r0": 1.0}, -4.0)
        solver.optimize({"r3": 1.0}, "maximize")
        solver.set_fix_row(0, {"r1": 1.0}, 6.0)  # forget r0 entirely, pin r1 instead
        status, value, fluxes = solver.optimize({"r3": 1.0}, "maximize")
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(fluxes["r1"], 6.0, places=6)
        self.assertAlmostEqual(value, 6.0, places=6)
        # if the old r0==-4 coefficient had leaked, r0 would be pinned to
        # -4 too and the max would still work out to 4, not 6 -- so this
        # also indirectly checks r0 is free again:
        self.assertAlmostEqual(fluxes["r0"], -6.0, places=6)

    def test_clear_fix_row_restores_unconstrained_optimum(self):
        solver = self._fresh_solver(num_fix_slots=1)
        solver.set_fix_row(0, {"r0": 1.0}, -2.0)
        _, capped_value, _ = solver.optimize({"r3": 1.0}, "maximize")
        self.assertAlmostEqual(capped_value, 2.0, places=6)
        solver.clear_fix_row(0)
        _, free_value, _ = solver.optimize({"r3": 1.0}, "maximize")
        self.assertAlmostEqual(free_value, 10.0, places=6)


class TestYieldSolver(unittest.TestCase):
    def _fresh_solver(self, den_weight=1.0, num_fix_slots=0):
        lp, reaction_ids, rxn_index, den_row, t_col, fix_slot_rows = self._build(den_weight, num_fix_slots)
        return hlc.HighsYieldSolver(lp, reaction_ids, rxn_index, den_row, t_col, fix_slot_rows)

    def _build(self, den_weight, num_fix_slots):
        den_coeffs = {RXN_INDEX["r0"]: -den_weight}  # den = -den_weight * r0 = den_weight * (uptake)
        lp, den_row, t_col, fix_slot_rows = hlc._build_yopt_lp_arrays(
            toy_S(), COL_LOWER, COL_UPPER, den_coeffs, num_fix_slots=num_fix_slots)
        return lp, REACTION_IDS, RXN_INDEX, den_row, t_col, fix_slot_rows

    def test_constant_ratio_yield(self):
        # r3 == -r0 identically (mass balance), so yield r3 / (w * (-r0))
        # is the constant 1/w everywhere the denominator is achievable.
        for w in (1.0, 2.0, 0.5):
            solver = self._fresh_solver(den_weight=w)
            status, value, fluxes, scalable = solver.optimize({"r3": 1.0}, "maximize", denominator_sign=1.0)
            self.assertEqual(status, "optimal")
            self.assertAlmostEqual(value, 1.0 / w, places=6, msg=f"w={w}")

    def test_fix_row_in_yield_space_matches_rate_axis(self):
        solver = self._fresh_solver(den_weight=1.0, num_fix_slots=1)
        for target in (1.0, 3.0, 7.5, 10.0):
            solver.set_fix_row(0, {"r1": 1.0}, target)
            status, value, fluxes, scalable = solver.optimize(
                {"r3": 1.0}, "maximize", denominator_sign=1.0)
            self.assertEqual(status, "optimal")
            self.assertAlmostEqual(fluxes["r1"], target, places=6)
            # r1 == r3 identically, and yield value is still 1.0 (den_weight=1)
            self.assertAlmostEqual(value, 1.0, places=6)
            self.assertAlmostEqual(fluxes["r3"], target, places=6)

    def test_retargeting_fix_row_clears_t_coefficient(self):
        solver = self._fresh_solver(den_weight=1.0, num_fix_slots=1)
        solver.set_fix_row(0, {"r1": 1.0}, 4.0)
        solver.optimize({"r3": 1.0}, "maximize", denominator_sign=1.0)
        solver.clear_fix_row(0)
        status, value, fluxes, scalable = solver.optimize(
            {"r3": 1.0}, "maximize", denominator_sign=1.0)
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(value, 1.0, places=6)  # back to the unconstrained (constant) yield


    def test_yield_matches_hand_derivation_on_2d_case(self):
        # toy: X, Y in [0,10], X+Y<=12; yield = Y/(X+Y).
        # Analytically (not the toy_S chain's degenerate constant-ratio
        # case): d/dX[Y/(X+Y)] = -Y/(X+Y)^2 < 0 for Y>0, so the ratio is
        # maximized by minimizing X -> X=0 gives Y/(0+Y)=1 for any Y>0
        # (e.g. X=0,Y=10 is feasible) => max=1. Minimized by Y->0 with
        # X>0 (e.g. X=5,Y=0 is feasible, den=5>0) => ratio=0/5=0 => min=0.
        # Denominator X+Y is >=0 everywhere here (X,Y>=0), so only
        # sign=+1 is achievable.
        reaction_ids = ["X", "Y"]
        rxn_index = {"X": 0, "Y": 1}
        S = sp.lil_matrix((0, 2))
        extra_rows = [({0: 1.0, 1: 1.0}, '<=', 12.0)]  # X + Y <= 12 (yield builder's ctype-string format)
        lp, den_row, t_col, fix_rows = hlc._build_yopt_lp_arrays(
            S, [0.0, 0.0], [10.0, 10.0], den_coeffs={0: 1.0, 1: 1.0}, extra_rows=extra_rows)
        solver = hlc.HighsYieldSolver(lp, reaction_ids, rxn_index, den_row, t_col, fix_rows)

        status, value, fluxes, scalable = solver.optimize({"Y": 1.0}, "maximize", denominator_sign=1.0)
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(value, 1.0, places=6)

        status, value, fluxes, scalable = solver.optimize({"Y": 1.0}, "minimize", denominator_sign=1.0)
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(value, 0.0, places=6)


class TestThreadIsolation(unittest.TestCase):
    def test_two_threads_share_lp_without_cross_contamination(self):
        lp, fix_slot_rows = hlc._build_rate_lp_arrays(
            toy_S(), COL_LOWER, COL_UPPER, num_fix_slots=1)

        results = {}

        def worker(name, rhs_values):
            solver = hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_slot_rows)
            out = []
            for rhs in rhs_values:
                solver.set_fix_row(0, {"r0": 1.0}, rhs)
                _, value, _ = solver.optimize({"r3": 1.0}, "maximize")
                out.append((rhs, value))
            results[name] = out

        t1 = th.Thread(target=worker, args=("A", [-1.0, -4.0, -9.0]))
        t2 = th.Thread(target=worker, args=("B", [-2.0, -6.0, -10.0]))
        t1.start(); t2.start()
        t1.join(); t2.join()

        for rhs, value in results["A"]:
            self.assertAlmostEqual(value, -rhs, places=6)
        for rhs, value in results["B"]:
            self.assertAlmostEqual(value, -rhs, places=6)


def in_fresh_thread(fn):
    """fn() on a new plain thread, i.e. with a HiGHS scheduler that nothing
    has created yet; re-raises fn's exception."""
    out = {}

    def run():
        try:
            out["value"] = fn()
        except BaseException as e:
            out["error"] = e

    t = th.Thread(target=run)
    t.start()
    t.join()
    if "error" in out:
        raise out["error"]
    return out.get("value")


def default_threads_solve():
    """A HiGHS solve with default options, as cobra/optlang and cnapy.core
    run them: creates the calling thread's scheduler with the default size."""
    import highspy
    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.addVar(0.0, 1.0)
    h.changeColCost(0, -1.0)
    assert h.run() == highspy.HighsStatus.kOk


def threads_option(h):
    value = h.getOptionValue("threads")
    return value[1] if isinstance(value, tuple) else value   # (status, value) in newer highspy


class TestThreadScheduler(unittest.TestCase):
    """HiGHS has one scheduler per OS thread, sized by the first run() on
    it; a later run with a different explicit threads value fails (see
    "HiGHS thread scheduler handling" in highs_lp_cache.py)."""

    def _solver(self):
        lp, fix_slot_rows = hlc._build_rate_lp_arrays(toy_S(), COL_LOWER, COL_UPPER)
        return hlc.HighsRateSolver(lp, REACTION_IDS, RXN_INDEX, fix_slot_rows)

    def test_solver_works_after_default_threads_solve_on_same_thread(self):
        def scenario():
            default_threads_solve()
            return self._solver().optimize({"r3": 1.0}, "maximize")
        status, value, _ = in_fresh_thread(scenario)
        self.assertEqual(status, "optimal")
        self.assertAlmostEqual(value, 10.0, places=6)

    def test_threads_pinned_to_one_only_on_worker_pool_threads(self):
        self.assertEqual(threads_option(self._solver().h), 0)
        with hlc.worker_pool(2) as ex:
            in_pool = list(ex.map(lambda _: threads_option(self._solver().h), range(4)))
        self.assertEqual(in_pool, [1, 1, 1, 1])

    def test_failed_run_raises_instead_of_returning_stale_solution(self):
        import os

        def scenario():
            solver = self._solver()
            status, _, _ = solver.optimize({"r3": 1.0}, "maximize")
            self.assertEqual(status, "optimal")
            # can't match the scheduler the first run created (half the cores)
            solver.h.setOptionValue("threads", os.cpu_count() + 1)
            with self.assertRaises(RuntimeError):
                solver.optimize({"r3": 1.0}, "maximize")
        in_fresh_thread(scenario)


if __name__ == "__main__":
    unittest.main(verbosity=2)
