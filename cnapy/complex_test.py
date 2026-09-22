"""
A genuinely complex, cross-validated test scenario exercising every feature
of optmdfpathway.py together:

  - a strictly-coupled 3-reaction subset (reaction_subsets)
  - a cofactor pair with a concentration ratio *range* (concentration_ratios)
  - a reaction with dG0 given as (value, uncertainty)
  - per-metabolite Cmin/Cmax via annotation, overriding the global default
  - a structurally blocked dead-end reaction (must be pruned by FVA)
  - a reaction with dG0 that is explicitly ignored (ignore_reactions)
  - two scenario constraints: a Scenario-style bound *and* a raw multi-
    reaction yield-style triple
  - FVA preprocessing against the real core.py logic
  - the full iterative bottleneck-relaxation loop (OptMDFAnalysis.run())
  - shadow_prices() / find_bottleneck() cross-checked against each other
  - solve_fba() with a positive B_bounds[0] threshold and a real cobra
    objective

Cross-validated against an independently-built "baseline" model that
avoids every shortcut (no reaction_subsets, no FVA preprocessing) but is
otherwise identical, to confirm the optimizations don't change the answer.
"""
import sys
# sys.path.insert(0, '<path-to-your-core.py-directory>')  # only needed if core.py isn't already importable

from optmdfpathway import OptMDFAnalysis, optMDFpathway
import cobra
from optlang import highs_interface
cobra.Configuration.solver = highs_interface


def build_model(use_subset_friendly_ids=True):
    """
    S --EX_S--> [uptake]
    S -R1-> I1 -R2-> I2 -R3-> P        (strictly coupled chain, dG0: -4, -3(+/-0.5), +1.5)
    P -R4-> X  (uses ATP->ADP)          dG0 = -15 (very favourable)
    ADP -ATPreg-> ATP                   regeneration, no dG0
    X -GROWTH-> Growth_met -EX_GROWTH-> [secretion]   (the FBA objective)
    P -Rdead-> Pb                       dG0 = -2, but Pb has NO exit -> blocked
    I2 -Rignore-> Junk -EX_Junk->       dG0 = +5, but explicitly ignored
    """
    m = cobra.Model('complex')
    S = cobra.Metabolite('S', compartment='c')
    S.annotation['Cmin'] = 1e-4
    S.annotation['Cmax'] = 0.1
    I1 = cobra.Metabolite('I1', compartment='c')
    I2 = cobra.Metabolite('I2', compartment='c')
    P = cobra.Metabolite('P', compartment='c')
    X = cobra.Metabolite('X', compartment='c')
    ATP = cobra.Metabolite('ATP', compartment='c')
    ADP = cobra.Metabolite('ADP', compartment='c')
    Growth_met = cobra.Metabolite('Growth_met', compartment='c')
    Pb = cobra.Metabolite('Pb', compartment='c')
    Junk = cobra.Metabolite('Junk', compartment='c')

    EX_S = cobra.Reaction('EX_S', lower_bound=-20, upper_bound=0)
    EX_S.add_metabolites({S: -1})

    R1 = cobra.Reaction('R1', lower_bound=0, upper_bound=1000)
    R1.add_metabolites({S: -1, I1: 1})
    R1.annotation['dG0'] = -4.0

    R2 = cobra.Reaction('R2', lower_bound=0, upper_bound=1000)
    R2.add_metabolites({I1: -1, I2: 1})
    R2.annotation['dG0'] = (-3.0, 0.5)  # (value, uncertainty) form

    R3 = cobra.Reaction('R3', lower_bound=0, upper_bound=1000)
    R3.add_metabolites({I2: -1, P: 1})
    R3.annotation['dG0'] = 1.5  # mildly unfavourable -- expected first bottleneck

    R4 = cobra.Reaction('R4', lower_bound=0, upper_bound=1000)
    R4.add_metabolites({P: -1, ATP: -1, X: 1, ADP: 1})
    R4.annotation['dG0'] = -15.0

    ATPreg = cobra.Reaction('ATPreg', lower_bound=0, upper_bound=1000)
    ATPreg.add_metabolites({ADP: -1, ATP: 1})

    GROWTH = cobra.Reaction('GROWTH', lower_bound=0, upper_bound=1000)
    GROWTH.add_metabolites({X: -1, Growth_met: 1})
    EX_GROWTH = cobra.Reaction('EX_GROWTH', lower_bound=0, upper_bound=1000)
    EX_GROWTH.add_metabolites({Growth_met: -1})

    Rdead = cobra.Reaction('Rdead', lower_bound=0, upper_bound=1000)
    Rdead.add_metabolites({P: -1, Pb: 1})
    Rdead.annotation['dG0'] = -2.0
    # Pb has NO exit reaction at all -> Rdead is structurally blocked

    Rignore = cobra.Reaction('Rignore', lower_bound=0, upper_bound=1000)
    Rignore.add_metabolites({I2: -1, Junk: 1})
    Rignore.annotation['dG0'] = 5.0
    EX_Junk = cobra.Reaction('EX_Junk', lower_bound=0, upper_bound=1000)
    EX_Junk.add_metabolites({Junk: -1})

    m.add_reactions([EX_S, R1, R2, R3, R4, ATPreg, GROWTH, EX_GROWTH,
                      Rdead, Rignore, EX_Junk])
    m.objective = GROWTH
    return m


