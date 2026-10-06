import json
import logging

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from app.config import settings
from app.db import SessionLocal
from app.detection import evaluate
from app.detection_temp import evaluate_hausse
from app.models import Measurement
from app.schemas import DetectionIn, MeasurementIn
from app.vision import record_person

log = logging.getLogger(__name__)

SENSORS_TOPIC = "sentinelx/+/sensors"
VISION_TOPIC = "sentinelx/+/vision"
_client: mqtt.Client | None = None


def send_buzzer(table_id: str, state: str) -> None:
    _client.publish(f"sentinelx/{table_id}/cmd", json.dumps({"buzzer": state}))


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        client.subscribe(SENSORS_TOPIC)
        client.subscribe(VISION_TOPIC)
    else:
        log.error("Connexion MQTT refusée : %s", reason_code)


def _on_sensors(table_id: str, payload: bytes) -> None:
    data = MeasurementIn.model_validate_json(payload)
    with SessionLocal() as session:
        session.add(Measurement(table_id=table_id, **data.model_dump()))
        session.commit()
        evaluate(session, table_id, send_buzzer)
        evaluate_hausse(session, table_id, send_buzzer)


def _on_vision(table_id: str, payload: bytes) -> None:
    data = DetectionIn.model_validate_json(payload)
    with SessionLocal() as session:
        record_person(session, table_id, data, send_buzzer)


def on_message(client, userdata, msg):
    _, table_id, kind = msg.topic.split("/")
    handlers = {"sensors": _on_sensors, "vision": _on_vision}
    try:
        handlers[kind](table_id, msg.payload)
    except ValidationError:
        log.warning("Payload invalide sur %s", msg.topic)


def start_mqtt() -> mqtt.Client:
    global _client
    _client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    _client.on_connect = on_connect
    _client.on_message = on_message
    if settings.mqtt_user:
        _client.username_pw_set(settings.mqtt_user, settings.mqtt_password)
    _client.connect_async(settings.mqtt_host, settings.mqtt_port)
    _client.loop_start()
    return _client
