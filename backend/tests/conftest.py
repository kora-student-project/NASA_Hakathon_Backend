import os

os.environ.update(
    DATABASE_URL="sqlite+aiosqlite:///:memory:",
    API_KEY_ADMIN="admin-key",
    API_KEY_DEVICE="device-key",
    API_KEY_SATELLITE="sat-key",
    RATE_LIMIT_ENABLED="false",
)

import pytest_asyncio  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy.pool import StaticPool  # noqa: E402

from app import database  # noqa: E402
from app.main import app  # noqa: E402


@pytest_asyncio.fixture
async def client():
    # Одна in-memory БД на тест
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    database.engine = engine
    database.SessionLocal = async_sessionmaker(engine, expire_on_commit=False)

    async def override():
        async with database.SessionLocal() as s:
            yield s

    app.dependency_overrides[database.get_db] = override
    from app import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(database.Base.metadata.create_all)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
    await engine.dispose()
