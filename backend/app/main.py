from collections.abc import Iterator
from contextlib import asynccontextmanager

import numpy as np
from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import detection, ml, models
from app.db import Base, SessionLocal, engine
from app.mqtt import send_buzzer, start_mqtt
from app.schemas import (
    AlertOut,
    CommandeIn,
    EntrainementOut,
    EtatOut,
    MeasurementOut,
)


def get_session() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    mqtt_client = start_mqtt()
    yield
    mqtt_client.loop_stop()
    mqtt_client.disconnect()


app = FastAPI(title="SENTINEL-X API", lifespan=lifespan)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/mesures", response_model=list[MeasurementOut])
def list_mesures(
    table_id: str | None = None,
    limit: int = 100,
    session: Session = Depends(get_session),
):
    stmt = (
        select(models.Measurement)
        .order_by(models.Measurement.received_at.desc())
        .limit(min(limit, 1000))
    )
    if table_id:
        stmt = stmt.where(models.Measurement.table_id == table_id)
    return session.scalars(stmt).all()


@app.get("/api/v1/alertes", response_model=list[AlertOut])
def list_alertes(
    table_id: str | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    stmt = (
        select(models.Alert)
        .order_by(models.Alert.created_at.desc())
        .limit(min(limit, 500))
    )
    if table_id:
        stmt = stmt.where(models.Alert.table_id == table_id)
    return session.scalars(stmt).all()


@app.get("/api/v1/tables/{table_id}/etat", response_model=EtatOut)
def etat(table_id: str) -> EtatOut:
    return EtatOut(
        alerte_active=detection.is_active(table_id),
        modele_entraine=ml.get_model(table_id) is not None,
    )


@app.post("/api/v1/tables/{table_id}/entrainement", response_model=EntrainementOut)
def entrainement(table_id: str, session: Session = Depends(get_session)):
    rows = list(
        reversed(
            session.scalars(
                select(models.Measurement)
                .where(models.Measurement.table_id == table_id)
                .order_by(models.Measurement.id.desc())
                .limit(5000)
            ).all()
        )
    )
    if len(rows) < ml.MIN_TRAINING_SAMPLES:
        raise HTTPException(
            status_code=400,
            detail=f"Au moins {ml.MIN_TRAINING_SAMPLES} mesures sont nécessaires (actuellement {len(rows)}).",
        )
    values = np.array([[r.temp, r.hum, r.gas] for r in rows], dtype=float)
    ml.train(table_id, values)
    return EntrainementOut(mesures_utilisees=len(rows))


@app.post("/api/v1/tables/{table_id}/commande", status_code=202)
def commande(table_id: str, body: CommandeIn) -> dict[str, str]:
    send_buzzer(table_id, body.buzzer)
    return {"buzzer": body.buzzer}
