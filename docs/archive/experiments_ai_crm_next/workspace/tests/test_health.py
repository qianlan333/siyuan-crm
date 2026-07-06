from __future__ import annotations

from conftest import make_client


def test_health_returns_ok() -> None:
    response = make_client().get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_system_health_returns_ok() -> None:
    response = make_client().get("/api/system/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True
