"""Le firmware reconnaît une commande en cherchant une chaîne exacte dans le message
MQTT (ex. "buzzer":"on"). Ces tests vérifient que chaque commande acceptée par l'API
produit exactement une chaîne que le firmware sait reconnaître."""

import re
import typing
from pathlib import Path

import pytest

from app import mqtt
from app.schemas import CommandeIn

FIRMWARE = Path(__file__).resolve().parents[2] / "firmware" / "sentinel_temp" / "sentinel_temp.ino"


def chaines_reconnues() -> set[str]:
    # msg.indexOf("\"buzzer\":\"on\"") -> "buzzer":"on"
    source = FIRMWARE.read_text(encoding="utf-8")
    return {m.replace('\\"', '"') for m in re.findall(r'msg\.indexOf\("((?:\\"|[^"])*)"\)', source)}


def valeurs_api(champ: str) -> list[str]:
    annotation = CommandeIn.model_fields[champ].annotation
    litteral = next(a for a in typing.get_args(annotation) if a is not type(None))
    return list(typing.get_args(litteral))


def test_payload_compact():
    assert mqtt.payload_commande("buzzer", "on") == '{"buzzer":"on"}'


@pytest.mark.parametrize("champ", ["buzzer", "led"])
def test_chaque_commande_de_l_api_est_reconnue_par_le_firmware(champ):
    reconnues = chaines_reconnues()
    for valeur in valeurs_api(champ):
        payload = mqtt.payload_commande(champ, valeur)
        assert any(c in payload for c in reconnues if c.startswith(f'"{champ}"')), (
            f"{payload} : aucune chaîne du firmware ne correspond"
        )


def test_commandes_publiees(monkeypatch):
    publies = []

    class FauxClient:
        def publish(self, topic, payload):
            publies.append((topic, payload))

    monkeypatch.setattr(mqtt, "_client", FauxClient())
    mqtt.send_buzzer("table1", "on")
    mqtt.send_led("table1", "off")
    assert publies == [
        ("sentinelx/table1/cmd", '{"buzzer":"on"}'),
        ("sentinelx/table1/cmd", '{"led":"off"}'),
    ]
