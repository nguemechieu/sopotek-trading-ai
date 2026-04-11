from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampedMixin
from app.models.enums import LicensePlan, SubscriptionStatus


class Subscription(TimestampedMixin, Base):
    __tablename__ = "subscriptions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    license_id: Mapped[str] = mapped_column(ForeignKey("licenses.id", ondelete="CASCADE"), index=True)
    provider: Mapped[str] = mapped_column(String(32), default="internal", index=True)
    plan: Mapped[LicensePlan] = mapped_column(Enum(LicensePlan), default=LicensePlan.FREE, index=True)
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus), default=SubscriptionStatus.ACTIVE, index=True
    )
    stripe_customer_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    stripe_price_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    last_payment_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(512), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)

    user = relationship("User", back_populates="subscriptions")
    license = relationship("License", back_populates="subscriptions")
