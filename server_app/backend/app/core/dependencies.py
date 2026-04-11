from __future__ import annotations

from fastapi import Request


def get_settings(request: Request):
    return request.app.state.settings


def get_state_store(request: Request):
    return request.app.state.platform_state


def get_kafka_gateway(request: Request):
    return request.app.state.kafka_gateway


def get_control_service(request: Request):
    return request.app.state.control_service


def get_auth_rate_limiter(request: Request):
    return request.app.state.auth_rate_limiter


def get_license_rate_limiter(request: Request):
    return request.app.state.license_rate_limiter


def get_license_service(request: Request):
    return request.app.state.license_service


def get_stripe_service(request: Request):
    return request.app.state.stripe_service


def get_terminal_service(request: Request):
    return request.app.state.terminal_service


def get_runtime_service(request: Request):
    return request.app.state.runtime_service
