import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import select

from app import main, vision
from app.db import SessionLocal
from app.models import Detection
from app.schemas import DetectionIn

client = TestClient(main.app)


def test_personne_enregistree_et_buzzer_active(monkeypatch):
    monkeypatch.setattr(vision, "BUZZER_DURATION", 60)
    appels = []
    with SessionLocal() as session:
        vision.record_person(session, "table1", DetectionIn(label="person", confidence=0.91),
                             lambda t, s: appels.append((t, s)))
        lignes = session.scalars(select(Detection)).all()

    for timer in vision._timers.values():
        timer.cancel()
    vision._timers.clear()

    assert len(lignes) == 1
    assert lignes[0].label == "person"
    assert appels == [("table1", "on")]


def test_liste_des_detections_filtree_par_table():
    with SessionLocal() as session:
        session.add(Detection(table_id="table1", label="person", confidence=0.9))
        session.add(Detection(table_id="table2", label="person", confidence=0.8))
        session.commit()

    r = client.get("/api/v1/detections", params={"table_id": "table1"})
    assert r.status_code == 200
    assert len(r.json()) == 1
    assert r.json()[0]["table_id"] == "table1"


def test_label_non_person_refuse():
    with pytest.raises(ValidationError):
        DetectionIn(label="dog", confidence=0.9)
