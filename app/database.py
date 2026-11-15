from collections.abc import AsyncIterator
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.types import DateTime, TypeDecorator

from app.config import get_settings


class Base(DeclarativeBase):
    pass


class UTCDateTime(TypeDecorator):
    """DateTime, що завжди зберігається та повертається як UTC (tz-aware).

    SQLite повертає naive-дати, тому нормалізуємо їх тут.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value: datetime | None, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def _normalize_url(url: str) -> tuple[str, dict]:
    """Приводить URL до async-драйвера. Повертає (url, connect_args)."""
    connect_args: dict = {}
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]
    if url.startswith("postgresql+asyncpg://"):
        parts = urlsplit(url)
        params = dict(parse_qsl(parts.query))
        sslmode = params.get("sslmode")
        # asyncpg не розуміє sslmode/channel_binding з рядків Neon/Supabase — переводимо в connect_args
        query = [(k, v) for k, v in params.items() if k not in ("sslmode", "channel_binding")]
        url = urlunsplit(parts._replace(query=urlencode(query)))
        if sslmode in ("require", "verify-ca", "verify-full"):
            connect_args["ssl"] = "require"
        # Supabase pooler (pgbouncer, transaction mode) не підтримує prepared statements
        connect_args["statement_cache_size"] = 0
    return url, connect_args


_url, _connect_args = _normalize_url(get_settings().database_url)
engine = create_async_engine(_url, connect_args=_connect_args, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session


log = logging.getLogger("kora.db")

# Унікальні індекси. Окремо від моделей, щоб їх можна було додати й до вже наявної бази
# (create_all не змінює існуючі таблиці, а міграцій немає). IF NOT EXISTS: безпечно запускати щоразу.
UNIQUE_INDEXES = (
    # одне супутникове спостереження на (об'єкт, дата, джерело)
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_sat_object_date_source "
    "ON satellite_observations (object_id, observation_date, source)",
    # одне АКТИВНЕ попередження на (об'єкт, датчик або супутник, рівень); coalesce, бо NULL у індексах різні
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_active_alert "
    "ON alerts (object_id, (coalesce(sensor_id, 0)), severity) WHERE is_resolved = false",
)


async def ensure_indexes(conn: AsyncConnection) -> None:
    for ddl in UNIQUE_INDEXES:
        await conn.execute(text(ddl))


async def init_db() -> None:
    from app import models  # noqa: F401  (реєстрація таблиць)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    for ddl in UNIQUE_INDEXES:  # кожен окремо: дублікати в старих даних не повинні зупиняти запуск
        try:
            async with engine.begin() as conn:
                await conn.execute(text(ddl))
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not create unique index (existing duplicates?): %s", exc)
