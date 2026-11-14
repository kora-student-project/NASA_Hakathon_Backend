from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import MonitoredObject
from app.schemas.object import ObjectCreate, ObjectRead, ObjectStatus
from app.security import require_admin
from app.services import alert_service

router = APIRouter(prefix="/api/objects", tags=["objects"])


async def _get_or_404(db: AsyncSession, object_id: int) -> MonitoredObject:
    obj = await db.get(MonitoredObject, object_id)
    if obj is None:
        raise HTTPException(404, f"Object {object_id} not found")
    return obj


@router.post("", response_model=ObjectRead, status_code=201, dependencies=[Depends(require_admin)])
async def create_object(request: Request, data: ObjectCreate, db: AsyncSession = Depends(get_db)):
    obj = MonitoredObject(**data.model_dump())
    db.add(obj)
    await db.commit()
    return obj


@router.get("", response_model=list[ObjectRead])
async def list_objects(
    request: Request,
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    q = select(MonitoredObject).order_by(MonitoredObject.id).limit(limit).offset(offset)
    return (await db.execute(q)).scalars().all()


@router.get("/{object_id}", response_model=ObjectRead)
async def get_object(request: Request, object_id: int, db: AsyncSession = Depends(get_db)):
    return await _get_or_404(db, object_id)


@router.get("/{object_id}/status", response_model=ObjectStatus)
async def get_object_status(request: Request, object_id: int, db: AsyncSession = Depends(get_db)):
    obj = await _get_or_404(db, object_id)
    return await alert_service.compute_object_status(db, obj)
