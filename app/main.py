from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api import alerts, meta, objects, satellite, sensors
from app.config import get_settings
from app.database import init_db
from app.ratelimit import limiter

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_db()
    yield


app = FastAPI(
    title="KORA Backend",
    description="Моніторинг стану будівель: NASA NISAR + IoT (ESP32/MPU6050). "
    "Попередження — індикатори для перевірки, а не висновок про аварійність.",
    version="1.0.0",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    cl = request.headers.get("content-length")
    if cl and cl.isdigit() and int(cl) > settings.max_body_bytes:
        return JSONResponse({"detail": "Request body too large"}, status_code=413)
    return await call_next(request)


# CORS додаємо останнім, щоб він був зовнішнім шаром і працював і для помилок
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(objects.router)
app.include_router(sensors.router)
app.include_router(satellite.router)
app.include_router(alerts.router)
app.include_router(meta.router)


@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse("/docs")


@app.get("/health", tags=["meta"])
async def health():
    return {"status": "ok"}
