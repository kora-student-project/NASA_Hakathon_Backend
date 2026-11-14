from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Measurement, Sensor
from app.schemas.measurement import MeasurementCreate, MeasurementIngestResult
from app.services import alert_service


class DuplicateMeasurement(Exception):
    pass


async def ingest_measurement(
    db: AsyncSession, sensor: Sensor, data: MeasurementCreate
) -> MeasurementIngestResult:
    m = Measurement(**data.model_dump())
    db.add(m)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateMeasurement from exc
    severity, alert, created = await alert_service.evaluate_measurement(db, sensor, m)
    await db.commit()
    return MeasurementIngestResult(
        measurement_id=m.id,
        severity=severity,
        alert_id=alert.id if alert else None,
        alert_created=created,
    )


async def get_sensor(db: AsyncSession, sensor_id: int) -> Sensor | None:
    return (await db.execute(select(Sensor).where(Sensor.id == sensor_id))).scalar_one_or_none()
