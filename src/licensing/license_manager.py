from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from urllib import error, request


class LicenseManager:
    TRIAL_DAYS = 14
    PREMIUM_FEATURES = {"live_trading"}
    SERVER_RESTRICTED_FEATURES = {
        "ai_trading",
        "desktop_sync",
        "institutional_risk",
        "live_trading",
        "multi_exchange",
        "portfolio_automation",
        "priority_support",
    }
    SERVER_KEY_PATTERN = re.compile(r"^SOPOTEK-[A-Z0-9]{4}-[A-Z0-9]{4}-[A-Z0-9]{4}$")
    DEFAULT_SERVER_URL = "http://127.0.0.1:8000/api/license/validate"
    SERVER_URL_ENV_KEYS = ("SOPOTEK_LICENSE_API_URL", "SOPOTEK_PLATFORM_LICENSE_API_URL")

    def __init__(self, settings, logger=None):
        self.settings = settings
        self.logger = logger
        self._ensure_trial_started()

    def _now(self):
        return datetime.now(timezone.utc)

    def _iso(self, value):
        if value is None:
            return ""
        if isinstance(value, datetime):
            if value.tzinfo is None:
                value = value.replace(tzinfo=timezone.utc)
            return value.astimezone(timezone.utc).isoformat()
        return str(value)

    def _parse_datetime(self, value):
        text = str(value or "").strip()
        if not text:
            return None
        try:
            parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except Exception:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    def _setting(self, key, default=""):
        try:
            return self.settings.value(key, default)
        except Exception:
            return default

    def _set(self, key, value):
        try:
            self.settings.setValue(key, value)
        except Exception:
            pass

    def _remove(self, key):
        try:
            self.settings.remove(key)
        except Exception:
            pass

    def _ensure_trial_started(self):
        started = self._parse_datetime(self._setting("license/trial_started_at", ""))
        if started is not None:
            return
        self._set("license/trial_started_at", self._iso(self._now()))

    def _normalize_key(self, key):
        cleaned = str(key or "").upper().strip()
        cleaned = re.sub(r"[^A-Z0-9-]", "", cleaned)
        cleaned = re.sub(r"-+", "-", cleaned)
        return cleaned

    def _subscription_duration(self, key):
        match = re.search(r"\b(\d+)([DMY])\b", key)
        if not match:
            return timedelta(days=365)
        value = max(1, int(match.group(1)))
        unit = match.group(2)
        if unit == "D":
            return timedelta(days=value)
        if unit == "Y":
            return timedelta(days=value * 365)
        return timedelta(days=value * 30)

    def _plan_name(self, plan):
        normalized = str(plan or "").strip().lower()
        if not normalized:
            return "Server License"
        if normalized == "free":
            return "Free License"
        return f"{normalized.title()} License"

    def _server_payload(self):
        raw = str(self._setting("license/server_validation_payload", "") or "").strip()
        if not raw:
            return None
        try:
            payload = json.loads(raw)
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _save_server_payload(self, key, payload):
        cached = dict(payload or {})
        cached["license_key"] = key
        cached["validated_at"] = self._iso(self._now())
        cached["server_url"] = self.server_api_url()
        self._set("license/server_validation_payload", json.dumps(cached, separators=(",", ":")))

    def _device_id(self):
        return f"desktop-{uuid.getnode():012x}"

    def server_api_url(self):
        stored = str(self._setting("license/server_api_url", "") or "").strip()
        if stored:
            return stored
        for env_key in self.SERVER_URL_ENV_KEYS:
            candidate = str(os.getenv(env_key, "") or "").strip()
            if candidate:
                return candidate
        return self.DEFAULT_SERVER_URL

    def set_server_api_url(self, raw_url):
        normalized = str(raw_url or "").strip()
        if normalized:
            self._set("license/server_api_url", normalized)
        else:
            self._remove("license/server_api_url")

    def _store_server_activation(self, key, payload):
        self._set("license/key", key)
        self._set("license/type", "server")
        self._set("license/plan_name", self._plan_name(payload.get("plan")))
        self._set("license/activated_at", self._iso(self._now()))
        expires_at = self._parse_datetime(payload.get("expires_at"))
        if expires_at is not None:
            self._set("license/expires_at", self._iso(expires_at))
        else:
            self._remove("license/expires_at")
        self._save_server_payload(key, payload)

    def _validate_server_online(self, key):
        body = json.dumps(
            {
                "license_key": key,
                "device_id": self._device_id(),
                "app_version": str(os.getenv("SOPOTEK_APP_VERSION", "desktop-ui")).strip() or "desktop-ui",
            }
        ).encode("utf-8")
        req = request.Request(
            self.server_api_url(),
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            try:
                payload = json.loads(exc.read().decode("utf-8"))
            except Exception:
                payload = {}
            message = ""
            if isinstance(payload, dict):
                message = str(payload.get("message") or payload.get("detail") or "").strip()
            return {"valid": False, "message": message or f"License server returned HTTP {exc.code}."}

    def _validate_server_offline(self, key):
        cached = self._server_payload()
        if not cached or self._normalize_key(cached.get("license_key")) != key:
            return {"valid": False, "message": "No cached server validation is available for this license."}
        if not cached.get("valid"):
            return {"valid": False, "message": "The cached server response is not valid."}
        now = self._now()
        expires_at = self._parse_datetime(cached.get("expires_at"))
        if expires_at is not None and expires_at <= now:
            return {"valid": False, "message": "The cached server license has already expired."}
        offline_valid_until = self._parse_datetime(cached.get("offline_valid_until"))
        if offline_valid_until is not None and offline_valid_until <= now:
            return {"valid": False, "message": "The offline grace period for this server license has expired."}
        payload = dict(cached)
        payload["valid"] = True
        payload["message"] = "Offline grace mode enabled from cached server validation."
        return payload

    def _activate_server_key(self, key):
        try:
            result = self._validate_server_online(key)
        except error.URLError:
            result = self._validate_server_offline(key)
        except Exception as exc:
            if self.logger:
                try:
                    self.logger.warning("License server validation failed: %s", exc)
                except Exception:
                    pass
            result = self._validate_server_offline(key)

        if not result.get("valid"):
            return False, str(result.get("message") or "License server validation failed."), self.status()

        self._store_server_activation(key, result)
        message = str(result.get("message") or f"{self._plan_name(result.get('plan'))} verified with the server.")
        return True, message, self.status()

    def activate_key(self, raw_key):
        key = self._normalize_key(raw_key)
        if not key.startswith("SOPOTEK-"):
            return False, "License key must start with SOPOTEK-.", self.status()

        if self.SERVER_KEY_PATTERN.fullmatch(key):
            return self._activate_server_key(key)

        now = self._now()
        if key.startswith("SOPOTEK-FULL-") or key.startswith("SOPOTEK-PERP-"):
            self._set("license/key", key)
            self._set("license/type", "perpetual")
            self._set("license/plan_name", "Full License")
            self._set("license/activated_at", self._iso(now))
            self._remove("license/expires_at")
            self._remove("license/server_validation_payload")
            return True, "Full license activated.", self.status()

        if key.startswith("SOPOTEK-SUB-"):
            duration = self._subscription_duration(key)
            expires_at = now + duration
            self._set("license/key", key)
            self._set("license/type", "subscription")
            self._set("license/plan_name", "Subscription")
            self._set("license/activated_at", self._iso(now))
            self._set("license/expires_at", self._iso(expires_at))
            self._remove("license/server_validation_payload")
            return True, "Subscription activated.", self.status()

        return False, "License key format was not recognized.", self.status()

    def revalidate_server_license(self):
        key = self._normalize_key(self._setting("license/key", ""))
        if str(self._setting("license/type", "") or "").strip().lower() != "server" or not key:
            return False, "No server-managed license is active on this desktop.", self.status()
        return self.activate_key(key)

    def clear_paid_license(self):
        for key in (
            "license/key",
            "license/type",
            "license/plan_name",
            "license/activated_at",
            "license/expires_at",
            "license/server_validation_payload",
        ):
            self._remove(key)
        return self.status()

    def _server_status(self):
        license_type = str(self._setting("license/type", "") or "").strip().lower()
        if license_type != "server":
            return None

        key = self._normalize_key(self._setting("license/key", ""))
        payload = self._server_payload()
        if not key or payload is None or self._normalize_key(payload.get("license_key")) != key:
            return {
                "tier": "server",
                "state": "revalidate",
                "plan_name": "Server License",
                "badge": "SERVER",
                "summary": "Server validation required",
                "description": "This desktop is configured for server-managed licensing. Verify the license online to unlock desktop entitlements.",
                "days_remaining": None,
                "expires_at": None,
                "is_premium": False,
                "features": [],
                "source": "server",
                "server_url": self.server_api_url(),
            }

        now = self._now()
        plan = str(payload.get("plan") or "free").strip().lower() or "free"
        plan_name = self._plan_name(plan)
        features = [str(item).strip().lower() for item in (payload.get("features") or []) if str(item).strip()]
        feature_set = set(features)
        expires_at = self._parse_datetime(payload.get("expires_at"))
        offline_valid_until = self._parse_datetime(payload.get("offline_valid_until"))
        validated_at = self._parse_datetime(payload.get("validated_at"))
        active_devices = payload.get("active_devices")
        max_devices = payload.get("max_devices")
        is_premium = "live_trading" in feature_set

        if expires_at is not None and expires_at <= now:
            return {
                "tier": plan,
                "state": "expired",
                "plan_name": plan_name,
                "badge": plan.upper(),
                "summary": f"{plan_name} expired",
                "description": f"The server license expired on {expires_at.date().isoformat()}. Reissue or renew it from the Sopotek platform.",
                "days_remaining": 0,
                "expires_at": expires_at,
                "is_premium": False,
                "features": features,
                "source": "server",
                "server_url": self.server_api_url(),
                "validated_at": validated_at,
                "offline_valid_until": offline_valid_until,
            }

        if offline_valid_until is not None and offline_valid_until <= now:
            return {
                "tier": plan,
                "state": "revalidate",
                "plan_name": plan_name,
                "badge": plan.upper(),
                "summary": "Server revalidation required",
                "description": "The offline grace window has expired. Reconnect to the Sopotek platform to refresh this desktop license.",
                "days_remaining": None if expires_at is None else max(0, (expires_at - now).days),
                "expires_at": expires_at,
                "is_premium": False,
                "features": features,
                "source": "server",
                "server_url": self.server_api_url(),
                "validated_at": validated_at,
                "offline_valid_until": offline_valid_until,
            }

        days_remaining = None if expires_at is None else max(0, (expires_at - now).days)
        device_summary = ""
        if isinstance(active_devices, int) and isinstance(max_devices, int):
            device_summary = f" using {active_devices}/{max_devices} devices"
        offline_summary = ""
        if offline_valid_until is not None:
            offline_summary = f" Offline grace is valid until {offline_valid_until.strftime('%Y-%m-%d %H:%M UTC')}."
        return {
            "tier": plan,
            "state": "active",
            "plan_name": plan_name,
            "badge": plan.upper(),
            "summary": f"{plan_name} active",
            "description": f"Server-verified via {self.server_api_url()}{device_summary}.{offline_summary}".strip(),
            "days_remaining": days_remaining,
            "expires_at": expires_at,
            "is_premium": is_premium,
            "features": features,
            "source": "server",
            "server_url": self.server_api_url(),
            "validated_at": validated_at,
            "offline_valid_until": offline_valid_until,
        }

    def status(self):
        self._ensure_trial_started()
        server_status = self._server_status()
        if server_status is not None:
            return server_status

        now = self._now()
        trial_started = self._parse_datetime(self._setting("license/trial_started_at", ""))
        trial_expires = trial_started + timedelta(days=self.TRIAL_DAYS) if trial_started else None
        trial_days_left = None
        if trial_expires is not None:
            trial_days_left = max(0, (trial_expires - now).days)

        license_type = str(self._setting("license/type", "") or "").strip().lower()
        plan_name = str(self._setting("license/plan_name", "") or "").strip()
        expires_at = self._parse_datetime(self._setting("license/expires_at", ""))

        if license_type == "perpetual":
            return {
                "tier": "full",
                "state": "active",
                "plan_name": plan_name or "Full License",
                "badge": "FULL",
                "summary": "Full license active",
                "description": "Perpetual license with live trading unlocked.",
                "days_remaining": None,
                "expires_at": None,
                "is_premium": True,
                "features": ["live_trading"],
                "source": "local",
            }

        if license_type == "subscription" and expires_at is not None and expires_at > now:
            days_remaining = max(0, (expires_at - now).days)
            return {
                "tier": "subscription",
                "state": "active",
                "plan_name": plan_name or "Subscription",
                "badge": "SUB",
                "summary": f"Subscription active ({days_remaining}d left)",
                "description": f"Subscription active until {expires_at.date().isoformat()}.",
                "days_remaining": days_remaining,
                "expires_at": expires_at,
                "is_premium": True,
                "features": ["live_trading"],
                "source": "local",
            }

        if trial_expires is not None and trial_expires > now:
            return {
                "tier": "trial",
                "state": "trial",
                "plan_name": "Trial",
                "badge": "TRIAL",
                "summary": f"Trial active ({trial_days_left}d left)",
                "description": f"Trial ends on {trial_expires.date().isoformat()} and includes live trading.",
                "days_remaining": trial_days_left,
                "expires_at": trial_expires,
                "is_premium": True,
                "features": ["live_trading"],
                "source": "local",
            }

        return {
            "tier": "community",
            "state": "community",
            "plan_name": "Community",
            "badge": "FREE",
            "summary": "Community mode",
            "description": "Paper trading, charts, and research remain available. Live trading requires Trial, Subscription, or a server-issued Pro or Elite license.",
            "days_remaining": 0,
            "expires_at": trial_expires,
            "is_premium": False,
            "features": [],
            "source": "local",
        }

    def allows_feature(self, feature):
        feature_name = str(feature or "").strip().lower()
        status = self.status()
        features = {str(item).strip().lower() for item in (status.get("features") or []) if str(item).strip()}
        if status.get("source") == "server":
            if str(status.get("state") or "").strip().lower() != "active":
                return feature_name not in self.SERVER_RESTRICTED_FEATURES
            if feature_name in features:
                return True
            if feature_name in self.SERVER_RESTRICTED_FEATURES:
                return False
            return True
        if feature_name in self.PREMIUM_FEATURES:
            return bool(status.get("is_premium"))
        return True

    def feature_message(self, feature):
        feature_name = str(feature or "").strip().lower().replace("_", " ")
        status = self.status()
        if self.allows_feature(feature):
            return f"{feature_name.title()} is available under {status.get('plan_name', 'the current license')}."
        if status.get("source") == "server":
            return (
                f"{feature_name.title()} is not enabled for {status.get('plan_name', 'this server license')}. "
                "Issue or upgrade the license from the Sopotek platform admin console, then revalidate this desktop."
            )
        return (
            f"{feature_name.title()} requires Trial, Subscription, or Full License. "
            "Community mode remains available for paper trading and analysis."
        )
