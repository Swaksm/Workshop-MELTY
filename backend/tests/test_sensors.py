import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app import mqtt
from app.db import SessionLocal
from app.models import Measurement
from app.schemas import MeasurementIn


def test_message_esp32_avec_pir_accepte():
    data = MeasurementIn.model_validate_json('{"temp":23.4,"hum":51.2,"gas":1234,"pir":1}')
    assert data.pir == 1


def test_message_sans_pir_reste_valide():
    data = MeasurementIn.model_validate_json('{"temp":23.4,"hum":51.2,"gas":1234}')
    assert data.pir is None


def test_pir_hors_limite_refuse():
    with pytest.raises(ValidationError):
        MeasurementIn.model_validate_json('{"temp":23.4,"hum":51.2,"gas":1234,"pir":2}')


def test_message_esp32_stocke_avec_le_pir(monkeypatch):
    monkeypatch.setattr(mqtt, "send_buzzer", lambda *_: None)
    mqtt._on_sensors("table1", b'{"temp":23.4,"hum":51.2,"gas":1234,"pir":1}')

    with SessionLocal() as session:
        ligne = session.scalars(select(Measurement).where(Measurement.table_id == "table1")).one()
        assert ligne.temp == 23.4
        assert ligne.pir == 1
