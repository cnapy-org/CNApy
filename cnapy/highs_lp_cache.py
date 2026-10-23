"""cnapy/highs_lp_cache.py (prototype)

Build-once, incrementally-updated HiGHS LP wrappers for FVA-style repeated
optimization over a *fixed* feasible region -- plain rate objectives, and
Charnes-Cooper yield (linear-fractional) objectives -- meant to be handed
out to worker threads the same way core.multi_threaded_HiGHS_FVA already
hands out its `lp_data` HighsLp to GraphAwareFVAWorker.

No dependency on straindesign. cobra is only needed by the two
`build_*_lp(cobra_model, ...)` convenience wrappers; the array-level
builders (`_build_rate_lp_arrays` / `_build_yopt_lp_arrays`) take a
stoichiometric matrix + bound arrays directly and have no cobra
dependency at all, which is also what makes them unit-testable without a
real cobra.Model (see test_highs_lp_cache.py).

Design
------
Each HighsLp is constructed exactly once. Every worker thread then does

    solver = HighsRateSolver(lp, reaction_ids, rxn_index, fix_slot_rows)   # or HighsYieldSolver

which calls `Highs().passModel(lp)` -- HiGHS copies the model into its own
internal state at that point, so the same `lp` object can safely be
handed to multiple threads' solvers (mirrors multi_threaded_HiGHS_FVA's
`lp_data` sharing). From then on a solver only ever touches its own
Highs() instance via the incremental API:

  - optimize(obj, sense[, denominator_sign])   -> changeColCost (+ one
    changeRowBounds for the yield case) + run(). No Python-side matrix
    ever gets rebuilt.
  - set_fix_row(slot, coeffs, value)           -> used for plot_flux_space's
    "fix axis i to this value" pattern (boundary bisection, y-slicing).
    `num_fix_slots` reserved rows are placeholders (inert: free bounds /
    all-zero row) until first used. As long as a given slot keeps being
    aimed at the *same* linear expression across a trace (true for
    plot_flux_space: the axis identity is constant through one adaptive
    refinement or slice scan, only the target value changes), every call
    after the first is a single changeRowBounds (rate) or changeCoeff
    (yield, homogeneous in the LFP scaling variable t) call -- no
    Python-side sparse-matrix construction, no re-running
    create_stoichiometric_matrix.
  - clear_fix_row(slot)                        -> deactivate a slot again.

This is the piece that's missing from core.py's existing
_highs_fba_optimize / build_highs_yopt_model / highs_yopt: those rebuild
a fresh HighsLp (including create_stoichiometric_matrix and a fresh
scipy.sparse matrix) on *every* call, which is fine for FVA's one-shot
sign-check calls but would dominate wall-clock (and be entirely
GIL-bound, i.e. not helped by threading at all) if used as the inner
loop of an adaptive boundary trace that issues dozens to hundreds of
solves per axis.

NOT thread-safe to share one HighsRateSolver / HighsYieldSolver instance
across threads -- build one per worker thread from the same read-only
HighsLp, exactly like GraphAwareFVAWorker builds its own `h` from the
shared `lp_data`.
"""

import concurrent.futures as cf
import math
import threading as th
from typing import Dict, Iterable, List, Optional, Tuple

import numpy
import scipy.sparse as sp


# ---------------------------------------------------------------------------
# HiGHS thread scheduler handling
# ---------------------------------------------------------------------------
# HiGHS keeps one task scheduler per OS thread. The first run() on a thread
# creates it, sized by that run's `threads` option (default 0 = half the
# cores), and it is never resized: later runs on the same thread must use
# threads=0 or exactly that size, otherwise run() returns kError. A thread
# whose scheduler was created with threads=1 therefore also stays
# single-threaded for everything that runs there later (e.g. a MILP).
#
# So solvers built here only pin threads=1 on threads started by
# worker_pool() (fresh, so nothing else has touched their scheduler, and
# all parallelism comes from the pool). Anywhere else they keep the default
# and fit whatever scheduler the calling thread already has.