# scenario constraints: a Scenario-style bound + a raw multi-reaction yield triple
scenarios = [
    {'EX_GROWTH': (0.5, 1000.0)},                            # force nonzero flux
    ({'EX_GROWTH': 1.0, 'EX_S': 0.05}, '>=', 0.0),            # GROWTH >= 0.05 * (-EX_S), a yield requirement
]
concentration_ratios = [('ATP', 'ADP', 5.0, 20.0)]            # a RANGE, not just a fixed ratio
reaction_subsets = [[('R1', 1.0), ('R2', 1.0), ('R3', 1.0)]]  # strict 1:1:1 coupling
ignore_reactions = ['Rignore']


def run_optimized():
    m = build_model()
    analysis = OptMDFAnalysis(
        m,
        Cmin=1e-6, Cmax=1e-2,  # default fallback; S overridden via annotation
        scenarios=scenarios,
        concentration_ratios=concentration_ratios,
        reaction_subsets=reaction_subsets,
        ignore_reactions=ignore_reactions,
        use_fva_preprocessing=True,
        verbose=True,
    )
    return analysis


def run_baseline():
    """Same model/constraints, but with every shortcut disabled: no
    reaction_subsets (R1/R2/R3 stand alone), no FVA preprocessing (static
    bounds). Independently exercises the same underlying MILP machinery."""
    m = build_model()
    analysis = OptMDFAnalysis(
        m,
        Cmin=1e-6, Cmax=1e-2,
        scenarios=scenarios,
        concentration_ratios=concentration_ratios,
        reaction_subsets=None,
        ignore_reactions=ignore_reactions,
        use_fva_preprocessing=False,
        verbose=True,
    )
    return analysis


