from datetime import datetime

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
