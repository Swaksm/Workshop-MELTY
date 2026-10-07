import os
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app import retention
from app.db import SessionLocal
from app.models import Measurement

MAINTENANT = datetime(2026, 10, 7, 12, 0, tzinfo=timezone.utc)


def inserer(age_jours: float) -> None:
    with SessionLocal() as session:
        session.add(
            Measurement(
                table_id="table1", temp=23, hum=50, gas=1200,
                received_at=MAINTENANT - timedelta(days=age_jours),
            )
        )
        session.commit()


def creer_clip(dossier, nom: str, age_jours: float, taille: int = 10) -> None:
    chemin = dossier / nom
    chemin.write_bytes(b"x" * taille)
    horodatage = (MAINTENANT - timedelta(days=age_jours)).timestamp()
    os.utime(chemin, (horodatage, horodatage))


def test_purge_les_mesures_trop_anciennes():
    inserer(10)
    inserer(8)
    inserer(1)
    with SessionLocal() as session:
        assert retention.purger_mesures(session, MAINTENANT, jours=7) == 2
        restantes = session.scalars(select(Measurement)).all()
    assert len(restantes) == 1


def test_purge_les_clips_trop_anciens(tmp_path):
    creer_clip(tmp_path, "clip_table1_1.mp4", age_jours=5)
    creer_clip(tmp_path, "clip_table1_2.mp4", age_jours=1)
    creer_clip(tmp_path, "autre.txt", age_jours=30)

    assert retention.purger_clips(tmp_path, MAINTENANT, jours=3, max_octets=10**6) == 1
    assert sorted(p.name for p in tmp_path.iterdir()) == ["autre.txt", "clip_table1_2.mp4"]


def test_purge_les_plus_vieux_clips_si_le_dossier_est_trop_gros(tmp_path):
    for i in range(5):
        creer_clip(tmp_path, f"clip_table1_{i}.mp4", age_jours=1 - i * 0.1, taille=100)

    assert retention.purger_clips(tmp_path, MAINTENANT, jours=3, max_octets=250) == 3
    assert sorted(p.name for p in tmp_path.iterdir()) == ["clip_table1_3.mp4", "clip_table1_4.mp4"]


def test_dossier_media_absent(tmp_path):
    assert retention.purger_clips(tmp_path / "absent", MAINTENANT, jours=3, max_octets=0) == 0