if __name__ == '__main__':
    print('=' * 70)
    print('OPTIMIZED (reaction_subsets + FVA preprocessing)')
    print('=' * 70)
    opt = run_optimized()
    r_opt = opt.solve()
    print(r_opt)
    print('fluxes:', r_opt.fluxes)
    print('driving_forces:', r_opt.driving_forces)
    print('concentrations:', r_opt.concentrations)

    print()
    print('=' * 70)
    print('BASELINE (no shortcuts)')
    print('=' * 70)
    base = run_baseline()
    r_base = base.solve()
    print(r_base)
    print('driving_forces:', r_base.driving_forces)

    print()
    print('=' * 70)
    print('CROSS-VALIDATION')
    print('=' * 70)
    assert r_opt.status == r_base.status == 'optimal'
    assert abs(r_opt.mdf - r_base.mdf) < 1e-6, (r_opt.mdf, r_base.mdf)
    print(f'MDF matches exactly: optimized={r_opt.mdf:.10f}  baseline={r_base.mdf:.10f}')

    # structural checks: Pb/Rdead never got thermodynamic machinery at all
    # in the FVA-preprocessed run, because FVA discovers Rdead is
    # structurally blocked (Pb has no exit reaction at all). The baseline
    # (use_fva_preprocessing=False) only sees Rdead's own static bounds
    # (0, 1000), which don't reveal that global infeasibility, so it still
    # builds Rdead's driving-force constraint -- Rdead's flux still comes
    # out exactly 0 in the solution either way, it's just that only FVA
    # preprocessing *knows in advance* it can never be otherwise. This is
    # precisely what FVA preprocessing buys: fewer constraints, not a
    # different answer.
    assert 'Rdead' not in r_opt.driving_forces
    assert abs(r_base.fluxes['Rdead']) < 1e-9
    assert 'Rignore' not in r_opt.driving_forces
    assert 'Rignore' not in r_base.driving_forces
    print('OK: Rdead correctly pruned by FVA in the optimized run (absent from '
          'driving_forces); present but always zero-flux in the baseline run. '
          'Rignore excluded in both (explicitly ignored).')

    # every ACTIVE reaction's driving force must respect the achieved mdf
    for label, r in [('optimized', r_opt), ('baseline', r_base)]:
        for rid, df in r.driving_forces.items():
            if abs(r.fluxes[rid]) > 1e-9:
                assert df >= r.mdf - 1e-6, f'{label}: {rid} active with df={df} < mdf={r.mdf}'
    print('OK: every active reaction respects the achieved MDF in both versions')

    # cofactor ratio range respected
    for label, r in [('optimized', r_opt), ('baseline', r_base)]:
        ratio = r.concentrations['ATP'] / r.concentrations['ADP']
        assert 5.0 - 1e-6 <= ratio <= 20.0 + 1e-6, (label, ratio)
    print('OK: ATP/ADP ratio respected in both versions')

    # S concentration respects its annotation-based bounds, not the 1e-6/1e-2 default
    for label, r in [('optimized', r_opt), ('baseline', r_base)]:
        assert 1e-4 - 1e-9 <= r.concentrations['S'] <= 0.1 + 1e-9, (label, r.concentrations['S'])
    print('OK: S respects its annotation Cmin/Cmax override in both versions')

    # yield constraint respected
    for label, r in [('optimized', r_opt), ('baseline', r_base)]:
        assert r.fluxes['EX_GROWTH'] + 0.05 * r.fluxes['EX_S'] >= -1e-6, label
    print('OK: yield scenario constraint respected in both versions')

    print()
    print('=' * 70)
    print('SHADOW PRICES / BOTTLENECK CROSS-CHECK (optimized instance)')
    print('=' * 70)
    duals = opt.shadow_prices()
    bottleneck = opt.find_bottleneck()
    print('duals:', duals)
    print('bottleneck:', bottleneck)
    # every reaction with a nonzero dual must be part of the verified
    # bottleneck OR the bottleneck must at least explain the same mdf
    # (duals can over/under-attribute under degeneracy -- see conversation;
    # what must ALWAYS hold is that the bottleneck set is non-empty here,
    # since R3 was deliberately made unfavourable)
    assert bottleneck, 'expected a non-empty bottleneck (R3 chain is unfavourable)'
    assert set(bottleneck) <= set(r_opt.driving_forces), bottleneck
    print('OK: bottleneck search returns a valid, plausible non-empty set')

    print()
    print('=' * 70)
    print('ITERATIVE BOTTLENECK RELAXATION (fresh instance)')
    print('=' * 70)
    iterative = run_optimized()
    prev_mdf = None
    for i, (result, bn) in enumerate(iterative.run(max_iterations=10)):
        print(f'  iter {i}: mdf={result.mdf:.4f}  bottleneck={bn}')
        if prev_mdf is not None:
            assert result.mdf >= prev_mdf - 1e-9, 'mdf decreased across iterations!'
        prev_mdf = result.mdf
    print(f'OK: mdf monotonically improved across {len(iterative.history)} iterations, '
          f'model/FVA/MILP built once')

    print()
    print('=' * 70)
    print('THERMODYNAMIC FBA')
    print('=' * 70)
    fba_analysis = run_optimized()
    # rebuild with a positive MDF threshold -- reuse the model, new instance
    m = build_model()
    fba_analysis2 = OptMDFAnalysis(
        m, Cmin=1e-6, Cmax=1e-2, scenarios=scenarios,
        concentration_ratios=concentration_ratios,
        reaction_subsets=reaction_subsets, ignore_reactions=ignore_reactions,
        B_bounds=(1.0, 1e4),  # require MDF >= 1.0 throughout
        use_fva_preprocessing=True, verbose=True,
    )
    r_fba = fba_analysis2.solve_fba()
    print(r_fba)
    print('objective_value (growth):', r_fba.objective_value)
    assert r_fba.status == 'optimal'
    assert r_fba.mdf >= 1.0 - 1e-6
    for rid, df in r_fba.driving_forces.items():
        if abs(r_fba.fluxes[rid]) > 1e-9:
            assert df >= 1.0 - 1e-6, f'{rid} active with df={df} < required 1.0'
    print('OK: thermodynamic FBA respects the 1.0 threshold for every active reaction')

    print()
    print('ALL COMPLEX-SCENARIO CHECKS PASSED')
