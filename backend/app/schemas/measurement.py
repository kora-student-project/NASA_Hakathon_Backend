from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.config import get_settings
from app.schemas.object import Severity


class MeasurementCreate(BaseModel):
    sensor_id: int = Field(gt=0)
    tilt_x: float = Field(ge=-90, le=90, allow_inf_nan=False)
    tilt_y: float = Field(ge=-90, le=90, allow_inf_nan=False)
    temperature: float | None = Field(default=None, ge=-100, le=200, allow_inf_nan=False)
    timestamp: datetime

    @field_validator("timestamp")
    @classmethod
    def to_utc(cls, v: datetime) -> datetime:
        # Naive час трактуємо як UTC
        v = v.replace(tzinfo=timezone.utc) if v.tzinfo is None else v.astimezone(timezone.utc)
        limit = datetime.now(timezone.utc) + timedelta(seconds=get_settings().max_future_skew_seconds)
        if v > limit:
            raise ValueError("timestamp is in the future")
        return v


class MeasurementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sensor_id: int
    tilt_x: float
    tilt_y: float
    temperature: float | None
    timestamp: datetime


class MeasurementIngestResult(BaseModel):
    status: str = "stored"
    measurement_id: int
    severity: Severity
    alert_id: int | None = None
    alert_created: bool = False
