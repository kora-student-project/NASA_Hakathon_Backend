from fastapi import Request
from slowapi import Limiter

from app.config import get_settings


def client_key(request: Request) -> str:
    # За проксі (Render) реальний IP клієнта — перший у X-Forwarded-For
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


_s = get_settings()
limiter = Limiter(
    key_func=client_key,
    default_limits=[_s.rate_limit_default],
    enabled=_s.rate_limit_enabled,
)
