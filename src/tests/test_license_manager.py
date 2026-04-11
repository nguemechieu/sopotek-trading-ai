from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from licensing.license_manager import LicenseManager


class DictSettings:
    def __init__(self):
        self.data = {}

    def value(self, key, default=""):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value

    def remove(self, key):
        self.data.pop(key, None)


class FakeHttpResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_trial_starts_automatically_and_unlocks_live_trading():
    settings = DictSettings()
    manager = LicenseManager(settings)

    status = manager.status()

    assert status["tier"] == "trial"
    assert manager.allows_feature("live_trading") is True
    assert "license/trial_started_at" in settings.data


def test_subscription_key_activates_with_duration():
    settings = DictSettings()
    manager = LicenseManager(settings)

    success, message, status = manager.activate_key("SOPOTEK-SUB-12M-TEAM-001")

    assert success is True
    assert "Subscription" in message
    assert status["tier"] == "subscription"
    assert status["is_premium"] is True
    assert status["days_remaining"] is not None
    assert status["days_remaining"] > 300


def test_server_license_uses_online_validation(monkeypatch):
    settings = DictSettings()
    manager = LicenseManager(settings)
    manager.set_server_api_url("https://licenses.sopotek.inc/api/license/validate")

    payload = {
        "valid": True,
        "plan": "pro",
        "features": ["workspace", "manual_trading", "desktop_sync", "live_trading"],
        "max_devices": 3,
        "active_devices": 1,
        "offline_valid_until": (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=30)).isoformat(),
    }

    monkeypatch.setattr(
        "licensing.license_manager.request.urlopen",
        lambda req, timeout=10: FakeHttpResponse(payload),
    )

    success, message, status = manager.activate_key("SOPOTEK-ABCD-EF12-GH34")

    assert success is True
    assert "verified" in message.lower() or "license" in message.lower()
    assert status["source"] == "server"
    assert status["tier"] == "pro"
    assert status["is_premium"] is True
    assert manager.allows_feature("live_trading") is True
    assert settings.data["license/type"] == "server"


def test_server_license_falls_back_to_cached_offline_validation(monkeypatch):
    settings = DictSettings()
    manager = LicenseManager(settings)

    cached_payload = {
        "valid": True,
        "license_key": "SOPOTEK-Z9X8-C7V6-B5N4",
        "plan": "elite",
        "features": ["workspace", "manual_trading", "live_trading", "priority_support"],
        "max_devices": 10,
        "active_devices": 2,
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "offline_valid_until": (datetime.now(timezone.utc) + timedelta(hours=12)).isoformat(),
        "expires_at": (datetime.now(timezone.utc) + timedelta(days=90)).isoformat(),
    }
    settings.setValue("license/key", cached_payload["license_key"])
    settings.setValue("license/type", "server")
    settings.setValue("license/server_validation_payload", json.dumps(cached_payload))

    def _raise_url_error(req, timeout=10):
        raise error.URLError("offline")

    monkeypatch.setattr("licensing.license_manager.request.urlopen", _raise_url_error)

    success, message, status = manager.revalidate_server_license()

    assert success is True
    assert "offline" in message.lower()
    assert status["source"] == "server"
    assert status["tier"] == "elite"
    assert manager.allows_feature("live_trading") is True


def test_expired_trial_falls_back_to_community():
    settings = DictSettings()
    settings.setValue(
        "license/trial_started_at",
        (datetime.now(timezone.utc) - timedelta(days=LicenseManager.TRIAL_DAYS + 3)).isoformat(),
    )
    manager = LicenseManager(settings)

    status = manager.status()

    assert status["tier"] == "community"
    assert manager.allows_feature("live_trading") is False
