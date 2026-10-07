"""Supervision de la machine (MCO) : ressources de l'hôte Docker, volume de la base,
des clips vidéo et activité du broker MQTT."""

from pathlib import Path

import psutil
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app import retention
from app.config import settings
from app.models import Measurement

# Statistiques publiées par Mosquitto sur $SYS/broker/... (toutes les 10 s)
SYS_TOPICS = {
    "$SYS/broker/clients/connected": "clients_connectes",
    "$SYS/broker/messages/received": "messages_recus",
    "$SYS/broker/messages/sent": "messages_envoyes",
    "$SYS/broker/load/messages/received/1min": "messages_recus_par_min",
    "$SYS/broker/bytes/received": "octets_recus",
    "$SYS/broker/store/messages/bytes": "octets_stockes",
    "$SYS/broker/uptime": "uptime",
}
mqtt_stats: dict[str, str] = {}


def on_sys(client, userdata, msg) -> None:
    cle = SYS_TOPICS.get(msg.topic)
    if cle:
        mqtt_stats[cle] = msg.payload.decode(errors="replace")


def _hote() -> dict:
    # Dans le conteneur, psutil voit la machine qui fait tourner Docker
    # (la VM WSL2 de Docker Desktop sous Windows, la machine elle-même sous Linux).
    memoire = psutil.virtual_memory()
    disque = psutil.disk_usage("/")
    return {
        "cpu_pourcent": psutil.cpu_percent(interval=0.2),
        "cpu_coeurs": psutil.cpu_count(),
        "ram_pourcent": memoire.percent,
        "ram_utilisee_mo": round(memoire.used / 2**20),
        "ram_totale_mo": round(memoire.total / 2**20),
        "disque_pourcent": disque.percent,
    }


def _base(session: Session) -> dict:
    nb, plus_ancienne = session.execute(
        select(func.count(Measurement.id), func.min(Measurement.received_at))
    ).one()
    infos = {
        "mesures": nb,
        "plus_ancienne_mesure": plus_ancienne.isoformat() if plus_ancienne else None,
        "taille_base_mo": None,
        "taille_mesures_mo": None,
    }
    if session.bind.dialect.name == "postgresql":
        base, mesures = session.execute(
            text("SELECT pg_database_size(current_database()), pg_total_relation_size('measurements')")
        ).one()
        infos["taille_base_mo"] = round(base / 2**20, 1)
        infos["taille_mesures_mo"] = round(mesures / 2**20, 1)
    return infos


def _media() -> dict:
    dossier = Path(settings.media_dir)
    clips = list(dossier.glob("clip_*.mp4")) if dossier.is_dir() else []
    return {
        "clips": len(clips),
        "taille_mo": round(sum(c.stat().st_size for c in clips) / 2**20, 1),
        "max_mo": settings.media_max_mo,
    }


def etat(session: Session) -> dict:
    return {
        "hote": _hote(),
        "base": _base(session),
        "media": _media(),
        "mqtt": dict(mqtt_stats),
        "retention": {
            "mesures_jours": settings.retention_mesures_jours,
            "clips_jours": settings.retention_clips_jours,
            "dernier_passage": dict(retention.dernier_passage) or None,
        },
    }
