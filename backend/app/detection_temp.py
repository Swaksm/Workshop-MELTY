from collections.abc import Callable

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ml_temp
from app.detection import _mesures_recentes
from app.evolution_chart import graphique_evolution
from app.models import Alert, Measurement
from app.notifier import notifier

KIND = "hausse_temperature"
SEUIL_FIN = 0.5
_active: set[str] = set()


def evaluate_hausse(session: Session, table_id: str, set_buzzer: Callable[[str, str], None]) -> None:
    rows = list(
        reversed(
            session.scalars(
                select(Measurement)
                .where(Measurement.table_id == table_id)
                .order_by(Measurement.id.desc())
                .limit(ml_temp.WINDOW)
            ).all()
        )
    )
    if len(rows) < ml_temp.WINDOW:
        return

    serie = np.array([r.temp for r in rows], dtype=float)
    probabilite = ml_temp.probabilite_hausse(serie)
    last = rows[-1]

    if probabilite >= ml_temp.SEUIL and table_id not in _active:
        _active.add(table_id)
        details = ml_temp.explication(serie)
        session.add(
            Alert(
                table_id=table_id,
                temp=last.temp,
                hum=last.hum,
                gas=last.gas,
                kind=KIND,
                details=details,
            )
        )
        session.commit()
        set_buzzer(table_id, "on")
        graphique = graphique_evolution(_mesures_recentes(session, table_id, last.received_at), last.received_at)
        notifier.hausse(table_id, last.temp, probabilite, details, graphique)
    elif probabilite < SEUIL_FIN and table_id in _active:
        _active.discard(table_id)
        set_buzzer(table_id, "off")
