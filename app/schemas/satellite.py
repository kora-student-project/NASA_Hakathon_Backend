from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.object import Severity


class PointGeometry(BaseModel):
    type: Literal["Point"]
    coordinates: list[float] = Field(min_length=2, max_length=3, description="[lon, lat]")

    @field_validator("coordinates")
    @classmethod
    def check_range(cls, v: list[float]) -> list[float]:
        lon, lat = v[0], v[1]
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError("coordinates must be [longitude, latitude] within valid range")
        return v


class SatelliteCreate(BaseModel):
    object_id: int = Field(gt=0)
    displacement: float = Field(allow_inf_nan=False)
    unit: Literal["mm", "cm", "m"] = "mm"
    observation_date: date
    geometry: PointGeometry
    source: str = Field(default="NASA NISAR", min_length=1, max_length=100)


class SatelliteRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    object_id: int
    displacement: float
    unit: str
    observation_date: date
    geometry: dict[str, Any]
    source: str


class SatelliteIngestResult(BaseModel):
    status: str = "stored"
    observation_id: int
    severity: Severity
    alert_id: int | None = None
    alert_created: bool = False


class GeoJSONFeature(BaseModel):
    type: Literal["Feature"] = "Feature"
    geometry: dict[str, Any]
    properties: dict[str, Any]


class GeoJSONFeatureCollection(BaseModel):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    features: list[GeoJSONFeature]
