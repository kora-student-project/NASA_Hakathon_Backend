from math import atan2, degrees, hypot

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.schemas.measurement import MeasurementCreate
from app.schemas.telemetry import DeviceTelemetry, TelemetryIngestResult
from app.models import Sensor
from app.services import sensor_service
from datetime import datetime, timezone


def tilt_from_accel(ax: float, ay: float, az: float, vertical: str) -> tuple[float, float]:
    """Нахил (градуси) по двох горизонтальних осях відносно гравітації.

    Для кожної горизонтальної осі a: кут = atan2(a, hypot(інша_горизонтальна, вертикальна)).
    Порядок: осі x, y, z без вертикальної. Не залежить від знака вертикальної осі.
    """
    if vertical not in ("x", "y", "z"):
        raise ValueError("DEVICE_VERTICAL_AXIS must be x, y or z")
    a = {"x": ax, "y": ay, "z": az}
    h1, h2 = [k for k in "xyz" if k != vertical]
    v = a[vertical]
    return (
        degrees(atan2(a[h1], hypot(a[h2], v))),
        degrees(atan2(a[h2], hypot(a[h1], v))),
    )


def build_extra(t: DeviceTelemetry) -> dict:
    extra: dict = {"device_id": t.device_id, "device_uptime_ms": t.timestamp_ms}
    if t.climate and t.climate.humidity is not None:
        extra["humidity"] = t.climate.humidity
    extra["accel"] = t.imu.accel.model_dump()
    if t.imu.gyro:
        extra["gyro"] = t.imu.gyro.model_dump()
    if t.gps:
        gps = t.gps.model_dump()
        if not (t.gps.valid and t.gps.lat is not None and t.gps.lng is not None):
            gps["lat"] = gps["lng"] = None  # без фіксу координати недостовірні
        extra["gps"] = gps
    return extra


async def ingest_telemetry(db: AsyncSession, sensor: Sensor, t: DeviceTelemetry) -> TelemetryIngestResult:
    a = t.imu.accel
    tilt_x, tilt_y = tilt_from_accel(a.x, a.y, a.z, get_settings().device_vertical_axis)
    data = MeasurementCreate(
        sensor_id=sensor.id,
        tilt_x=round(tilt_x, 4),
        tilt_y=round(tilt_y, 4),
        temperature=t.climate.temperature if t.climate else None,
        # timestamp_ms у пристрої — uptime, а не календарний час: беремо час отримання (UTC)
        timestamp=datetime.now(timezone.utc),
    )
    res = await sensor_service.ingest_measurement(db, sensor, data, extra=build_extra(t))
    return TelemetryIngestResult(**res.model_dump(), sensor_id=sensor.id, tilt_x=data.tilt_x, tilt_y=data.tilt_y)
