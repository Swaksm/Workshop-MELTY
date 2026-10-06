from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DetectionIn(BaseModel):
    label: Literal["person"]
    confidence: float = Field(ge=0, le=1)
    image: str | None = None
    clip: str | None = None


class DetectionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    table_id: str
    label: str
    confidence: float
    created_at: datetime


class MeasurementIn(BaseModel):
    temp: float
    hum: float
    gas: int
    pir: int | None = Field(default=None, ge=0, le=1)


class MeasurementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    table_id: str
    temp: float
    hum: float
    gas: int
    pir: int | None = None
    received_at: datetime


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    table_id: str
    kind: str
    temp: float
    hum: float
    gas: int
    details: dict | None = None
    created_at: datetime


class CommandeIn(BaseModel):
    buzzer: Literal["on", "off"]


class EntrainementOut(BaseModel):
    mesures_utilisees: int


class EtatOut(BaseModel):
    alerte_active: bool
    modele_entraine: bool
