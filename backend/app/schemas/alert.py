from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.object import Severity


class AlertRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    object_id: int
    sensor_id: int | None
    severity: Severity
    message: str
    created_at: datetime
    is_resolved: bool
