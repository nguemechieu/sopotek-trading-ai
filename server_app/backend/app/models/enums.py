from __future__ import annotations

from enum import Enum


class UserRole(str, Enum):
    ADMIN = "admin"
    TRADER = "trader"
    VIEWER = "viewer"


class LicensePlan(str, Enum):
    FREE = "free"
    PRO = "pro"
    ELITE = "elite"


class LicenseStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    REVOKED = "revoked"


class SubscriptionStatus(str, Enum):
    ACTIVE = "active"
    INCOMPLETE = "incomplete"
    PAST_DUE = "past_due"
    SUSPENDED = "suspended"
    CANCELED = "canceled"


class StrategyStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"
    PAUSED = "paused"


class OrderStatus(str, Enum):
    PENDING = "pending"
    WORKING = "working"
    FILLED = "filled"
    PARTIAL = "partial"
    CANCELED = "canceled"
    REJECTED = "rejected"


class LogLevel(str, Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
