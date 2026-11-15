"""Єдине місце бізнес-правил оцінки значень. API віддає готовий `severity`, клієнти нічого не перераховують."""
from app.config import get_settings
from app.schemas.object import Severity

TO_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0}


def classify(value: float, warning: float, critical: float) -> Severity:
    """Класифікує значення за модулем відносно порогів (строге «більше»)."""
    v = abs(value)
    if v > critical:
        return Severity.CRITICAL
    if v > warning:
        return Severity.WARNING
    return Severity.NORMAL


def to_mm(value: float, unit: str) -> float:
    return value * TO_MM[unit]


def displacement_severity(value: float, unit: str) -> Severity:
    s = get_settings()
    return classify(to_mm(value, unit), s.displacement_warning_threshold_mm, s.displacement_critical_threshold_mm)
