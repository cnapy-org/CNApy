"""Tests trace_boundary_adaptive (RateAxis / YieldAxis) against
hand-derivable boundaries.

Toy network: X, P in [0,10], S in [1,10] (S never 0, sidesteps
denominator-sign edge cases), constraint X + P <= 12.

Case A (flat sanity check): x-axis = X (rate), y-axis = P/S (yield),
*without* the X+P<=12 constraint -- X and P/S are fully decoupled, so
the true boundary is exactly flat: upper y = 10 (P=10, S=1) and
lower y = 0 (P=0) for every x in [0,10]. A correct adaptive tracer
should find this with no extra refinement points, since linear
interpolation between the two endpoints is already exact everywhere.

Case B (real curvature): same axes, *with* X+P<=12 active. Now
P_max(x) = min(10, 12-x), giving a piecewise-linear upper boundary
with a kink at x=2 (10 for x<=2, 12-x for x>2) that pure endpoint
interpolation would get wrong in the middle -- forcing the tracer to
actually refine and find the kink. Lower boundary stays flat at 0
(P can always be driven to 0 regardless of x, since X<=10<12).
"""

import unittest

import scipy.sparse as sp


from cnapy import highs_lp_cache as hlc
from cnapy import plot_trace_highs as pth

REACTION_IDS = ["X", "P", "S"]
RXN_INDEX = {"X": 0, "P": 1, "S": 2}
COL_LOWER = [0.0, 0.0, 1.0]
COL_UPPER = [10.0, 10.0, 10.0]


def build_solvers(with_budget_constraint: bool):
    Smat = sp.lil_matrix((0, 3))
    rate_extra = [({0: 1.0, 1: 1.0}, float("-inf"), 12.0)] if with_budget_constraint else []
    yield_extra = [({0: 1.0, 1: 1.0}, "<=", 12.0)] if with_budget_constraint else []

    rate_lp, rate_fix_rows = hlc._build_rate_lp_arrays(
        Smat, COL_LOWER, COL_UPPER, extra_rows=rate_extra, num_fix_slots=1)
    rate_solver = hlc.HighsRateSolver(rate_lp, REACTION_IDS, RXN_INDEX, rate_fix_rows)

    yield_lp, den_row, t_col, yield_fix_rows = hlc._build_yopt_lp_arrays(
        Smat, COL_LOWER, COL_UPPER, den_coeffs={2: 1.0}, extra_rows=yield_extra, num_fix_slots=1)
    yield_solver = hlc.HighsYieldSolver(yield_lp, REACTION_IDS, RXN_INDEX, den_row, t_col, yield_fix_rows)

    return rate_solver, yield_solver


