from collections.abc import Iterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models
from app.db import Base, SessionLocal, engine
from app.mqtt import start_mqtt
from app.schemas import MeasurementOut


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
