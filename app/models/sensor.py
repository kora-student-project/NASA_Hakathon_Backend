from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime
from app.models.object import utcnow


class Sensor(Base):
    __tablename__ = "sensors"

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255))
    sensor_type: Mapped[str] = mapped_column(String(100))
    # Ідентифікатор фізичного пристрою (напр. "kora_tracker_01") для POST /api/sensors/data
    device_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True, nullable=True)
    # SHA-256 від персонального ключа пристрою (сам ключ не зберігається)
    api_key_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
