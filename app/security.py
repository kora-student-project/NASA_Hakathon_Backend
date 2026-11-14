import hashlib
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable

from fastapi import Header, HTTPException, status

from app.config import get_settings


def _require(*key_attrs: str) -> Callable:
    """Dependency: перевіряє X-API-Key. Адмін-ключ приймається скрізь."""

    async def dependency(x_api_key: str | None = Header(default=None)) -> None:
        settings = get_settings()
        valid = [
            getattr(settings, a) for a in ("api_key_admin", *key_attrs) if getattr(settings, a)
        ]
        if not valid:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "API keys are not configured on the server"
            )
        if not x_api_key or not any(secrets.compare_digest(x_api_key, k) for k in valid):
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Invalid or missing API key",
                headers={"WWW-Authenticate": "ApiKey"},
            )

    return dependency


require_admin = _require()
require_satellite = _require("api_key_satellite")


# ---------- Персональні ключі пристроїв ----------


def new_device_key() -> str:
    return "kora_" + secrets.token_urlsafe(32)


def hash_key(key: str) -> str:
    # Ключ має високу ентропію (256 біт), тому швидкого SHA-256 достатньо
    return hashlib.sha256(key.encode()).hexdigest()


def _is_admin(key: str | None) -> bool:
    admin = get_settings().api_key_admin
    return bool(key and admin and secrets.compare_digest(key, admin))


def authorize_device(sensor, key: str | None) -> None:
    """Пропускає лише власника цього датчика (або admin).

    Невідомий пристрій і хибний ключ повертають однакове 401, щоб не можна було
    перебирати існуючі device_id.
    """
    if _is_admin(key):
        return
    ok = bool(
        sensor is not None
        and key
        and sensor.api_key_hash
        and secrets.compare_digest(hash_key(key), sensor.api_key_hash)
    )
    if not ok:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Invalid or missing device key", headers={"WWW-Authenticate": "ApiKey"}
        )
    if not sensor.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Device is disabled")


class DeviceRateLimiter:
    """Ковзне вікно 60 с на пристрій (в пам'яті процесу). Захищає від спаму зі скомпрометованим ключем."""

    def __init__(self) -> None:
        self._hits: dict[int, deque[float]] = defaultdict(deque)

    def check(self, sensor_id: int) -> None:
        s = get_settings()
        if not s.rate_limit_enabled:
            return
        now = time.monotonic()
        q = self._hits[sensor_id]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= s.device_max_per_minute:
            raise HTTPException(
                status.HTTP_429_TOO_MANY_REQUESTS, "Too many measurements from this device", headers={"Retry-After": "60"}
            )
        q.append(now)


device_limiter = DeviceRateLimiter()
