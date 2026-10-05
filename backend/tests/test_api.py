import numpy as np
from fastapi.testclient import TestClient

from app import main
from app.db import SessionLocal
from app.models import Measurement
from tests.helpers import serie_normale

client = TestClient(main.app)


def inserer(table_id: str, valeurs: np.ndarray) -> None:
    with SessionLocal() as session:
        for temp, hum, gas in valeurs:
            session.add(Measurement(table_id=table_id, temp=temp, hum=hum, gas=int(gas)))
        session.commit()


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_etat_initial():
    r = client.get("/api/v1/tables/table1/etat")
    assert r.json() == {"alerte_active": False, "modele_entraine": False}


def test_entrainement_refuse_sans_assez_de_mesures():
    inserer("table1", serie_normale(np.random.default_rng(0), 10))
    r = client.post("/api/v1/tables/table1/entrainement")
    assert r.status_code == 400


def test_entrainement_puis_etat():
    inserer("table1", serie_normale(np.random.default_rng(0), 150))
    r = client.post("/api/v1/tables/table1/entrainement")
    assert r.status_code == 200
    assert r.json() == {"mesures_utilisees": 150}
    assert client.get("/api/v1/tables/table1/etat").json()["modele_entraine"] is True


def test_mesures_filtrees_par_table():
    inserer("table1", serie_normale(np.random.default_rng(0), 3))
    inserer("table2", serie_normale(np.random.default_rng(1), 2))
    r = client.get("/api/v1/mesures", params={"table_id": "table1"})
    assert len(r.json()) == 3
    assert all(m["table_id"] == "table1" for m in r.json())


def test_commande_buzzer_transmise(monkeypatch):
    appels = []
    monkeypatch.setattr(main, "send_buzzer", lambda table, etat: appels.append((table, etat)))
    r = client.post("/api/v1/tables/table1/commande", json={"buzzer": "on"})
    assert r.status_code == 202
    assert appels == [("table1", "on")]


def test_commande_invalide_refusee():
    r = client.post("/api/v1/tables/table1/commande", json={"buzzer": "peut-etre"})
    assert r.status_code == 422