_thread_state = th.local()


def _mark_worker_thread():
    _thread_state.is_worker = True


def worker_pool(n_workers: int) -> cf.ThreadPoolExecutor:
    """ThreadPoolExecutor whose threads build their HiGHS solvers with
    threads=1 (see the comment above)."""
    return cf.ThreadPoolExecutor(max_workers=n_workers, initializer=_mark_worker_thread)


def _configure_highs(h):
    """Silent logging, and threads=1 on worker_pool threads only. Must be
    called before passModel() so that no log output is produced."""
    h.setOptionValue("output_flag", False)
    h.setOptionValue("log_to_console", False)
    if getattr(_thread_state, "is_worker", False):
        h.setOptionValue("threads", 1)


def _run_checked(h):
    """h.run(), raising on a failed run: after a kError run (e.g. a threads
    mismatch, see above) a reused instance still reports the model status
    of its previous solve, which would otherwise be read as a valid result."""
    import highspy
    status = h.run()
    if status not in (highspy.HighsStatus.kOk, highspy.HighsStatus.kWarning):
        raise RuntimeError(f"HiGHS run() failed with {status} "
                           f"(model status: {h.modelStatusToString(h.getModelStatus())})")


# ---------------------------------------------------------------------------
# Rate (plain FBA-style) model
# ---------------------------------------------------------------------------

def _build_rate_lp_arrays(S: sp.spmatrix, col_lower, col_upper,
                          extra_rows: Iterable[Tuple[Dict[int, float], float, float]] = (),
                          num_fix_slots: int = 0):
    """Array-level builder, no cobra dependency.

    Args:
        S: stoichiometric matrix, shape (n_mets, n_rxns).
        col_lower, col_upper: per-reaction bounds, length n_rxns.
        extra_rows: iterable of (coeffs_by_col_idx, row_lower, row_upper)
            for caller-supplied constraints already resolved to column
            indices (mirrors core.build_highs_fba_model's `constraints`,
            just pre-resolved so this function stays cobra-free). NOTE:
            this is (coeffs, lower, upper) -- different from
            _build_yopt_lp_arrays's extra_rows, which takes
            (coeffs, ctype_str, rhs) instead, matching the two
            functions' different callers (build_rate_lp resolves ctype
            strings itself; build_yopt_lp passes them straight through).
        num_fix_slots: number of extra placeholder rows to reserve for
            later reuse via HighsRateSolver.set_fix_row().

    Returns:
        (HighsLp, fix_slot_rows)
    """
    import highspy

    n_mets, n_rxns = S.shape
    extra_rows = list(extra_rows)
    n_extra = len(extra_rows)
    n_rows = n_mets + n_extra + num_fix_slots

    S = sp.lil_matrix(S)
    S.resize((n_rows, n_rxns))

    row_lower = numpy.zeros(n_rows, dtype=numpy.double)
    row_upper = numpy.zeros(n_rows, dtype=numpy.double)

    row = n_mets
    for coeffs, lo, hi in extra_rows:
        for col, c in coeffs.items():
            S[row, col] = c
        row_lower[row], row_upper[row] = lo, hi
        row += 1

    fix_slot_rows = list(range(row, row + num_fix_slots))
    for r in fix_slot_rows:
        row_lower[r], row_upper[r] = -math.inf, math.inf  # inert until set_fix_row()

    lp = highspy.HighsLp()
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.num_col_ = n_rxns
    lp.num_row_ = n_rows
    lp.col_cost_ = numpy.zeros(n_rxns, dtype=numpy.double)
    lp.col_lower_ = numpy.asarray(col_lower, dtype=numpy.double)
    lp.col_upper_ = numpy.asarray(col_upper, dtype=numpy.double)
    lp.row_lower_ = row_lower
    lp.row_upper_ = row_upper
    Scsr = S.tocsr()
    lp.a_matrix_.start_ = Scsr.indptr.astype(numpy.int32)
    lp.a_matrix_.index_ = Scsr.indices.astype(numpy.int32)
    lp.a_matrix_.value_ = Scsr.data.astype(numpy.double)
    lp.sense_ = highspy.ObjSense.kMinimize  # optimize() sets the real sense per call
    return lp, fix_slot_rows


