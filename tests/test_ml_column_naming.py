import pytest

from rod_ia.domain.services.ml_column_naming import MLColumnNaming


def test_descriptive_and_target_prefixes():
    assert MLColumnNaming.descriptive("nb_chambres") == "d_nb_chambres"
    assert MLColumnNaming.target("m07_fb_alcool_montant") == "t_m07_fb_alcool_montant"


def test_no_target_leakage_in_features():
    with pytest.raises(ValueError):
        MLColumnNaming.assert_no_target_leakage(["d_nb_chambres", "t_m07_ca"])


def test_pct_column_names():
    assert MLColumnNaming.pct_month(7) == "d_pct_mois_m07"
    assert "d_pct_mois_m07_type_fb" == MLColumnNaming.pct_month_type(7, "FB")