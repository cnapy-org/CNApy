"""
Extensions of cobra classes used in CNApy
"""
import hashlib
import pickle
import cobra


def stoichiometry_hash(model: cobra.Model):
    """md5 hash object over the reaction IDs, bounds and stoichiometries of the model.
    It is recomputed on every call and is therefore always up to date (also after changes
    made from the console). Further data can be added with update() before digest()/hexdigest()."""
    # float(c): make stable with respect to the number type of the stoichiometric coefficients (1 != 1.0)
    return hashlib.md5(pickle.dumps(tuple(
        (r.id, r.lower_bound, r.upper_bound, tuple((m.id, float(c)) for m, c in r.metabolites.items()))
        for r in model.reactions), protocol=5))


class CNApyModel(cobra.Model):
    @staticmethod
    def read_sbml_model(file_name):
        model: cobra.Model = cobra.io.read_sbml_model(file_name)
        # kludge because in COBRApy creating a model from a SBML file is not implemented as method of the Model class
        model.__class__ = CNApyModel
        return model

    def __init__(self, id_or_model=None, name=None):
        super().__init__(id_or_model=id_or_model, name=name)
        if id_or_model is None:
            self.id = ""

    @property
    def stoichiometry_hash_object(self):
        """freshly computed on every access, see stoichiometry_hash"""
        return stoichiometry_hash(self)

    # no-ops, only for compatibility with optlang_enumerator.mcs_computation which calls these
    def set_reaction_hashes(self):
        pass

    def set_stoichiometry_hash_object(self):
        pass

    def restore_stoichiometry_hash_object(self, stoichiometry_hash_object):
        pass
