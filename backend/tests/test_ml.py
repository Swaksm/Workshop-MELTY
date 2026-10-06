import numpy as np

from app import ml
from tests.helpers import serie_normale


def test_pic_de_gaz_detecte_et_normal_accepte():
    rng = np.random.default_rng(0)
    ml.train("table1", serie_normale(rng, 150))
    model = ml.get_model("table1")

    normal = serie_normale(rng, 30)
    assert not ml.is_anomaly(model, normal)

    pic = normal.copy()
    pic[-1] = [23.1, 50.2, 3500]
    assert ml.is_anomaly(model, pic)


def test_explication_donne_les_ecarts_par_caracteristique():
    rng = np.random.default_rng(2)
    base = serie_normale(rng, 150)
    ml.train("table1", base)
    model = ml.get_model("table1")

    pic = serie_normale(rng, 30)
    pic[-1] = [23.1, 50.2, 3500]
    details = ml.explication(model, pic)

    assert details["modele"] == "LOF"
    assert len(details["caracteristiques"]) == 5
    gaz = next(c for c in details["caracteristiques"] if c["nom"] == "gaz")
    assert gaz["valeur"] == 3500
    assert gaz["ecart"] > 3


def test_modele_recharge_depuis_le_disque():
    rng = np.random.default_rng(1)
    ml.train("table1", serie_normale(rng, 150))
    ml._cache.clear()

    assert ml.get_model("table1") is not None


def test_aucun_modele_sans_entrainement():
    assert ml.get_model("table_inconnue") is None
