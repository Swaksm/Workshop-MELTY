from collections.abc import Callable
from datetime import timedelta

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import ml
from app.evolution_chart import graphique_evolution
from app.models import Alert, Measurement
from app.notifier import notifier

FENETRE_GRAPHIQUE = timedelta(minutes=15)
_active: set[str] = set()


def _mesures_recentes(session: Session, table_id: str, jusqu_a) -> list[Measurement]:
    return list(
        session.scalars(
            select(Measurement)
            .where(
                Measurement.table_id == table_id,
                Measurement.received_at >= jusqu_a - FENETRE_GRAPHIQUE,
                Measurement.received_at <= jusqu_a,
            )
            .order_by(Measurement.received_at)
        ).all()
    )


def is_active(table_id: str) -> bool:
    return table_id in _active


def evaluate(session: Session, table_id: str, set_buzzer: Callable[[str, str], None]) -> None:
    model = ml.get_model(table_id)
    if model is None:
        return

    rows = list(
        reversed(
            session.scalars(
                select(Measurement)
                .where(Measurement.table_id == table_id)
                .order_by(Measurement.id.desc())
                .limit(ml.WINDOW)
            ).all()
        )
    )
    values = np.array([[r.temp, r.hum, r.gas] for r in rows], dtype=float)
    anomaly = ml.is_anomaly(model, values)

    if anomaly and table_id not in _active:
        _active.add(table_id)
        last = rows[-1]
        details = ml.explication(model, values)
        session.add(
            Alert(
                table_id=table_id,
                temp=last.temp,
                hum=last.hum,
                gas=last.gas,
                details=details,
            )
        )
        session.commit()
        set_buzzer(table_id, "on")
        graphique = graphique_evolution(_mesures_recentes(session, table_id, last.received_at), last.received_at)
        notifier.anomalie(table_id, last.temp, last.hum, last.gas, details, graphique)
    elif not anomaly and table_id in _active:
        _active.discard(table_id)
        set_buzzer(table_id, "off")