def build_rate_lp(cobra_model, constraints=None, num_fix_slots: int = 0):
    """cobra.Model -> (HighsLp, reaction_ids, rxn_index, fix_slot_rows).

    `constraints`: same [dict, '<='/'='/'>=', rhs] triples
    core.build_highs_fba_model accepts.
    """
    from cobra.util.array import create_stoichiometric_matrix
    reaction_ids = cobra_model.reactions.list_attr("id")
    rxn_index = {rid: i for i, rid in enumerate(reaction_ids)}
    col_lower = [r.lower_bound for r in cobra_model.reactions]
    col_upper = [r.upper_bound for r in cobra_model.reactions]
    S = create_stoichiometric_matrix(cobra_model, array_type="lil")

    extra_rows = []
    for expr, ctype, rhs in (constraints or []):
        coeffs = {rxn_index[rid]: c for rid, c in expr.items() if rid in rxn_index}
        if ctype == '=':
            extra_rows.append((coeffs, rhs, rhs))
        elif ctype == '<=':
            extra_rows.append((coeffs, -math.inf, rhs))
        elif ctype == '>=':
            extra_rows.append((coeffs, rhs, math.inf))
        else:
            raise ValueError(f"Unknown constraint type {ctype!r}")

    lp, fix_slot_rows = _build_rate_lp_arrays(S, col_lower, col_upper, extra_rows, num_fix_slots)
    return lp, reaction_ids, rxn_index, fix_slot_rows


class HighsRateSolver:
    """One thread's private solver for a build-once rate LP."""

    def __init__(self, lp, reaction_ids: List[str], rxn_index: Dict[str, int],
                fix_slot_rows: List[int]):
        import highspy
        self._highspy = highspy
        self.reaction_ids = reaction_ids
        self.rxn_index = rxn_index
        self.fix_slot_rows = fix_slot_rows
        self.h = highspy.Highs()
        # threads=1 only on worker_pool threads, see "HiGHS thread scheduler
        # handling" at the top of this module
        _configure_highs(self.h)
        self.h.passModel(lp)
        self._active_cost_cols: set = set()
        self._fix_support: Dict[int, Dict[int, float]] = {}

    def optimize(self, obj: Dict[str, float], sense: str):
        """Set the objective to `obj` (all other columns zeroed), run,
        return (status, value, fluxes_or_None)."""
        h, hp = self.h, self._highspy
        for c in self._active_cost_cols:
            h.changeColCost(c, 0.0)
        self._active_cost_cols = set()
        for rid, coeff in obj.items():
            c = self.rxn_index[rid]
            h.changeColCost(c, coeff)
            self._active_cost_cols.add(c)
        h.changeObjectiveSense(hp.ObjSense.kMaximize if sense == 'maximize' else hp.ObjSense.kMinimize)
        _run_checked(h)
        status = h.getModelStatus()
        if status == hp.HighsModelStatus.kOptimal:
            x = numpy.asarray(h.getSolution().col_value)
            return "optimal", h.getInfo().objective_function_value, dict(zip(self.reaction_ids, x))
        elif status == hp.HighsModelStatus.kUnbounded:
            return "unbounded", (math.inf if sense == 'maximize' else -math.inf), None
        else:
            return "infeasible", float('nan'), None

    def set_fix_row(self, slot: int, coeffs: Dict[str, float], rhs: float):
        """Activate/update fix-row `slot` to `sum(coeffs[r]*v_r) = rhs`.
        Reusing the same `coeffs` across calls (only `rhs` varying, as in
        bisection refinement or a slice scan) costs one changeRowBounds
        call; only the first call for a given `coeffs` pays for the
        (small, sparse) changeCoeff calls."""
        row = self.fix_slot_rows[slot]
        new_support = {self.rxn_index[rid]: c for rid, c in coeffs.items()}
        old_support = self._fix_support.get(slot, {})
        if new_support != old_support:
            for col in old_support.keys() - new_support.keys():
                self.h.changeCoeff(row, col, 0.0)
            for col, c in new_support.items():
                if old_support.get(col) != c:
                    self.h.changeCoeff(row, col, c)
            self._fix_support[slot] = new_support
        self.h.changeRowBounds(row, rhs, rhs)

    def clear_fix_row(self, slot: int):
        self.h.changeRowBounds(self.fix_slot_rows[slot], -math.inf, math.inf)


