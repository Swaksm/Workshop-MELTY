import numpy as np
from sqlalchemy import select

from app import alerts_mail, detection_temp, ml_temp
from app.db import SessionLocal
from app.models import Alert, Measurement


def test_montee_reguliere_detectee():
    rng = np.random.default_rng(3)
    serie = 22 + 0.05 * np.arange(30) + rng.normal(0, 0.1, 30)
    assert ml_temp.probabilite_hausse(serie) >= ml_temp.SEUIL


def test_temperature_stable_non_detectee():
    rng = np.random.default_rng(4)
    serie = 23 + rng.normal(0, 0.1, 30)
    assert ml_temp.probabilite_hausse(serie) < ml_temp.SEUIL


def test_descente_non_detectee():
    rng = np.random.default_rng(5)
    serie = 30 - 0.05 * np.arange(30) + rng.normal(0, 0.1, 30)
    assert ml_temp.probabilite_hausse(serie) < ml_temp.SEUIL


def test_hausse_cree_une_alerte_et_active_le_buzzer():
    rng = np.random.default_rng(6)
    valeurs = 22 + 0.05 * np.arange(30) + rng.normal(0, 0.1, 30)
    appels = []
    with SessionLocal() as session:
        for temp in valeurs:
            session.add(Measurement(table_id="table1", temp=float(temp), hum=50.0, gas=1200))
        session.commit()
        detection_temp.evaluate_hausse(session, "table1", lambda t, e: appels.append((t, e)))
        alertes = session.scalars(select(Alert)).all()

    detection_temp._active.clear()
    assert [a.kind for a in alertes] == ["hausse_temperature"]
    assert appels == [("table1", "on")]


def test_mail_hausse_contient_la_probabilite(monkeypatch):
    from app import config
    monkeypatch.setattr(config.settings, "gmail_user", "a@b.c")
    monkeypatch.setattr(config.settings, "alert_to", "a@b.c")
    msg = alerts_mail.mail_hausse("table1", 24.3, 0.92)

    texte = msg.get_body(preferencelist=("plain",)).get_content()
    assert "HAUSSE DE TEMPÉRATURE" in texte
    assert "92 %" in texte
    assert "24.3 °C" in texte
