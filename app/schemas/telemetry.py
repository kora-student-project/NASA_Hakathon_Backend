from pydantic import BaseModel, Field, model_validator

from app.schemas.measurement import MeasurementIngestResult

_PATTERN_ID = r"^[A-Za-z0-9_.:-]+$"


class Vec3(BaseModel):
    x: float = Field(allow_inf_nan=False, ge=-2000, le=2000)
    y: float = Field(allow_inf_nan=False, ge=-2000, le=2000)
    z: float = Field(allow_inf_nan=False, ge=-2000, le=2000)


class Climate(BaseModel):
    temperature: float | None = Field(default=None, ge=-100, le=200, allow_inf_nan=False)
    humidity: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)


class Imu(BaseModel):
    accel: Vec3  # м/с²
    gyro: Vec3 | None = None


class Gps(BaseModel):
    lat: float | None = Field(default=None, ge=-90, le=90)
    lng: float | None = Field(default=None, ge=-180, le=180)
    sats: int | None = Field(default=None, ge=0, le=99)
    time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}:\d{2}$")  # UTC, без дати
    valid: bool = False


class DeviceTelemetry(BaseModel):
    """Формат повідомлення від пристрою (kora_tracker_*)."""

    device_id: str = Field(min_length=1, max_length=100, pattern=_PATTERN_ID)
    timestamp_ms: int | None = Field(default=None, ge=0, description="Час роботи пристрою (uptime), мс")
    climate: Climate | None = None
    imu: Imu
    gps: Gps | None = None

    @model_validator(mode="after")
    def accel_not_zero(self):
        a = self.imu.accel
        if a.x == 0 and a.y == 0 and a.z == 0:
            raise ValueError("accelerometer reads 0 on all axes: cannot compute tilt")
        return self


class TelemetryIngestResult(MeasurementIngestResult):
    sensor_id: int
    tilt_x: float
    tilt_y: float