# ---------------------------------------------------------------------------
# Yield (Charnes-Cooper LFP) model
# ---------------------------------------------------------------------------

def _build_yopt_lp_arrays(S: sp.spmatrix, col_lower, col_upper, den_coeffs: Dict[int, float],
                          extra_rows: Iterable[Tuple[Dict[int, float], str, float]] = (),
                          num_fix_slots: int = 0):
    """Charnes-Cooper LFP structure, build-once variant of
    core.build_highs_yopt_model (see that function's docstring for the
    full derivation). Variables are [v_1..v_n, t] with t the last column.

    `den_coeffs` (column index -> coefficient) is the denominator
    expression; it's baked into a dedicated row here, but that row's RHS
    (the +-1 sign) is left as a placeholder and is set per-call by
    HighsYieldSolver.optimize(), since the same structure is reused for
    both achievable signs and for many different numerators.

    `extra_rows` are caller constraints already resolved to column
    indices, as (coeffs_by_col, ctype, rhs) -- homogenized in t here so
    the caller doesn't need to know about the LFP transformation. NOTE:
    this is (coeffs, ctype_str, rhs) -- different from
    _build_rate_lp_arrays's extra_rows, which takes
    (coeffs, lower, upper) instead; see that function's docstring.

    Returns:
        (HighsLp, den_row, t_col, fix_slot_rows)
    """
    import highspy
    n_mets, n = S.shape
    lb_arr = numpy.asarray(col_lower, dtype=numpy.double)
    ub_arr = numpy.asarray(col_upper, dtype=numpy.double)
    real_lb = numpy.where(numpy.isfinite(lb_arr))[0]
    real_ub = numpy.where(numpy.isfinite(ub_arr))[0]

    extra_rows = list(extra_rows)
    n_extra = len(extra_rows)
    n_rows = n_mets + n_extra + len(real_lb) + len(real_ub) + 1 + num_fix_slots
    n_vars = n + 1
    t_col = n

    A = sp.lil_matrix((n_rows, n_vars))
    A[:n_mets, :n] = S
    row_lower = numpy.zeros(n_rows)
    row_upper = numpy.zeros(n_rows)

    row = n_mets
    for coeffs, ctype, rhs in extra_rows:
        for col, c in coeffs.items():
            A[row, col] = c
        A[row, t_col] = -float(rhs)
        if ctype == '=':
            row_lower[row] = row_upper[row] = 0.0
        elif ctype == '<=':
            row_lower[row], row_upper[row] = -math.inf, 0.0
        elif ctype == '>=':
            row_lower[row], row_upper[row] = 0.0, math.inf
        else:
            raise ValueError(f"Unknown constraint type {ctype!r}")
        row += 1

    for i in real_lb:
        A[row, i] = 1.0
        A[row, t_col] = -lb_arr[i]
        row_lower[row], row_upper[row] = 0.0, math.inf
        row += 1
    for i in real_ub:
        A[row, i] = 1.0
        A[row, t_col] = -ub_arr[i]
        row_lower[row], row_upper[row] = -math.inf, 0.0
        row += 1

    den_row = row
    for col, c in den_coeffs.items():
        A[den_row, col] = c
    row_lower[den_row] = row_upper[den_row] = 1.0  # placeholder, overwritten by optimize()
    row += 1

    fix_slot_rows = list(range(row, row + num_fix_slots))
    for r in fix_slot_rows:
        row_lower[r] = row_upper[r] = 0.0  # homogeneous eq.; all-zero row -> "0=0", inert

    col_lower_full = numpy.full(n_vars, -math.inf)
    col_upper_full = numpy.full(n_vars, math.inf)
    col_lower_full[t_col], col_upper_full[t_col] = 0.0, math.inf  # t >= 0
    # v columns stay free here -- their real bounds are enforced via the
    # real_lb/real_ub homogeneous rows above, exactly as in
    # core.build_highs_yopt_model.

    lp = highspy.HighsLp()
    lp.a_matrix_.format_ = highspy.MatrixFormat.kRowwise
    lp.num_col_ = n_vars
    lp.num_row_ = n_rows
    lp.col_cost_ = numpy.zeros(n_vars)
    lp.col_lower_ = col_lower_full
    lp.col_upper_ = col_upper_full
    lp.row_lower_ = row_lower
    lp.row_upper_ = row_upper
    Acsr = A.tocsr()
    lp.a_matrix_.start_ = Acsr.indptr.astype(numpy.int32)
    lp.a_matrix_.index_ = Acsr.indices.astype(numpy.int32)
    lp.a_matrix_.value_ = Acsr.data.astype(numpy.double)
    lp.sense_ = highspy.ObjSense.kMinimize
    return lp, den_row, t_col, fix_slot_rows


