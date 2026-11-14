from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import MonitoredObject, SatelliteObservation
from app.ratelimit import limiter
from app.schemas.satellite import (
    GeoJSONFeature,
    GeoJSONFeatureCollection,
    SatelliteCreate,
    SatelliteIngestResult,
    SatelliteRead,
)
from app.security import require_satellite
from app.services import satellite_service

router = APIRouter(prefix="/api/satellite", tags=["satellite"])


@router.post(
    "/data",
    response_model=SatelliteIngestResult,
    status_code=201,
    dependencies=[Depends(require_satellite)],
)
@limiter.limit(get_settings().rate_limit_ingest)
async def ingest_satellite_data(
    request: Request, data: SatelliteCreate, db: AsyncSession = Depends(get_db)
):
    if await db.get(MonitoredObject, data.object_id) is None:
        raise HTTPException(404, f"Object {data.object_id} not found")
    return await satellite_service.ingest_observation(db, data)


def _filtered(object_id: int | None, from_: date | None, to: date | None, limit: int):
    if from_ and to and from_ > to:
        raise HTTPException(422, "'from' must be earlier than 'to'")
    q = select(SatelliteObservation)
    if object_id is not None:
        q = q.where(SatelliteObservation.object_id == object_id)
    if from_:
        q = q.where(SatelliteObservation.observation_date >= from_)
    if to:
        q = q.where(SatelliteObservation.observation_date <= to)
    return q.order_by(
        SatelliteObservation.observation_date.desc(), SatelliteObservation.id.desc()
    ).limit(limit)


@router.get("/data", response_model=list[SatelliteRead])
async def satellite_history(
    request: Request,
    object_id: int | None = None,
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    return (await db.execute(_filtered(object_id, from_, to, limit))).scalars().all()


@router.get("/map", response_model=GeoJSONFeatureCollection)
async def satellite_map(
    request: Request,
    object_id: int | None = None,
    from_: date | None = Query(None, alias="from"),
    to: date | None = None,
    limit: int = Query(500, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """GeoJSON FeatureCollection для відображення на карті (Leaflet / Mapbox)."""
    rows = (await db.execute(_filtered(object_id, from_, to, limit))).scalars().all()
    return GeoJSONFeatureCollection(
        features=[
            GeoJSONFeature(
                geometry=r.geometry,
                properties={
                    "id": r.id,
                    "object_id": r.object_id,
                    "displacement": r.displacement,
                    "unit": r.unit,
                    "observation_date": r.observation_date.isoformat(),
                    "source": r.source,
                },
            )
            for r in rows
        ]
    )
