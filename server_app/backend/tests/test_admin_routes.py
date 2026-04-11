from __future__ import annotations


def _register_user(client, email: str, username: str, *, role: str = "trader") -> str:
    response = client.post(
        "/auth/register",
        json={
            "email": email,
            "username": username,
            "password": "SuperSecure123",
            "full_name": "Admin Test User",
            "role": role,
            "accept_terms": True,
        },
    )
    assert response.status_code == 201
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _current_user(client, token: str) -> dict:
    response = client.get("/auth/me", headers=_auth_headers(token))
    assert response.status_code == 200
    return response.json()


def test_admin_can_manage_user_account_controls(client) -> None:
    admin_token = _register_user(client, "admin-control@sopotek.ai", "admincontrol", role="admin")
    trader_token = _register_user(client, "desk-control@sopotek.ai", "deskcontrol")
    trader = _current_user(client, trader_token)

    response = client.patch(
        f"/api/admin/users/{trader['id']}",
        headers=_auth_headers(admin_token),
        json={
            "role": "viewer",
            "is_active": False,
            "email_verified": True,
            "clear_two_factor_secret": True,
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["role"] == "viewer"
    assert payload["is_active"] is False
    assert payload["email_verified"] is True
    assert payload["two_factor_enabled"] is False
    assert payload["current_license_plan"] == "free"
    assert payload["created_at"]
    assert payload["updated_at"]


def test_admin_can_create_admin_user(client) -> None:
    admin_token = _register_user(client, "seed-admin-create@sopotek.ai", "seedadmincreate", role="admin")

    response = client.post(
        "/api/admin/users",
        headers=_auth_headers(admin_token),
        json={
            "email": "new-admin@sopotek.ai",
            "username": "newadmin",
            "password": "SuperSecure123",
            "full_name": "New Admin",
            "role": "admin",
            "is_active": True,
            "email_verified": True,
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "new-admin@sopotek.ai"
    assert payload["role"] == "admin"
    assert payload["is_active"] is True
    assert payload["email_verified"] is True
    assert payload["current_license_plan"] == "free"


def test_admin_cannot_remove_last_active_admin(client) -> None:
    admin_token = _register_user(client, "solo-admin@sopotek.ai", "soloadmin", role="admin")
    admin = _current_user(client, admin_token)

    response = client.patch(
        f"/api/admin/users/{admin['id']}",
        headers=_auth_headers(admin_token),
        json={
            "role": "trader",
        },
    )
    assert response.status_code == 400
    assert "active admin" in response.json()["detail"].lower()


def test_non_admin_cannot_manage_users(client) -> None:
    admin_token = _register_user(client, "seed-admin-control@sopotek.ai", "seedadmincontrol", role="admin")
    trader_token = _register_user(client, "viewer-control@sopotek.ai", "viewercontrol")
    trader = _current_user(client, trader_token)
    _ = admin_token

    response = client.patch(
        f"/api/admin/users/{trader['id']}",
        headers=_auth_headers(trader_token),
        json={"email_verified": True},
    )
    assert response.status_code == 403

    create_response = client.post(
        "/api/admin/users",
        headers=_auth_headers(trader_token),
        json={
            "email": "blocked-admin@sopotek.ai",
            "username": "blockedadmin",
            "password": "SuperSecure123",
            "role": "admin",
        },
    )
    assert create_response.status_code == 403
