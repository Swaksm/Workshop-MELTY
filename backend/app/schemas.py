from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict


class MeasurementIn(BaseModel):
    temp: float
    hum: float
    gas: int


class MeasurementOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    table_id: str
    temp: float
    hum: float
    gas: int
    received_at: datetime


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    table_id: str
    temp: float
    hum: float
    gas: int
    created_at: datetime


class CommandeIn(BaseModel):
    buzzer: Literal["on", "off"]


class EntrainementOut(BaseModel):
    mesures_utilisees: int


class EtatOut(BaseModel):
    alerte_active: bool
    modele_entraine: bool
