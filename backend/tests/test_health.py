from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app import main


@pytest.fixture
def client():
    return TestClient(main.app)


def test_liveness_is_independent_of_database(client):
    response = client.get("/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": "backend"}


def test_readiness_is_200_when_database_is_available(monkeypatch, client):
    async def available(_settings):
        return True, None

    monkeypatch.setattr(main, "database_is_available", available)
    response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "available"}


def test_readiness_is_safe_503_when_database_is_down(monkeypatch, client):
    async def unavailable(_settings):
        return False, "OperationalError"

    monkeypatch.setattr(main, "database_is_available", unavailable)
    response = client.get("/health/ready")

    assert response.status_code == 503
    body = response.json()
    assert body["error"]["code"] == "DB_UNAVAILABLE"
    assert "OperationalError" not in response.text
    assert "postgres" not in response.text

