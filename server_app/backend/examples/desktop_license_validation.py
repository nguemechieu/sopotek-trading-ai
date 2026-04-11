from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib import error, request


API_URL = "http://127.0.0.1:8000/api/license/validate"
CACHE_PATH = Path.home() / ".sopotek_trading_ai_license.json"
OFFLINE_GRACE = timedelta(hours=24)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def device_id() -> str:
    host = uuid.getnode()
    return f"desktop-{host:012x}"


def load_cache() -> dict | None:
    if not CACHE_PATH.exists():
        return None
    try:
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def save_cache(payload: dict) -> None:
    payload = dict(payload)
    payload["validated_at"] = utc_now().isoformat()
    CACHE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def validate_online(license_key: str, app_version: str) -> dict:
    body = json.dumps(
        {
            "license_key": license_key,
            "device_id": device_id(),
            "app_version": app_version,
        }
    ).encode("utf-8")
    req = request.Request(API_URL, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def validate_offline(cache: dict | None) -> dict:
    if not cache or not cache.get("valid"):
        return {"valid": False, "message": "No cached license validation available"}
    validated_at = str(cache.get("validated_at") or "").strip()
    if not validated_at:
        return {"valid": False, "message": "Cached license is missing a validation timestamp"}
    cached_time = datetime.fromisoformat(validated_at)
    if cached_time.tzinfo is None:
        cached_time = cached_time.replace(tzinfo=timezone.utc)
    if utc_now() - cached_time > OFFLINE_GRACE:
        return {"valid": False, "message": "Offline grace period exceeded"}
    cache["message"] = "Offline mode enabled from cached validation"
    return cache


def main() -> int:
    license_key = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    app_version = (sys.argv[2] if len(sys.argv) > 2 else "desktop-1.0.0").strip()
    if not license_key:
        print("Usage: python desktop_license_validation.py <LICENSE_KEY> [APP_VERSION]")
        return 1

    cache = load_cache()
    try:
        result = validate_online(license_key, app_version)
        if result.get("valid"):
            save_cache(result)
        print(json.dumps(result, indent=2))
        return 0 if result.get("valid") else 2
    except error.URLError:
        offline = validate_offline(cache)
        print(json.dumps(offline, indent=2))
        return 0 if offline.get("valid") else 3


if __name__ == "__main__":
    raise SystemExit(main())
