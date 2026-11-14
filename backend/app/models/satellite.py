from datetime import date

from sqlalchemy import JSON, Date, Float, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class SatelliteObservation(Base):
    __tablename__ = "satellite_observations"
    __table_args__ = (Index("ix_sat_object_date", "object_id", "observation_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    displacement: Mapped[float] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(10))
    observation_date: Mapped[date] = mapped_column(Date)
    geometry: Mapped[dict] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    source: Mapped[str] = mapped_column(String(100))