def build_yopt_lp(cobra_model, obj_den: Dict[str, float], constraints=None, num_fix_slots: int = 0):
    """cobra.Model -> (HighsLp, reaction_ids, rxn_index, den_row, t_col, fix_slot_rows)."""
    from cobra.util.array import create_stoichiometric_matrix
    reaction_ids = cobra_model.reactions.list_attr("id")
    rxn_index = {rid: i for i, rid in enumerate(reaction_ids)}
    col_lower = [r.lower_bound for r in cobra_model.reactions]
    col_upper = [r.upper_bound for r in cobra_model.reactions]
    S = create_stoichiometric_matrix(cobra_model, array_type="lil")
    den_coeffs = {rxn_index[rid]: c for rid, c in obj_den.items() if rid in rxn_index}

    extra_rows = []
    for expr, ctype, rhs in (constraints or []):
        coeffs = {rxn_index[rid]: c for rid, c in expr.items() if rid in rxn_index}
        extra_rows.append((coeffs, ctype, rhs))

    lp, den_row, t_col, fix_slot_rows = _build_yopt_lp_arrays(
        S, col_lower, col_upper, den_coeffs, extra_rows, num_fix_slots)
    return lp, reaction_ids, rxn_index, den_row, t_col, fix_slot_rows


class HighsYieldSolver:
    """One thread's private solver for a build-once Charnes-Cooper LFP."""

    def __init__(self, lp, reaction_ids: List[str], rxn_index: Dict[str, int],
                den_row: int, t_col: int, fix_slot_rows: List[int],
                denominator_tol: float = 1e-9):
        import highspy
        self._highspy = highspy
        self.reaction_ids = reaction_ids
        self.rxn_index = rxn_index
        self.den_row = den_row
        self.t_col = t_col
        self.fix_slot_rows = fix_slot_rows
        self.denominator_tol = denominator_tol
        self.h = highspy.Highs()
        _configure_highs(self.h)  # see HighsRateSolver.__init__
        self.h.passModel(lp)
        self._active_num_cols: set = set()
        self._fix_support: Dict[int, Dict[int, float]] = {}

    def optimize(self, obj_num: Dict[str, float], sense: str, denominator_sign: float):
        """(status, value, fluxes_or_None, scalable)."""
        h, hp = self.h, self._highspy
        for c in self._active_num_cols:
            h.changeColCost(c, 0.0)
        self._active_num_cols = set()
        for rid, coeff in obj_num.items():
            c = self.rxn_index[rid]
            h.changeColCost(c, denominator_sign * coeff)
            self._active_num_cols.add(c)
        h.changeRowBounds(self.den_row, denominator_sign, denominator_sign)
        h.changeObjectiveSense(hp.ObjSense.kMaximize if sense == 'maximize' else hp.ObjSense.kMinimize)
        _run_checked(h)
        status = h.getModelStatus()
        if status == hp.HighsModelStatus.kOptimal:
            x = numpy.asarray(h.getSolution().col_value)
            t = x[self.t_col]
            if t > self.denominator_tol:
                fluxes = {rid: float(x[i] / t) for i, rid in enumerate(self.reaction_ids)}
                scalable = False
            else:
                fluxes = {rid: float(x[i]) for i, rid in enumerate(self.reaction_ids)}
                scalable = True
            return "optimal", h.getInfo().objective_function_value, fluxes, scalable
        elif status == hp.HighsModelStatus.kUnbounded:
            return "unbounded", (math.inf if sense == 'maximize' else -math.inf), None, True
        else:
            return "infeasible", float('nan'), None, False

    def set_fix_row(self, slot: int, coeffs: Dict[str, float], value: float):
        """Fix a *rate-type* linear expression `coeffs` to `value`, in the
        LFP's homogeneous space: sum(coeffs[r]*x_r) - value*t = 0. Reusing
        the same `coeffs` across calls (only `value` varying) costs one
        changeCoeff call (the t-column entry)."""
        row = self.fix_slot_rows[slot]
        new_support = {self.rxn_index[rid]: c for rid, c in coeffs.items()}
        old_support = self._fix_support.get(slot, {})
        if new_support != old_support:
            for col in old_support.keys() - new_support.keys():
                self.h.changeCoeff(row, col, 0.0)
            for col, c in new_support.items():
                if old_support.get(col) != c:
                    self.h.changeCoeff(row, col, c)
            self._fix_support[slot] = new_support
        self.h.changeCoeff(row, self.t_col, -float(value))

    def clear_fix_row(self, slot: int):
        row = self.fix_slot_rows[slot]
        for col in self._fix_support.get(slot, {}):
            self.h.changeCoeff(row, col, 0.0)
        self.h.changeCoeff(row, self.t_col, 0.0)
        self._fix_support[slot] = {}


