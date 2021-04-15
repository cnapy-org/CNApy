import cobra
import efmtool_link.efmtool4cobra as efmtool4cobra


def test_import():
    import cnapy


def test_efmtool4cobra_get_reversibility():
    model = cobra.Model()
    reversible, irrev_backwards_idx = efmtool4cobra.get_reversibility(model)
