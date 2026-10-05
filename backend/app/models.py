from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Measurement(Base):
    __tablename__ = "measurements"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[str] = mapped_column(String(64), index=True)
    temp: Mapped[float] = mapped_column(Float)
    hum: Mapped[float] = mapped_column(Float)
    gas: Mapped[int] = mapped_column(Integer)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(primary_key=True)
    table_id: Mapped[str] = mapped_column(String(64), index=True)
    temp: Mapped[float] = mapped_column(Float)
    hum: Mapped[float] = mapped_column(Float)
    gas: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