# ---------------------------------------------------------------------------
# Standalone demo / benchmark (needs real cobra + highspy; not runnable in
# this sandbox -- see test_highs_lp_cache.py for a sandbox-runnable
# correctness check against a fake highspy backed by scipy's own HiGHS).
# ---------------------------------------------------------------------------

def _toy_model():  # pragma: no cover
    import cobra
    model = cobra.Model("toy")
    a, b, c = cobra.Metabolite("A"), cobra.Metabolite("B"), cobra.Metabolite("C")
    ex_a = cobra.Reaction("EX_A"); ex_a.add_metabolites({a: 1}); ex_a.bounds = (-10, 0)
    r1 = cobra.Reaction("R1"); r1.add_metabolites({a: -1, b: 1}); r1.bounds = (0, 1000)
    r2 = cobra.Reaction("R2"); r2.add_metabolites({b: -1, c: 1}); r2.bounds = (0, 1000)
    ex_c = cobra.Reaction("EX_C"); ex_c.add_metabolites({c: -1}); ex_c.bounds = (0, 1000)
    model.add_reactions([ex_a, r1, r2, ex_c])
    return model


def _numpy_gil_sanity_check():  # pragma: no cover
    """Sanity-check that *this* interpreter/environment can show real
    threaded speedup at all, using a numpy matmul (known to release the
    GIL during the BLAS call). Subject to the exact same oversubscription
    trap as HiGHS's own `threads` default: OpenBLAS/MKL default to using
    several threads *inside* a single matmul call, so without pinning
    that down first, "N Python threads" here really means "N x (BLAS's
    own thread count)" -- confounded the same way the HiGHS numbers were.
    threadpoolctl pins it down at runtime; without it, set
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 in the
    environment *before* starting Python (numpy reads these at import
    time, so setting them after numpy is already imported won't help)."""
    import time
    import threading as th
    try:
        import threadpoolctl
        limiter = threadpoolctl.threadpool_limits(1)
    except ImportError:
        threadpoolctl = None
        limiter = None
        print("[sanity check] threadpoolctl not installed -- this reading may still be "
              "confounded by BLAS's own internal threading; `pip install threadpoolctl` "
              "for a clean one, or set OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 "
              "MKL_NUM_THREADS=1 before starting Python.")

    def run_check(pinned: bool):
        n = 700
        a = numpy.random.rand(n, n)
        b = numpy.random.rand(n, n)

        def work(k):
            for _ in range(k):
                a @ b

        reps = 12
        t0 = time.perf_counter()
        work(reps)
        t_seq = time.perf_counter() - t0

        n_threads = 4
        per = reps // n_threads
        t0 = time.perf_counter()
        threads = [th.Thread(target=work, args=(per,)) for _ in range(n_threads)]
        for t in threads: t.start()
        for t in threads: t.join()
        t_par = time.perf_counter() - t0
        pin_note = "BLAS pinned to 1 internal thread" if pinned else "BLAS NOT pinned -- reading may be confounded"
        print(f"[sanity check] numpy matmul, {n}x{n}, {pin_note}: "
              f"sequential {t_seq:.3f}s, {n_threads} threads {t_par:.3f}s "
              f"(speedup {t_seq / t_par:.2f}x -- should be well above 1x on a multi-core "
              f"machine; if it isn't, the HiGHS numbers below can't be trusted either way)")

    if limiter is not None:
        with limiter:
            run_check(pinned=True)
    else:
        run_check(pinned=False)


