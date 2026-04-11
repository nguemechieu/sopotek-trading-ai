from __future__ import annotations


def _register_user(client, email: str, username: str, *, role: str = "trader") -> str:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "SuperSecure123",
            "full_name": "License User",
            "role": role,
            "accept_terms": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _get_current_user(client, token: str) -> dict:
    response = client.get("/auth/me", headers=_auth_headers(token))
    assert response.status_code == 200
    return response.json()


def test_license_issue_and_validation_flow(client) -> None:
    access_token = _register_user(client, "license@sopotek.ai", "licensedesk")
    headers = _auth_headers(access_token)

    me_response = client.get("/api/license/me", headers=headers)
    assert me_response.status_code == 200
    assert me_response.json()["plan"] == "free"

    issue_response = client.post("/api/license/issue", headers=headers)
    assert issue_response.status_code == 201
    issued_license = issue_response.json()["license_key"]
    assert issued_license.startswith("SOPOTEK-")

    validate_response = client.post(
        "/api/license/validate",
        json={
            "license_key": issued_license,
            "device_id": "desktop-device-001",
            "app_version": "desktop-1.0.0",
        },
    )
    assert validate_response.status_code == 200
    payload = validate_response.json()
    assert payload["valid"] is True
    assert payload["plan"] == "free"
    assert payload["access_token"]
    assert payload["active_devices"] == 1


def test_free_plan_rejects_second_device(client) -> None:
    access_token = _register_user(client, "limit@sopotek.ai", "limitdesk")
    headers = _auth_headers(access_token)
    issue_response = client.post("/api/license/issue", headers=headers)
    assert issue_response.status_code == 201
    issued_license = issue_response.json()["license_key"]

    first_validation = client.post(
        "/api/license/validate",
        json={
            "license_key": issued_license,
            "device_id": "desktop-device-001",
            "app_version": "desktop-1.0.0",
        },
    )
    assert first_validation.status_code == 200
    assert first_validation.json()["valid"] is True

    second_validation = client.post(
        "/api/license/validate",
        json={
            "license_key": issued_license,
            "device_id": "desktop-device-002",
            "app_version": "desktop-1.0.0",
        },
    )
    assert second_validation.status_code == 200
    payload = second_validation.json()
    assert payload["valid"] is False
    assert payload["message"] == "Device limit exceeded"


def test_admin_can_issue_and_update_license_for_another_user(client) -> None:
    admin_token = _register_user(client, "admin-license@sopotek.ai", "adminlicense", role="admin")
    trader_token = _register_user(client, "desk@sopotek.ai", "deskuser")
    trader = _get_current_user(client, trader_token)

    overview_response = client.get("/api/license/admin/overview", headers=_auth_headers(admin_token))
    assert overview_response.status_code == 200
    overview_payload = overview_response.json()
    assert any(user["id"] == trader["id"] for user in overview_payload["users"])

    issue_response = client.post(
        "/api/license/admin/issue",
        headers=_auth_headers(admin_token),
        json={
            "user_id": trader["id"],
            "plan": "pro",
            "status": "active",
            "max_devices": 4,
        },
    )
    assert issue_response.status_code == 201
    issued_payload = issue_response.json()
    assert issued_payload["license_key"].startswith("SOPOTEK-")
    assert issued_payload["plan"] == "pro"
    assert issued_payload["max_devices"] == 4
    assert issued_payload["user_id"] == trader["id"]

    update_response = client.patch(
        f"/api/license/admin/{issued_payload['id']}",
        headers=_auth_headers(admin_token),
        json={
            "plan": "elite",
            "status": "suspended",
            "max_devices": 9,
        },
    )
    assert update_response.status_code == 200
    updated_payload = update_response.json()
    assert updated_payload["plan"] == "elite"
    assert updated_payload["status"] == "suspended"
    assert updated_payload["max_devices"] == 9


def test_non_admin_cannot_access_license_admin_routes(client) -> None:
    admin_token = _register_user(client, "seed-admin@sopotek.ai", "seedadmin", role="admin")
    trader_token = _register_user(client, "viewer-license@sopotek.ai", "viewerlicense")
    _ = admin_token

    response = client.get("/api/license/admin/overview", headers=_auth_headers(trader_token))
    assert response.status_code == 403
