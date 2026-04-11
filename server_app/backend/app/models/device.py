from __future__ import annotations

from uuid import uuid4

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampedMixin


class Device(TimestampedMixin, Base):
    __tablename__ = "devices"
    __table_args__ = (UniqueConstraint("license_id", "device_hash", name="uq_devices_license_hash"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    license_id: Mapped[str] = mapped_column(ForeignKey("licenses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    device_hash: Mapped[str] = mapped_column(String(128), index=True)
    app_version: Mapped[str] = mapped_column(String(64), default="unknown")
    last_ip: Mapped[str | None] = mapped_column(String(128), nullable=True)
    validation_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    license = relationship("License", back_populates="devices")
    user = relationship("User", back_populates="devices")