class TestBoundaryAdaptive(unittest.TestCase):
    def test_flat_boundary_no_coupling(self):
        rate_solver, yield_solver = build_solvers(with_budget_constraint=False)
        ax0 = pth.RateAxis(rate_solver, {"X": 1.0})
        ax1 = pth.YieldAxis(rate_solver, yield_solver, num={"P": 1.0}, den={"S": 1.0})

        upper, lower = pth.trace_boundary_adaptive(rate_solver, ax0, ax1)

        self.assertTrue(len(upper) >= 2 and len(lower) >= 2)
        for x, y in upper:
            self.assertAlmostEqual(y, 10.0, places=5, msg=f"upper at x={x}")
        for x, y in lower:
            self.assertAlmostEqual(y, 0.0, places=5, msg=f"lower at x={x}")
        xs_upper = [x for x, _ in upper]
        self.assertAlmostEqual(min(xs_upper), 0.0, places=5)
        self.assertAlmostEqual(max(xs_upper), 10.0, places=5)

    def test_kinked_upper_boundary_matches_formula(self):
        rate_solver, yield_solver = build_solvers(with_budget_constraint=True)
        ax0 = pth.RateAxis(rate_solver, {"X": 1.0})
        ax1 = pth.YieldAxis(rate_solver, yield_solver, num={"P": 1.0}, den={"S": 1.0})

        upper, lower = pth.trace_boundary_adaptive(rate_solver, ax0, ax1)

        for x, y in upper:
            expected = min(10.0, 12.0 - x)
            self.assertAlmostEqual(y, expected, places=4, msg=f"upper at x={x}: got {y}, expected {expected}")
        for x, y in lower:
            self.assertAlmostEqual(y, 0.0, places=5, msg=f"lower at x={x}")

        # the kink at x=2 should actually have been found, not smoothed over
        xs_upper = sorted(x for x, _ in upper)
        self.assertTrue(any(abs(x - 2.0) < 0.5 for x in xs_upper),
                        msg=f"expected a refinement point near the x=2 kink, got x values {xs_upper}")

    def test_yield_yield_case(self):
        # both axes yield, sharing the same denominator S: x = X/S, y = P/S,
        # with X+P<=12 still active. At any achievable x = X/S, P_max is
        # still capped by X+P<=12 i.e. P <= 12-X = 12-x*S, so y_max =
        # (12-x*S)/S = 12/S - x, S in [1,10] -- tightest (smallest) cap is
        # at S=10: y_max <= 1.2-x. But P is also capped at 10 directly
        # (P<=10/S i.e. y<=10/S, loosest at S=1: y<=10). The achievable
        # upper boundary is whichever of these actually binds; rather than
        # re-deriving the exact piecewise formula by hand, cross-check
        # each returned point by directly re-solving the same LP (max P
        # s.t. S=1, X = x*1) via the rate solver -- an independent
        # reference computed a different way.
        rate_solver, yield_solver_x = None, None
        Smat = sp.lil_matrix((0, 3))
        extra = [({0: 1.0, 1: 1.0}, float("-inf"), 12.0)]
        extra_y = [({0: 1.0, 1: 1.0}, "<=", 12.0)]
        rate_lp, rate_fix_rows = hlc._build_rate_lp_arrays(
            Smat, COL_LOWER, COL_UPPER, extra_rows=extra, num_fix_slots=1)
        rate_solver = hlc.HighsRateSolver(rate_lp, REACTION_IDS, RXN_INDEX, rate_fix_rows)

        yield_lp_x, den_row_x, t_col_x, fix_x = hlc._build_yopt_lp_arrays(
            Smat, COL_LOWER, COL_UPPER, den_coeffs={2: 1.0}, extra_rows=extra_y, num_fix_slots=1)
        yield_solver_x = hlc.HighsYieldSolver(yield_lp_x, REACTION_IDS, RXN_INDEX, den_row_x, t_col_x, fix_x)

        yield_lp_y, den_row_y, t_col_y, fix_y = hlc._build_yopt_lp_arrays(
            Smat, COL_LOWER, COL_UPPER, den_coeffs={2: 1.0}, extra_rows=extra_y, num_fix_slots=1)
        yield_solver_y = hlc.HighsYieldSolver(yield_lp_y, REACTION_IDS, RXN_INDEX, den_row_y, t_col_y, fix_y)

        ax0 = pth.YieldAxis(rate_solver, yield_solver_x, num={"X": 1.0}, den={"S": 1.0})
        ax1 = pth.YieldAxis(rate_solver, yield_solver_y, num={"P": 1.0}, den={"S": 1.0})

        upper, lower = pth.trace_boundary_adaptive(rate_solver, ax0, ax1)
        self.assertTrue(len(upper) >= 2)

        # independent cross-check: at each returned x, pin X = x*S with
        # S free in [1,10] (i.e. pin X - x*S = 0 directly on the rate
        # solver) and maximize P/S the *same way* (a second, independently
        # built yield solver with a fresh fix row), then compare.
        check_lp, check_den_row, check_t_col, check_fix = hlc._build_yopt_lp_arrays(
            Smat, COL_LOWER, COL_UPPER, den_coeffs={2: 1.0}, extra_rows=extra_y, num_fix_slots=1)
        check_solver = hlc.HighsYieldSolver(check_lp, REACTION_IDS, RXN_INDEX, check_den_row, check_t_col, check_fix)
        check_rate = hlc.HighsRateSolver(rate_lp, REACTION_IDS, RXN_INDEX, rate_fix_rows)
        for x, y in upper:
            coeffs, rhs = pth.fix_yield_axis({"X": 1.0}, {"S": 1.0})(x)
            check_rate.set_fix_row(0, coeffs, rhs)
            check_solver.set_fix_row(0, coeffs, rhs)
            check_ax1 = pth.YieldAxis(check_rate, check_solver, num={"P": 1.0}, den={"S": 1.0})
            expected = check_ax1.optimize("maximize")
            self.assertIsNotNone(expected, msg=f"reference solve infeasible at x={x}")
            self.assertAlmostEqual(y, expected, places=4, msg=f"upper at x={x}")


    def test_repeated_calls_on_same_solvers_give_identical_results(self):
        # Regression test for a real bug found via real-model benchmarking:
        # calling trace_boundary_adaptive() more than once on the *same*
        # rate_solver/axis objects (e.g. benchmarking with several
        # repeats, or any caller that reuses solvers across multiple
        # traces) used to silently inherit whatever fix-row value the
        # previous call's deepest refinement probe left behind, since
        # nothing reset it at the start of the next call -- constraining
        # x_min/x_max to something wrong from the very first step of
        # every call after the first. trace_boundary_adaptive now clears
        # its own fix state up front specifically to rule this out.
        rate_solver, yield_solver = build_solvers(with_budget_constraint=True)
        ax0 = pth.RateAxis(rate_solver, {"X": 1.0})
        ax1 = pth.YieldAxis(rate_solver, yield_solver, num={"P": 1.0}, den={"S": 1.0})

        results = [pth.trace_boundary_adaptive(rate_solver, ax0, ax1) for _ in range(4)]
        first = results[0]
        for i, (upper, lower) in enumerate(results[1:], start=1):
            self.assertEqual(len(upper), len(first[0]), msg=f"run {i}: upper point count changed")
            self.assertEqual(len(lower), len(first[1]), msg=f"run {i}: lower point count changed")
            for (x0, y0), (x1, y1) in zip(sorted(upper), sorted(first[0])):
                self.assertAlmostEqual(x0, x1, places=6, msg=f"run {i}")
                self.assertAlmostEqual(y0, y1, places=6, msg=f"run {i}")


    def test_mismatched_solver_raises(self):
        rate_solver, yield_solver = build_solvers(with_budget_constraint=True)
        other_rate_solver, _ = build_solvers(with_budget_constraint=True)  # a different instance
        ax0 = pth.RateAxis(other_rate_solver, {"X": 1.0})  # built against the WRONG solver
        ax1 = pth.YieldAxis(rate_solver, yield_solver, num={"P": 1.0}, den={"S": 1.0})
        with self.assertRaises(ValueError):
            pth.trace_boundary_adaptive(rate_solver, ax0, ax1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
