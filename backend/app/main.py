from collections.abc import Iterator
from contextlib import asynccontextmanager
from pathlib import Path

import numpy as np
from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app import auth, detection, ml, models, retention, supervision
from app.config import settings
from app.db import Base, SessionLocal, engine
from app.mqtt import send_buzzer, send_led, start_mqtt
from app.schemas import (
    AlertOut,
    CommandeIn,
    DetectionOut,
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
    with engine.begin() as conn:
        conn.execute(
            text("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS kind VARCHAR(32) NOT NULL DEFAULT 'anomalie'")
        )
        conn.execute(text("ALTER TABLE alerts ADD COLUMN IF NOT EXISTS details JSON"))
        conn.execute(text("ALTER TABLE measurements ADD COLUMN IF NOT EXISTS pir INTEGER"))
        conn.execute(text("ALTER TABLE detections ADD COLUMN IF NOT EXISTS clip VARCHAR(128)"))
    mqtt_client = start_mqtt()
    arret_retention = retention.demarrer()
    yield
    arret_retention.set()
    mqtt_client.loop_stop()
    mqtt_client.disconnect()


app = FastAPI(title="SENTINEL-X API", lifespan=lifespan)
app.include_router(auth.router)

# Toutes les routes /api/v1 exigent un jeton, sauf la connexion (routeur auth)
PROTEGE = [Depends(auth.exiger_auth)]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/supervision", dependencies=PROTEGE)
def get_supervision(session: Session = Depends(get_session)) -> dict:
    return supervision.etat(session)


@app.get("/api/v1/mesures", response_model=list[MeasurementOut], dependencies=PROTEGE)
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


@app.get("/api/v1/alertes", response_model=list[AlertOut], dependencies=PROTEGE)
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


@app.get("/api/v1/detections", response_model=list[DetectionOut], dependencies=PROTEGE)
def list_detections(
    table_id: str | None = None,
    limit: int = 50,
    session: Session = Depends(get_session),
):
    stmt = (
        select(models.Detection)
        .order_by(models.Detection.created_at.desc())
        .limit(min(limit, 500))
    )
    if table_id:
        stmt = stmt.where(models.Detection.table_id == table_id)
    return session.scalars(stmt).all()


@app.get("/api/v1/detections/{detection_id}/clip", dependencies=PROTEGE)
def get_clip(detection_id: int, session: Session = Depends(get_session)):
    detection_row = session.get(models.Detection, detection_id)
    if detection_row is None or not detection_row.clip:
        raise HTTPException(status_code=404, detail="Pas de vidéo pour cette détection.")
    chemin = Path(settings.media_dir) / Path(detection_row.clip).name
    if chemin.suffix != ".mp4" or not chemin.is_file():
        raise HTTPException(status_code=404, detail="Fichier vidéo introuvable.")
    return FileResponse(chemin, media_type="video/mp4")


@app.get("/api/v1/tables/{table_id}/etat", response_model=EtatOut, dependencies=PROTEGE)
def etat(table_id: str) -> EtatOut:
    return EtatOut(
        alerte_active=detection.is_active(table_id),
        modele_entraine=ml.get_model(table_id) is not None,
    )


@app.post("/api/v1/tables/{table_id}/entrainement", response_model=EntrainementOut, dependencies=PROTEGE)
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


@app.post("/api/v1/tables/{table_id}/commande", status_code=202, dependencies=PROTEGE)
def commande(table_id: str, body: CommandeIn) -> dict[str, str]:
    if body.buzzer is None and body.led is None:
        raise HTTPException(status_code=422, detail="Indique buzzer, led, ou les deux.")
    if body.buzzer is not None:
        send_buzzer(table_id, body.buzzer)
    if body.led is not None:
        send_led(table_id, body.led)
    return body.model_dump(exclude_none=True)
