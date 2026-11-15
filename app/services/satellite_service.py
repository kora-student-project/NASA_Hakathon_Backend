from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SatelliteObservation
from app.schemas.satellite import SatelliteCreate, SatelliteIngestResult
from app.services import alert_service


class DuplicateObservation(Exception):
    pass


async def ingest_observation(db: AsyncSession, data: SatelliteCreate) -> SatelliteIngestResult:
    obs = SatelliteObservation(**data.model_dump())
    db.add(obs)
    try:
        await db.flush()
    except IntegrityError as exc:
        await db.rollback()
        raise DuplicateObservation from exc
    severity, alert, created = await alert_service.evaluate_satellite(db, obs)
    await db.commit()
    return SatelliteIngestResult(
        observation_id=obs.id,
        severity=severity,
        alert_id=alert.id if alert else None,
        alert_created=created,
    )
