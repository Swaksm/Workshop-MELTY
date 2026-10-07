from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main, supervision
from app.db import SessionLocal
from app.models import Measurement

client = TestClient(main.app)


def test_supervision_renvoie_hote_base_media_mqtt():
    with SessionLocal() as session:
        session.add(Measurement(table_id="table1", temp=23, hum=50, gas=1200))
        session.commit()

    r = client.get("/api/v1/supervision")
    assert r.status_code == 200
    data = r.json()
    assert 0 <= data["hote"]["cpu_pourcent"] <= 100
    assert data["hote"]["ram_totale_mo"] > 0
    assert data["base"]["mesures"] == 1
    assert data["media"]["max_mo"] > 0
    assert data["retention"]["mesures_jours"] > 0
    assert isinstance(data["mqtt"], dict)


def test_statistiques_sys_du_broker():
    supervision.mqtt_stats.clear()
    supervision.on_sys(None, None, SimpleNamespace(topic="$SYS/broker/clients/connected", payload=b"3"))
    supervision.on_sys(None, None, SimpleNamespace(topic="$SYS/broker/version", payload=b"2.0"))
    assert supervision.mqtt_stats == {"clients_connectes": "3"}
