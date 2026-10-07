"""Rétention des données (MCO) : purge des vieilles mesures et des vieux clips vidéo.

Sans purge, la table `measurements` grossit d'environ 17 000 lignes par jour
(une mesure toutes les 5 s) et le dossier `media/` d'un clip par personne
détectée. Une tâche de fond passe toutes les heures.
"""

import logging
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Measurement

log = logging.getLogger(__name__)

INTERVALLE_S = 3600
dernier_passage: dict = {}


def purger_mesures(session: Session, maintenant: datetime, jours: int) -> int:
    limite = maintenant - timedelta(days=jours)
    resultat = session.execute(delete(Measurement).where(Measurement.received_at < limite))
    session.commit()
    return resultat.rowcount or 0


def purger_clips(dossier: Path, maintenant: datetime, jours: int, max_octets: int) -> int:
    """Supprime les clips plus vieux que `jours`, puis les plus anciens tant que le
    dossier dépasse `max_octets`. Ne touche qu'aux fichiers clip_*.mp4."""
    if not dossier.is_dir():
        return 0
    limite = (maintenant - timedelta(days=jours)).timestamp()
    clips = sorted(dossier.glob("clip_*.mp4"), key=lambda p: p.stat().st_mtime)
    supprimes = 0
    restants = []
    for clip in clips:
        if clip.stat().st_mtime < limite:
            clip.unlink(missing_ok=True)
            supprimes += 1
        else:
            restants.append(clip)
    total = sum(c.stat().st_size for c in restants)
    for clip in restants:
        if total <= max_octets:
            break
        total -= clip.stat().st_size
        clip.unlink(missing_ok=True)
        supprimes += 1
    return supprimes


def purger() -> dict:
    maintenant = datetime.now(timezone.utc)
    with SessionLocal() as session:
        mesures = purger_mesures(session, maintenant, settings.retention_mesures_jours)
    clips = purger_clips(
        Path(settings.media_dir),
        maintenant,
        settings.retention_clips_jours,
        settings.media_max_mo * 1024 * 1024,
    )
    dernier_passage.update(date=maintenant.isoformat(), mesures_supprimees=mesures, clips_supprimes=clips)
    if mesures or clips:
        log.info("Rétention : %d mesures et %d clips supprimés", mesures, clips)
    return dict(dernier_passage)


def _boucle(arret: threading.Event) -> None:
    while not arret.is_set():
        try:
            purger()
        except Exception:
            log.exception("Échec de la purge de rétention")
        arret.wait(INTERVALLE_S)


def demarrer() -> threading.Event:
    arret = threading.Event()
    threading.Thread(target=_boucle, args=(arret,), daemon=True, name="retention").start()
    return arret
