from __future__ import annotations


def test_register_and_login_flow(client) -> None:
    response = client.post(
        "/auth/register",
        json={
            "email": "trader@sopotek.ai",
            "username": "fundtrader",
            "password": "SuperSecure123",
            "full_name": "Fund Trader",
            "role": "trader",
            "accept_terms": True,
        },
    )
    assert response.status_code == 201
    register_payload = response.json()
    assert register_payload["access_token"]
    assert register_payload["refresh_token"]
    assert register_payload["user"]["role"] == "trader"
    assert register_payload["verification_required"] is True
    assert register_payload["user"]["email_verified"] is False

    login_response = client.post(
        "/auth/login",
        json={"identifier": "fundtrader", "password": "SuperSecure123", "remember_me": True},
    )
    assert login_response.status_code == 200
    login_payload = login_response.json()
    assert login_payload["user"]["email"] == "trader@sopotek.ai"
    assert login_payload["remember_me"] is True

    refresh_response = client.post(
        "/auth/refresh",
        json={"refresh_token": login_payload["refresh_token"], "remember_me": True},
    )
    assert refresh_response.status_code == 200
    refresh_payload = refresh_response.json()
    assert refresh_payload["access_token"]
    assert refresh_payload["remember_me"] is True

    verify_response = client.post(
        "/auth/verify-email",
        json={"token": register_payload["email_verification_token"]},
    )
    assert verify_response.status_code == 200
    verify_payload = verify_response.json()
    assert verify_payload["user"]["email_verified"] is True


def test_register_requires_terms(client) -> None:
    response = client.post(
        "/auth/register",
        json={
            "email": "no-terms@sopotek.ai",
            "username": "noterms",
            "password": "SuperSecure123",
            "full_name": "No Terms",
            "role": "trader",
            "accept_terms": False,
        },
    )
    assert response.status_code == 400
    assert "accept the terms" in response.json()["detail"].lower()


def test_public_register_cannot_create_followup_admin(client) -> None:
    first_response = client.post(
        "/auth/register",
        json={
            "email": "first-admin@sopotek.ai",
            "username": "firstadmin",
            "password": "SuperSecure123",
            "full_name": "First Admin",
            "role": "admin",
            "accept_terms": True,
        },
    )
    assert first_response.status_code == 201
    assert first_response.json()["user"]["role"] == "admin"

    second_response = client.post(
        "/auth/register",
        json={
            "email": "second-admin@sopotek.ai",
            "username": "secondadmin",
            "password": "SuperSecure123",
            "full_name": "Second Admin",
            "role": "admin",
            "accept_terms": True,
        },
    )
    assert second_response.status_code == 403
    assert "admin control center" in second_response.json()["detail"].lower()


def test_forgot_and_reset_password_flow(client) -> None:
    register_response = client.post(
        "/auth/register",
        json={
            "email": "reset@sopotek.ai",
            "username": "resetdesk",
            "password": "SuperSecure123",
            "full_name": "Reset Desk",
            "role": "trader",
            "accept_terms": True,
        },
    )
    assert register_response.status_code == 201

    forgot_response = client.post("/auth/forgot-password", json={"email": "reset@sopotek.ai"})
    assert forgot_response.status_code == 200
    forgot_payload = forgot_response.json()
    assert forgot_payload["message"]
    assert forgot_payload["reset_token"]
    assert forgot_payload["reset_url"]

    reset_response = client.post(
        "/auth/reset-password",
        json={"token": forgot_payload["reset_token"], "password": "NewSecure456"},
    )
    assert reset_response.status_code == 200
    reset_payload = reset_response.json()
    assert reset_payload["access_token"]
    assert reset_payload["user"]["email"] == "reset@sopotek.ai"

    login_response = client.post(
        "/auth/login",
        json={"email": "reset@sopotek.ai", "password": "NewSecure456"},
    )
    assert login_response.status_code == 200
