from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, UTCDateTime
from app.models.object import utcnow


class Alert(Base):
    __tablename__ = "alerts"
    __table_args__ = (Index("ix_alerts_object_resolved", "object_id", "is_resolved"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    object_id: Mapped[int] = mapped_column(ForeignKey("objects.id", ondelete="CASCADE"))
    sensor_id: Mapped[int | None] = mapped_column(
        ForeignKey("sensors.id", ondelete="SET NULL"), nullable=True
    )
    severity: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(Text)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
