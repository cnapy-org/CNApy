"""
(Re)generates tests/data/ecc2_fva_reference.json - the cobrapy ground-truth
FVA bounds that test_core_units.py checks multi_threaded_HiGHS_FVA against.

This is NOT run automatically by pytest. Computing full FVA on a 500-reaction
model twice per test run (once per test, unconstrained and growth-coupled)
adds real time to every CI run for a result that never changes, since the
ECC2 fixture model itself never changes - so it's computed once, here, and
committed as data.

Run this manually whenever tests/data/ECC2_model.sbml is replaced with a
different model:

    python tests/generate_fva_reference_data.py

The output JSON embeds a sha256 of the source SBML file; conftest.py's
`fva_reference` fixture checks that hash against the live fixture file on
every test run and fails loudly (rather than silently comparing against a
stale reference) if they no longer match - that's the signal this script
needs to be re-run.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import cobra

DATA_DIR = Path(__file__).parent / "data"
SBML_PATH = DATA_DIR / "ECC2_model.sbml.gz"
OUTPUT_PATH = DATA_DIR / "ecc2_fva_reference.json"


def _finite_bounds_model(model: cobra.Model) -> cobra.Model:
    """Same conversion MainWindow.fva() applies before calling
    multi_threaded_HiGHS_FVA, and that test_core_units.py's own
    _finite_bounds_model applies - kept in sync manually since this script
    intentionally has no dependency on the cnapy package (it only needs
    cobra), so it can be run even without a CNApy dev environment set up."""
    cfg = cobra.Configuration()
    m = model.copy()
    for r in m.reactions:
        if r.lower_bound == -float("inf"):
            r.lower_bound = cfg.lower_bound
        if r.upper_bound == float("inf"):
            r.upper_bound = cfg.upper_bound
    return m


def main() -> None:
    print(f"Loading {SBML_PATH} ...")
    model = _finite_bounds_model(cobra.io.read_sbml_model(str(SBML_PATH)))

    biomass_candidates = [r for r in model.reactions if r.objective_coefficient != 0]
    if len(biomass_candidates) != 1:
        sys.exit(
            f"Expected exactly one objective reaction, found "
            f"{len(biomass_candidates)}: {[r.id for r in biomass_candidates]}. "
            "Update this script if the fixture model's objective changed shape."
        )
    biomass = biomass_candidates[0]

    print("Computing unconstrained (fraction_of_optimum=0.0) reference FVA ...")
    t0 = time.time()
    unconstrained = cobra.flux_analysis.flux_variability_analysis(
        model, fraction_of_optimum=0.0, processes=1
    )
    print(f"  done in {time.time() - t0:.1f}s")

    opt = model.copy().optimize().objective_value
    print(f"Biomass reaction: {biomass.id}, optimum: {opt!r}")

    print("Computing growth-coupled (biomass fixed at optimum) reference FVA ...")
    t0 = time.time()
    growth_model = model.copy()
    growth_model.reactions.get_by_id(biomass.id).bounds = (opt, opt)
    growth_coupled = cobra.flux_analysis.flux_variability_analysis(
        growth_model, fraction_of_optimum=0.0, processes=1
    )
    print(f"  done in {time.time() - t0:.1f}s")

    sha256 = hashlib.sha256(SBML_PATH.read_bytes()).hexdigest()

    data = {
        "source_sbml_sha256": sha256,
        "biomass_reaction_id": biomass.id,
        "biomass_objective_value": opt,
        "unconstrained": {
            rid: [float(row["minimum"]), float(row["maximum"])]
            for rid, row in unconstrained.iterrows()
        },
        "growth_coupled": {
            rid: [float(row["minimum"]), float(row["maximum"])]
            for rid, row in growth_coupled.iterrows()
        },
    }
    OUTPUT_PATH.write_text(json.dumps(data, indent=0, sort_keys=True))
    print(f"Wrote {OUTPUT_PATH} ({len(data['unconstrained'])} reactions, "
          f"sha256={sha256[:12]}...)")


if __name__ == "__main__":
    main()
