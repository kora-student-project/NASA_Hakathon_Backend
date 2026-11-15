"""Розбір рядка підключення: від нього залежить, чи підключиться Render/Neon до Postgres."""
import pytest

from app.database import _normalize_url

ASYNC = "postgresql+asyncpg://u:p@h"


@pytest.mark.parametrize(
    "url, expected_url, expected_args",
    [
        ("postgres://u:p@h:5432/db", f"{ASYNC}:5432/db", {"statement_cache_size": 0}),
        ("postgresql://u:p@h/db", f"{ASYNC}/db", {"statement_cache_size": 0}),
        # рядок Neon: asyncpg не розуміє sslmode/channel_binding, тому переводимо в connect_args
        ("postgresql://u:p@ep-x.neon.tech/db?sslmode=require&channel_binding=require",
         "postgresql+asyncpg://u:p@ep-x.neon.tech/db", {"ssl": "require", "statement_cache_size": 0}),
        ("postgresql://u:p@h/db?sslmode=disable", f"{ASYNC}/db", {"statement_cache_size": 0}),  # disable: без ssl
        ("postgresql+asyncpg://u:p@h/db?foo=bar&sslmode=verify-full", f"{ASYNC}/db?foo=bar",
         {"ssl": "require", "statement_cache_size": 0}),  # інші параметри лишаються
        ("sqlite+aiosqlite:///./kora.db", "sqlite+aiosqlite:///./kora.db", {}),  # SQLite не чіпаємо
    ],
)
def test_normalize_url(url, expected_url, expected_args):
    assert _normalize_url(url) == (expected_url, expected_args)
