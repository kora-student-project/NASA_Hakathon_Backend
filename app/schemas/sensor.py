from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SensorCreate(BaseModel):
    object_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=255)
    sensor_type: str = Field(min_length=1, max_length=100, examples=["tilt"])
    device_id: str | None = Field(
        default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_.:-]+$", examples=["kora_tracker_01"]
    )


class SensorRead(SensorCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    is_active: bool = True
    created_at: datetime


class SensorCreated(SensorRead):
    """Відповідь на реєстрацію: персональний ключ пристрою показується ЛИШЕ ОДИН РАЗ."""

    api_key: str


class SensorUpdate(BaseModel):
    is_active: bool
