"""Tests for cnapy/cobra_cnapy.py: the stoichiometry hash must follow every change of
reaction IDs, bounds and stoichiometries, also when made directly on the model."""
import cobra

from cnapy.cobra_cnapy import CNApyModel, stoichiometry_hash


def small_model() -> CNApyModel:
    model = CNApyModel("small")
    a, b = cobra.Metabolite("A"), cobra.Metabolite("B")
    r1, r2 = cobra.Reaction("R1", lower_bound=-10, upper_bound=10), cobra.Reaction("R2")
    model.add_reactions([r1, r2])
    r1.add_metabolites({a: -1, b: 1})
    r2.add_metabolites({b: -1})
    return model


def test_unchanged_model_same_hash():
    model = small_model()
    assert stoichiometry_hash(model).digest() == stoichiometry_hash(model).digest()
    assert model.stoichiometry_hash_object.hexdigest() == stoichiometry_hash(small_model()).hexdigest()


def test_changes_alter_hash():
    model = small_model()
    reference = stoichiometry_hash(model).digest()
    model.reactions.R1.upper_bound = 5
    assert stoichiometry_hash(model).digest() != reference
    model.reactions.R1.upper_bound = 10
    assert stoichiometry_hash(model).digest() == reference
    model.reactions.R2.add_metabolites({cobra.Metabolite("C"): 2})
    assert stoichiometry_hash(model).digest() != reference

    model = small_model()
    model.reactions.R2.id = "R3"
    assert stoichiometry_hash(model).digest() != reference


def test_context_undo_restores_hash():
    model = small_model()
    reference = stoichiometry_hash(model).digest()
    with model:
        model.reactions.R1.bounds = (0, 1)
        assert stoichiometry_hash(model).digest() != reference
    assert stoichiometry_hash(model).digest() == reference


def test_coefficient_number_type_does_not_matter():
    model1, model2 = small_model(), small_model()
    model2.reactions.R1.add_metabolites({model2.metabolites.A: 1.0, model2.metabolites.B: -1.0}, combine=False)
    model2.reactions.R1.add_metabolites({model2.metabolites.A: -1.0, model2.metabolites.B: 1.0}, combine=False)
    assert stoichiometry_hash(model1).digest() == stoichiometry_hash(model2).digest()


def test_copy_and_optlang_enumerator_compatibility():
    model = small_model()
    assert isinstance(model.copy(), CNApyModel)
    # these are called by optlang_enumerator.mcs_computation
    model.set_reaction_hashes()
    model.set_stoichiometry_hash_object()
    model._stoichiometry_hash_object = None
    model.restore_stoichiometry_hash_object(None)
    assert model.stoichiometry_hash_object.copy().hexdigest() == stoichiometry_hash(model).hexdigest()
