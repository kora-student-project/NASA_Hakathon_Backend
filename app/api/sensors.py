from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Measurement, MonitoredObject, Sensor
from app.ratelimit import limiter
from app.config import get_settings
from app.schemas.measurement import MeasurementCreate, MeasurementIngestResult, MeasurementRead
from app.schemas.sensor import SensorCreate, SensorRead
from app.schemas.telemetry import DeviceTelemetry, TelemetryIngestResult
from app.services import telemetry_service
from app.security import require_admin, require_device
from app.services import sensor_service

router = APIRouter(prefix="/api/sensors", tags=["sensors"])


@router.post("", response_model=SensorRead, status_code=201, dependencies=[Depends(require_admin)])
async def register_sensor(request: Request, data: SensorCreate, db: AsyncSession = Depends(get_db)):
    if await db.get(MonitoredObject, data.object_id) is None:
        raise HTTPException(404, f"Object {data.object_id} not found")
    if data.device_id and await sensor_service.get_sensor_by_device(db, data.device_id):
        raise HTTPException(409, f"Device '{data.device_id}' is already registered")
    sensor = Sensor(**data.model_dump())
    db.add(sensor)
    await db.commit()
    return sensor


@router.get("", response_model=list[SensorRead])
async def list_sensors(
    request: Request,
    object_id: int | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    q = select(Sensor).order_by(Sensor.id).limit(limit)
    if object_id is not None:
        q = q.where(Sensor.object_id == object_id)
    return (await db.execute(q)).scalars().all()


@router.post(
    "/data",
    response_model=TelemetryIngestResult | MeasurementIngestResult,
    status_code=201,
    dependencies=[Depends(require_device)],
)
@limiter.limit(get_settings().rate_limit_ingest)
async def ingest_sensor_data(
    request: Request, data: DeviceTelemetry | MeasurementCreate, db: AsyncSession = Depends(get_db)
):
    """Єдиний endpoint для пристрою. Приймає два формати тіла:

    1. **Повідомлення пристрою** (`device_id`, `climate`, `imu`, `gps`): нахил рахується з акселерометра,
       час вимірювання = час отримання (UTC). Пристрій має бути зареєстрований з `device_id`.
    2. **Готове вимірювання** (`sensor_id`, `tilt_x`, `tilt_y`, `temperature`, `timestamp`).
    """
    if isinstance(data, DeviceTelemetry):
        sensor = await sensor_service.get_sensor_by_device(db, data.device_id)
        if sensor is None:
            raise HTTPException(404, f"Device '{data.device_id}' is not registered")
        return await telemetry_service.ingest_telemetry(db, sensor, data)

    sensor = await sensor_service.get_sensor(db, data.sensor_id)
    if sensor is None:
        raise HTTPException(404, f"Sensor {data.sensor_id} not found")
    try:
        return await sensor_service.ingest_measurement(db, sensor, data)
    except sensor_service.DuplicateMeasurement:
        raise HTTPException(409, "Measurement for this sensor and timestamp already exists")


@router.get("/{sensor_id}", response_model=SensorRead)
async def get_sensor(request: Request, sensor_id: int, db: AsyncSession = Depends(get_db)):
    sensor = await sensor_service.get_sensor(db, sensor_id)
    if sensor is None:
        raise HTTPException(404, f"Sensor {sensor_id} not found")
    return sensor


@router.get("/{sensor_id}/data", response_model=list[MeasurementRead])
async def sensor_history(
    request: Request,
    sensor_id: int,
    from_: datetime | None = Query(None, alias="from"),
    to: datetime | None = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    if await sensor_service.get_sensor(db, sensor_id) is None:
        raise HTTPException(404, f"Sensor {sensor_id} not found")
    if from_ and to and from_ > to:
        raise HTTPException(422, "'from' must be earlier than 'to'")
    q = select(Measurement).where(Measurement.sensor_id == sensor_id)
    if from_:
        q = q.where(Measurement.timestamp >= from_)
    if to:
        q = q.where(Measurement.timestamp <= to)
    q = q.order_by(Measurement.timestamp.desc()).limit(limit)
    return (await db.execute(q)).scalars().all()
