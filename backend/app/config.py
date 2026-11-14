from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Усі налаштування читаються зі змінних середовища / файлу .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # База даних. Для Supabase: postgresql://user:pass@host:5432/postgres
    database_url: str = "sqlite+aiosqlite:///./kora.db"

    # API-ключі (заголовок X-API-Key). Порожнє значення = запис відхиляється.
    api_key_admin: str = ""  # створення об'єктів/датчиків, закриття алертів
    api_key_device: str = ""  # ESP32 -> POST /api/sensors/data
    api_key_satellite: str = ""  # NISAR-модуль -> POST /api/satellite/data

    # CORS: список через кому, або "*"
    cors_origins: str = "http://localhost:5173,http://localhost:3000"

    # Яка вісь акселерометра вертикальна (дивиться вздовж гравітації, ≈9.81 м/с² у спокої).
    # tilt_x/tilt_y рахуються по двох інших осях за порядком x, y, z.
    device_vertical_axis: str = "y"

    # Пороги нахилу (градуси, по модулю)
    tilt_warning_threshold: float = 2.0
    tilt_critical_threshold: float = 5.0

    # Пороги зміщення за супутником (міліметри, по модулю)
    displacement_warning_threshold_mm: float = 10.0
    displacement_critical_threshold_mm: float = 25.0

    # Обмеження
    rate_limit_enabled: bool = True
    rate_limit_ingest: str = "60/minute"
    rate_limit_default: str = "120/minute"
    max_body_bytes: int = 64 * 1024
    max_future_skew_seconds: int = 86400  # допуск на зсув годинника ESP32: не далі ніж на добу в майбутнє

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
