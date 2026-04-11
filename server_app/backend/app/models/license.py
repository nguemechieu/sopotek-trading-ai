from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampedMixin
from app.models.enums import LicensePlan, LicenseStatus


class License(TimestampedMixin, Base):
    __tablename__ = "licenses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    plan: Mapped[LicensePlan] = mapped_column(Enum(LicensePlan), default=LicensePlan.FREE, index=True)
    status: Mapped[LicenseStatus] = mapped_column(Enum(LicenseStatus), default=LicenseStatus.ACTIVE, index=True)
    key_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    key_mask: Mapped[str] = mapped_column(String(64), index=True)
    max_devices: Mapped[int] = mapped_column(Integer, default=1)
    features_json: Mapped[list] = mapped_column(JSON, default=list)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    suspicious_events: Mapped[int] = mapped_column(Integer, default=0)
    failed_validation_count: Mapped[int] = mapped_column(Integer, default=0)
    validation_count: Mapped[int] = mapped_column(Integer, default=0)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_validated_ip: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_validated_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    user = relationship("User", back_populates="licenses")
    devices = relationship("Device", back_populates="license", cascade="all, delete-orphan")
    subscriptions = relationship("Subscription", back_populates="license", cascade="all, delete-orphan")
