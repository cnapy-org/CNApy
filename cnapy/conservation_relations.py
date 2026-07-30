"""
Detect linearly dependent rows (conservation relations / conserved moieties)
in a stoichiometric matrix via SVD, with an automatically chosen tolerance
for separating genuinely zero singular values from small-but-real ones.

Rationale
---------
Conservation relations (e.g. ATP + ADP + AMP = const) correspond to EXACT
linear dependencies among rows of S: y^T S = 0 for some nonzero y. Because
stoichiometric coefficients are integers/simple rationals, these
dependencies are algebraically exact, not approximate. Numerically this
means their singular values collapse to a tight cluster right at the
floating point noise floor (~ sigma_max * eps), clearly separated by many
orders of magnitude from any genuinely small-but-nonzero singular value
arising from ordinary (non-degenerate) network structure.

This module exploits that structural signature in three complementary ways:

1. The classical LAPACK-style eps-floor tolerance as a baseline.
2. Gap detection in the sorted log10(singular value) spectrum, requiring
   the gap to be followed by a tight, low-variance cluster (not just any
   large drop -- ordinary spectra can have big drops too).
3. A perturbation-response test: inject small, controlled noise into S at
   several scales and check whether the candidate near-zero singular
   values grow linearly with the noise scale. An exact dependency broken
   open by perturbation behaves this way; a merely small but real singular
   value generally does not.

Typical usage
-------------
    from conservation_relations import analyze_conservation_relations
    from cobra.util.array import create_stoichiometric_matrix

    S = create_stoichiometric_matrix(cobra_model, array_type="dense")
    result = analyze_conservation_relations(S)

    print(result["null_dim"], "conservation relations detected")
    Y = result["Y"]  # (n_mets, null_dim) orthonormal basis of left null space
"""

from __future__ import annotations
import numpy as np


def _padded_singular_values(sigma: np.ndarray, m: int, n: int) -> np.ndarray:
    """Pad the length-min(m,n) singular value array to length m with
    implicit zeros (relevant when m > n, i.e. more rows than columns)."""
    k = min(m, n)
    if m > k:
        return np.concatenate([sigma, np.zeros(m - k, dtype=sigma.dtype)])
    return sigma


def _find_rank_gap(
    sigma_full: np.ndarray,
    m: int,
    n: int,
    min_gap_orders: float = 3.0,
    tail_std_max: float = 1.0,
):
    """Locate a rank-revealing gap in the singular value spectrum.

    Searches for the largest drop (in orders of magnitude) between
    consecutive sorted singular values, subject to the constraint that
    everything below the drop forms a tight cluster (low std in log10
    space) -- consistent with a set of exact zeros perturbed only by
    floating point roundoff, rather than ordinary spectral decay.

    Falls back to the classical eps-based tolerance if no such gap is
    found (i.e. presumed full rank, or no detectable rank deficiency).
    """
    eps = np.finfo(sigma_full.dtype).eps
    sigma_max = sigma_full[0] if sigma_full[0] > 0 else 1.0
    eps_floor = max(m, n) * sigma_max * eps

    tiny = np.finfo(sigma_full.dtype).tiny
    log_sigma = np.log10(np.maximum(sigma_full, tiny))

    gaps = log_sigma[:-1] - log_sigma[1:]

    best_idx = None
    best_gap = 0.0
    for i in range(len(gaps)):
        tail = log_sigma[i + 1:]
        if len(tail) == 0:
            continue
        tail_std = np.std(tail) if len(tail) > 1 else 0.0
        gap = gaps[i]
        if gap >= min_gap_orders and tail_std <= tail_std_max and gap > best_gap:
            best_gap = gap
            best_idx = i

    if best_idx is not None:
        r = best_idx + 1
        # tolerance placed at the geometric mean between the last "kept"
        # and first "discarded" singular value
        lo = sigma_full[best_idx + 1]
        hi = sigma_full[best_idx]
        tol = np.sqrt(hi * lo) if lo > 0 else hi / 2.0
        method = "gap"
    else:
        r = int(np.sum(sigma_full > eps_floor))
        tol = eps_floor
        method = "eps-floor"

    return r, tol, method, eps_floor


def _perturbation_response(
    S: np.ndarray,
    r: int,
    scales,
    n_trials: int,
    rng: np.random.Generator,
):
    """Test whether the candidate near-zero singular values scale
    approximately linearly with injected perturbation size -- the
    signature of an exact structural dependency rather than a
    coincidentally small but genuine singular value."""
    m, n = S.shape
    null_dim = m - r
    if null_dim == 0:
        return {"tested": False, "reason": "no candidate null space (full rank)"}

    nz_mask = (S != 0).astype(S.dtype)
    typical_mag = np.abs(S[S != 0]).mean() if np.any(S != 0) else 1.0

    responses = {}
    for scale in scales:
        vals = []
        for _ in range(n_trials):
            noise = rng.standard_normal(S.shape) * scale * typical_mag
            S_pert = S + noise * nz_mask
            sigma_pert = np.linalg.svd(S_pert, compute_uv=False)
            sigma_pert_full = _padded_singular_values(sigma_pert, m, n)
            vals.append(np.mean(sigma_pert_full[-null_dim:]))
        responses[scale] = float(np.mean(vals))

    scales_arr = np.array(list(responses.keys()), dtype=float)
    resp_arr = np.array(list(responses.values()), dtype=float)
    ratios = resp_arr / scales_arr
    cv = float(np.std(ratios) / np.mean(ratios)) if np.mean(ratios) > 0 else np.inf
    linear = cv < 0.5  # heuristic: consistent (low-variance) ratio => linear scaling

    return {
        "tested": True,
        "responses": responses,
        "response_to_scale_ratio": dict(zip(scales_arr.tolist(), ratios.tolist())),
        "coefficient_of_variation": cv,
        "consistent_with_exact_dependency": bool(linear),
    }


