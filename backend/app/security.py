import secrets
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
require_device = _require("api_key_device")
require_satellite = _require("api_key_satellite")
