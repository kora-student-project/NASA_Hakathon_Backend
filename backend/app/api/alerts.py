from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Alert
from app.schemas.alert import AlertRead
from app.schemas.object import Severity
from app.security import require_admin

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("", response_model=list[AlertRead])
async def list_alerts(
    request: Request,
    object_id: int | None = None,
    sensor_id: int | None = None,
    severity: Severity | None = None,
    is_resolved: bool | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    q = select(Alert).order_by(Alert.created_at.desc(), Alert.id.desc()).limit(limit)
    if object_id is not None:
        q = q.where(Alert.object_id == object_id)
    if sensor_id is not None:
        q = q.where(Alert.sensor_id == sensor_id)
    if severity is not None:
        q = q.where(Alert.severity == severity.value)
    if is_resolved is not None:
        q = q.where(Alert.is_resolved.is_(is_resolved))
    return (await db.execute(q)).scalars().all()


@router.get("/{alert_id}", response_model=AlertRead)
async def get_alert(request: Request, alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, f"Alert {alert_id} not found")
    return alert


@router.patch(
    "/{alert_id}/resolve", response_model=AlertRead, dependencies=[Depends(require_admin)]
)
async def resolve_alert(request: Request, alert_id: int, db: AsyncSession = Depends(get_db)):
    alert = await db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, f"Alert {alert_id} not found")
    alert.is_resolved = True
    await db.commit()
    return alert
