from datetime import datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Alert, Measurement, MonitoredObject, SatelliteObservation, Sensor
from app.schemas.object import (
    LatestSatelliteData,
    LatestSensorData,
    ObjectStatus,
    ObjectStatusValue,
    Severity,
)

_RANK = {Severity.NORMAL: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}
_TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0}


def classify(value: float, warning: float, critical: float) -> Severity:
    """Класифікує значення за модулем відносно порогів."""
    v = abs(value)
    if v > critical:
        return Severity.CRITICAL
    if v > warning:
        return Severity.WARNING
    return Severity.NORMAL


async def _create_alert_dedup(
    db: AsyncSession, object_id: int, sensor_id: int | None, severity: Severity, message: str
) -> tuple[Alert, bool]:
    """Створює попередження, якщо такого ж активного (object+sensor+severity) ще нема."""
    cond = [
        Alert.object_id == object_id,
        Alert.severity == severity.value,
        Alert.is_resolved.is_(False),
        Alert.sensor_id.is_(None) if sensor_id is None else Alert.sensor_id == sensor_id,
    ]
    existing = (await db.execute(select(Alert).where(*cond).limit(1))).scalar_one_or_none()
    if existing:
        return existing, False
    alert = Alert(
        object_id=object_id, sensor_id=sensor_id, severity=severity.value, message=message
    )
    db.add(alert)
    await db.flush()
    return alert, True


async def evaluate_measurement(
    db: AsyncSession, sensor: Sensor, m: Measurement
) -> tuple[Severity, Alert | None, bool]:
    s = get_settings()
    worst_axis, worst_val = max((("tilt_x", m.tilt_x), ("tilt_y", m.tilt_y)), key=lambda p: abs(p[1]))
    severity = classify(worst_val, s.tilt_warning_threshold, s.tilt_critical_threshold)
    if severity is Severity.NORMAL:
        return severity, None, False
    limit = (
        s.tilt_critical_threshold if severity is Severity.CRITICAL else s.tilt_warning_threshold
    )
    msg = (
        f"{severity.value}: {worst_axis}={worst_val:.2f}° exceeds {limit:.2f}° "
        f"(sensor '{sensor.name}'). Requires inspection; not a conclusion about structural failure."
    )
    alert, created = await _create_alert_dedup(db, sensor.object_id, sensor.id, severity, msg)
    return severity, alert, created


async def evaluate_satellite(
    db: AsyncSession, obs: SatelliteObservation
) -> tuple[Severity, Alert | None, bool]:
    s = get_settings()
    mm = obs.displacement * _TO_MM[obs.unit]
    severity = classify(mm, s.displacement_warning_threshold_mm, s.displacement_critical_threshold_mm)
    if severity is Severity.NORMAL:
        return severity, None, False
    limit = (
        s.displacement_critical_threshold_mm
        if severity is Severity.CRITICAL
        else s.displacement_warning_threshold_mm
    )
    msg = (
        f"{severity.value}: satellite displacement {mm:.1f} mm exceeds {limit:.1f} mm "
        f"({obs.source}, {obs.observation_date}). Requires verification."
    )
    alert, created = await _create_alert_dedup(db, obs.object_id, None, severity, msg)
    return severity, alert, created


async def compute_object_status(db: AsyncSession, obj: MonitoredObject) -> ObjectStatus:
    """UNKNOWN — якщо даних немає взагалі; інакше найвищий рівень активних алертів, або NORMAL."""
    latest_m = (
        await db.execute(
            select(Measurement)
            .join(Sensor, Sensor.id == Measurement.sensor_id)
            .where(Sensor.object_id == obj.id)
            .order_by(Measurement.timestamp.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    latest_s = (
        await db.execute(
            select(SatelliteObservation)
            .where(SatelliteObservation.object_id == obj.id)
            .order_by(SatelliteObservation.observation_date.desc(), SatelliteObservation.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    active = (
        await db.execute(
            select(Alert.severity).where(Alert.object_id == obj.id, Alert.is_resolved.is_(False))
        )
    ).scalars().all()

    if latest_m is None and latest_s is None:
        status = ObjectStatusValue.UNKNOWN
    elif active:
        worst = max((Severity(a) for a in active), key=lambda x: _RANK[x])
        status = ObjectStatusValue(worst.value)
    else:
        status = ObjectStatusValue.NORMAL

    stamps = []
    if latest_m:
        stamps.append(latest_m.timestamp)
    if latest_s:
        stamps.append(datetime.combine(latest_s.observation_date, time.min, tzinfo=timezone.utc))

    return ObjectStatus(
        object_id=obj.id,
        status=status,
        latest_sensor_data=LatestSensorData(
            sensor_id=latest_m.sensor_id,
            tilt_x=latest_m.tilt_x,
            tilt_y=latest_m.tilt_y,
            temperature=latest_m.temperature,
            humidity=(latest_m.extra or {}).get("humidity"),
            timestamp=latest_m.timestamp,
        )
        if latest_m
        else None,
        latest_satellite_data=LatestSatelliteData(
            displacement=latest_s.displacement,
            unit=latest_s.unit,
            observation_date=latest_s.observation_date,
        )
        if latest_s
        else None,
        active_alerts=len(active),
        last_updated=max(stamps) if stamps else None,
    )
