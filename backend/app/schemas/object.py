from datetime import date, datetime
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class Severity(str, Enum):
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ObjectStatusValue(str, Enum):
    UNKNOWN = "UNKNOWN"
    NORMAL = "NORMAL"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ObjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = Field(default=None, max_length=5000)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class ObjectRead(ObjectCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: datetime


class LatestSensorData(BaseModel):
    sensor_id: int
    tilt_x: float
    tilt_y: float
    temperature: float | None = None
    timestamp: datetime


class LatestSatelliteData(BaseModel):
    displacement: float
    unit: str
    observation_date: date


class ObjectStatus(BaseModel):
    object_id: int
    status: ObjectStatusValue
    latest_sensor_data: LatestSensorData | None
    latest_satellite_data: LatestSatelliteData | None
    active_alerts: int
    last_updated: datetime | None