def _gil_release_direct_test(lp, n_run_calls: int = 4000):  # pragma: no cover
    """Directly tests whether h.run() releases the GIL, independent of
    problem size or Python/pybind11 call-overhead noise (which is what
    made the wall-clock speedup numbers hard to read once individual
    solves got down to microseconds). A background thread does a tight
    pure-Python increment loop -- CPU-bound work that needs the GIL for
    every step, and *cannot make any progress at all* while some other
    thread holds the GIL uninterrupted. Meanwhile the main thread hammers
    h.run(). If run() releases the GIL even briefly per call, the counter
    accumulates real progress during that period; if run() never releases
    it, the counter is starved almost completely, regardless of how many
    run() calls happen or how long each one takes."""
    import threading as th
    import time
    import highspy

    h = highspy.Highs()
    h.setOptionValue("output_flag", False)
    h.setOptionValue("log_to_console", False)
    h.setOptionValue("threads", 1)
    h.passModel(lp)

    def counter_loop(counter, stop):
        c = 0
        while not stop.is_set():
            c += 1
        counter[0] = c

    counter = [0]
    stop = th.Event()
    t = th.Thread(target=counter_loop, args=(counter, stop))
    t.start()
    t0 = time.perf_counter()
    for _ in range(n_run_calls):
        h.run()
    dt = time.perf_counter() - t0
    stop.set()
    t.join()
    concurrent_count = counter[0]

    # reference: same counter thread, undisturbed, for the same wall time
    counter2 = [0]
    stop2 = th.Event()
    t2 = th.Thread(target=counter_loop, args=(counter2, stop2))
    t2.start()
    time.sleep(dt)
    stop2.set()
    t2.join()
    solo_count = counter2[0]

    frac = concurrent_count / solo_count if solo_count else float("nan")
    print(f"[GIL direct test] {n_run_calls} h.run() calls took {dt:.3f}s; counter thread "
          f"reached {concurrent_count:,} running alongside them vs {solo_count:,} running "
          f"solo for the same wall time ({frac:.1%}). Near 0% => run() holds the GIL "
          f"throughout; a sizeable fraction => run() does release it.")


