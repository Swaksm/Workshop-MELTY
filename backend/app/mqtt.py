import logging

import paho.mqtt.client as mqtt
from pydantic import ValidationError

from app.config import settings
from app.db import SessionLocal
from app.models import Measurement
from app.schemas import MeasurementIn

log = logging.getLogger(__name__)

SENSORS_TOPIC = "sentinelx/+/sensors"


def on_connect(client, userdata, flags, reason_code, properties):
    if reason_code == 0:
        client.subscribe(SENSORS_TOPIC)
    else:
        log.error("Connexion MQTT refusée : %s", reason_code)


def on_message(client, userdata, msg):
    table_id = msg.topic.split("/")[1]
    try:
        data = MeasurementIn.model_validate_json(msg.payload)
    except ValidationError:
        log.warning("Payload invalide sur %s", msg.topic)
        return
    with SessionLocal() as session:
        session.add(Measurement(table_id=table_id, **data.model_dump()))
        session.commit()


def start_mqtt() -> mqtt.Client:
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect_async(settings.mqtt_host, settings.mqtt_port)
    client.loop_start()
    return client