def _print_report(result: dict) -> None:
    m, n = result["shape"]
    print(f"Stoichiometric matrix: {m} rows x {n} cols")
    print(f"Estimated rank:        {result['rank']}")
    print(f"Left null space dim:   {result['null_dim']}  (candidate conservation relations)")
    print(f"Tolerance method:      {result['tolerance_method']}  (tol = {result['tolerance']:.3e}, "
          f"eps-floor = {result['eps_floor']:.3e})")
    print(f"||Y^T S|| / ||S||:     {result['residual_norm']:.3e}  (should be ~1e-13 to 1e-15 if genuine)")
    pr = result["perturbation_report"]
    if pr.get("tested"):
        print("Perturbation-response test:")
        for scale, ratio in pr["response_to_scale_ratio"].items():
            print(f"    scale={scale:.1e}  ->  response/scale={ratio:.3e}")
        verdict = "PASS (consistent with exact dependency)" if pr["consistent_with_exact_dependency"] \
            else "FAIL (does not look like an exact dependency -- inspect manually)"
        print(f"    CV of ratios = {pr['coefficient_of_variation']:.3f}  ->  {verdict}")
    else:
        print(f"Perturbation-response test skipped: {pr.get('reason')}")


def analyze_conservation_relations(
    S,
    min_gap_orders: float = 3.0,
    tail_std_max: float = 1.0,
    perturbation_scales=(1e-6, 1e-8, 1e-10),
    n_perturbation_trials: int = 5,
    random_state: int = 0,
    verbose: bool = True,
) -> dict:
    """Detect conservation relations (linearly dependent rows) in a
    stoichiometric matrix S via SVD, with an automatically chosen
    tolerance for separating zero from non-zero singular values.

    Parameters
    ----------
    S : array_like, shape (n_metabolites, n_reactions)
        Stoichiometric matrix. Sparse input is densified internally
        (fine for typical genome-scale model sizes; a warning is not
        raised here -- check S.shape before calling on very large models).
    min_gap_orders : float
        Minimum size (in orders of magnitude) a drop in the singular
        value spectrum must have to be considered a candidate rank gap.
    tail_std_max : float
        Maximum allowed std-dev (in log10 space) of the singular values
        below a candidate gap, for that gap to be accepted as a genuine
        "cluster of exact zeros" rather than ordinary spectral spread.
    perturbation_scales : sequence of float
        Relative noise scales used for the perturbation-response
        validation test.
    n_perturbation_trials : int
        Number of random trials averaged per perturbation scale.
    random_state : int
        Seed for reproducibility of the perturbation test.
    verbose : bool
        Print a diagnostic report.

    Returns
    -------
    dict with keys: shape, rank, null_dim, Y (left null space basis,
    shape (n_metabolites, null_dim)), singular_values, tolerance,
    tolerance_method, eps_floor, residual_norm, perturbation_report.
    """
    S = np.asarray(S, dtype=float)
    m, n = S.shape

    U, sigma, _ = np.linalg.svd(S, full_matrices=True)
    sigma_full = _padded_singular_values(sigma, m, n)

    r, tol, method, eps_floor = _find_rank_gap(sigma_full, m, n, min_gap_orders, tail_std_max)
    null_dim = m - r
    Y = U[:, r:]

    residual = float(np.linalg.norm(Y.T @ S) / (np.linalg.norm(S) + 1e-300)) if null_dim > 0 else 0.0

    rng = np.random.default_rng(random_state)
    perturbation_report = _perturbation_response(S, r, perturbation_scales, n_perturbation_trials, rng)

    result = {
        "shape": (m, n),
        "rank": r,
        "null_dim": null_dim,
        "Y": Y,
        "singular_values": sigma_full,
        "tolerance": tol,
        "tolerance_method": method,
        "eps_floor": eps_floor,
        "residual_norm": residual,
        "perturbation_report": perturbation_report,
    }

    if verbose:
        _print_report(result)

    return result


if __name__ == "__main__":
    # Synthetic demo: 6 metabolites, 8 reactions (more columns than rows,
    # as is typical for genome-scale models -- so any rank deficiency here
    # is a genuine extra dependency, not one forced by matrix shape).
    #
    # Rows 0-4 are independent random integer vectors; row 5 is an exact
    # integer linear combination of rows 0-4 (a toy conserved moiety,
    # e.g. "row5 = 2*row0 - row1 + row2 - row3 + row4").
    rng = np.random.default_rng(0)
    basis_rows = rng.integers(-3, 4, size=(5, 8)).astype(float)
    combo = rng.integers(-2, 3, size=5).astype(float)
    dependent_row = combo @ basis_rows
    S_demo = np.vstack([basis_rows, dependent_row])

    print("=== Synthetic demo (row 5 is an exact combination of rows 0-4) ===")
    analyze_conservation_relations(S_demo)

