import numpy as np
from sqlalchemy import select

from app import detection, ml
from app.db import SessionLocal
from app.models import Alert, Measurement
from tests.helpers import serie_normale


def test_pic_cree_une_alerte_puis_le_buzzer_repasse_a_off():
    rng = np.random.default_rng(2)
    baseline = serie_normale(rng, 150)
    ml.train("table1", baseline)
    appels = []

    def buzzer(table_id: str, etat: str) -> None:
        appels.append((table_id, etat))

    with SessionLocal() as session:
        for temp, hum, gas in baseline:
            session.add(Measurement(table_id="table1", temp=temp, hum=hum, gas=int(gas)))
        session.commit()

        session.add(Measurement(table_id="table1", temp=23.1, hum=50.2, gas=3500))
        session.commit()
        detection.evaluate(session, "table1", buzzer)

        assert appels == [("table1", "on")]
        assert len(session.scalars(select(Alert)).all()) == 1
        assert detection.is_active("table1")

        for temp, hum, gas in serie_normale(rng, 30):
            session.add(Measurement(table_id="table1", temp=temp, hum=hum, gas=int(gas)))
            session.commit()
            detection.evaluate(session, "table1", buzzer)

    assert ("table1", "off") in appels
    assert not detection.is_active("table1")


def test_sans_modele_aucune_alerte():
    with SessionLocal() as session:
        session.add(Measurement(table_id="table1", temp=23.1, hum=50.2, gas=3500))
        session.commit()
        detection.evaluate(session, "table1", lambda *_: None)
        assert session.scalars(select(Alert)).all() == []