def _pure_run_benchmark(lp, n_calls, n_threads):  # pragma: no cover
    """Isolates h.run() itself from all the Python-side bookkeeping in
    HighsRateSolver.optimize()/set_fix_row() (dict construction, set
    diffing, etc.) -- objective/bounds are set once, then run() is called
    repeatedly with nothing changed. This is the cleanest available test
    of whether run() itself releases the GIL, independent of whatever
    overhead this prototype's wrapper adds."""
    import time
    import threading as th
    import highspy

    def make_h():
        h = highspy.Highs()
        h.setOptionValue("output_flag", False)
        h.setOptionValue("log_to_console", False)
        h.setOptionValue("threads", 1)
        h.passModel(lp)
        return h

    h = make_h()
    t0 = time.perf_counter()
    for _ in range(n_calls):
        h.run()
    t_seq = time.perf_counter() - t0
    print(f"[pure run()] sequential: {n_calls} calls in {t_seq:.3f}s "
          f"({1e6 * t_seq / n_calls:.1f}us/call)")

    def worker(k):
        hh = make_h()
        for _ in range(k):
            hh.run()

    per = n_calls // n_threads
    t0 = time.perf_counter()
    threads = [th.Thread(target=worker, args=(per,)) for _ in range(n_threads)]
    for t in threads: t.start()
    for t in threads: t.join()
    t_par = time.perf_counter() - t0
    print(f"[pure run()] {n_threads} threads x {per} calls: {t_par:.3f}s "
          f"(speedup vs sequential: {t_seq / t_par:.2f}x)")


def _demo(model=None, n_calls=2000, n_threads=4):  # pragma: no cover
    import os
    import time
    import threading as th

    if model is None:
        model = _toy_model()
    print(f"model: {len(model.reactions)} reactions, {len(model.metabolites)} "
          f"metabolites; os.cpu_count()={os.cpu_count()}")

    _numpy_gil_sanity_check()

    reaction_ids0 = model.reactions.list_attr("id")
    fix_rid, obj_rid = reaction_ids0[0], reaction_ids0[-1]

    lp, reaction_ids, rxn_index, fix_slot_rows = build_rate_lp(model, num_fix_slots=1)

    solver = HighsRateSolver(lp, reaction_ids, rxn_index, fix_slot_rows)
    t0 = time.perf_counter()
    for i in range(n_calls):
        solver.set_fix_row(0, {fix_rid: 1.0}, -float(1 + i % 9))
        solver.optimize({obj_rid: 1.0}, "maximize")
    t_reuse = time.perf_counter() - t0
    print(f"build-once + incremental updates: {n_calls} solves in {t_reuse:.3f}s")

    t0 = time.perf_counter()
    for i in range(n_calls):
        lp_i, rid_i, ridx_i, _ = build_rate_lp(
            model, constraints=[({fix_rid: 1.0}, '=', -float(1 + i % 9))])
        HighsRateSolver(lp_i, rid_i, ridx_i, []).optimize({obj_rid: 1.0}, "maximize")
    t_rebuild = time.perf_counter() - t0
    print(f"rebuild-every-call:               {n_calls} solves in {t_rebuild:.3f}s")

    def worker(n):
        s = HighsRateSolver(lp, reaction_ids, rxn_index, fix_slot_rows)
        for i in range(n):
            s.set_fix_row(0, {fix_rid: 1.0}, -float(1 + i % 9))
            s.optimize({obj_rid: 1.0}, "maximize")

    per_thread = n_calls // n_threads
    t0 = time.perf_counter()
    threads = [th.Thread(target=worker, args=(per_thread,)) for _ in range(n_threads)]
    for t in threads: t.start()
    for t in threads: t.join()
    t_threaded = time.perf_counter() - t0
    print(f"{n_threads} threads x {per_thread} solves (via optimize()): {t_threaded:.3f}s "
          f"(speedup vs single-thread reuse: {t_reuse / t_threaded:.2f}x)")

    print()
    print("Isolating h.run() from this wrapper's own Python overhead:")
    _pure_run_benchmark(lp, n_calls, n_threads)

    print()
    _gil_release_direct_test(lp)


if __name__ == "__main__":  # pragma: no cover
    import sys
    if len(sys.argv) > 1:
        import cobra
        _demo(model=cobra.io.read_sbml_model(sys.argv[1]))
    else:
        _demo()
