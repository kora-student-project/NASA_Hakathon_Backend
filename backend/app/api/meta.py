from fastapi import APIRouter, Request
from pydantic import BaseModel

from app.config import get_settings

router = APIRouter(prefix="/api", tags=["meta"])


class Thresholds(BaseModel):
    tilt_warning: float
    tilt_critical: float
    displacement_warning_mm: float
    displacement_critical_mm: float


@router.get("/thresholds", response_model=Thresholds)
async def thresholds(request: Request):
    """Поточні пороги попереджень (для відображення на графіках)."""
    s = get_settings()
    return Thresholds(
        tilt_warning=s.tilt_warning_threshold,
        tilt_critical=s.tilt_critical_threshold,
        displacement_warning_mm=s.displacement_warning_threshold_mm,
        displacement_critical_mm=s.displacement_critical_threshold_mm,
    )
