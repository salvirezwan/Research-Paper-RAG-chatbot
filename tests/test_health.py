"""Tests for GET /api/v1/health"""
from unittest.mock import AsyncMock, patch


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        with patch(
            "backend.routes.health.check_mongodb_health",
            new=AsyncMock(return_value=True),
        ):
            resp = client.get("/api/v1/health")
        assert resp.status_code == 200

    def test_health_response_structure(self, client):
        with patch(
            "backend.routes.health.check_mongodb_health",
            new=AsyncMock(return_value=True),
        ):
            resp = client.get("/api/v1/health")
        body = resp.json()
        assert "status" in body
        assert "mongodb" in body
        assert "app" in body

    def test_mongodb_connected(self, client):
        with patch(
            "backend.routes.health.check_mongodb_health",
            new=AsyncMock(return_value=True),
        ):
            resp = client.get("/api/v1/health")
        assert resp.json()["mongodb"] == "connected"

    def test_mongodb_disconnected(self, client):
        with patch(
            "backend.routes.health.check_mongodb_health",
            new=AsyncMock(return_value=False),
        ):
            resp = client.get("/api/v1/health")
        assert resp.json()["mongodb"] == "disconnected"

    def test_status_is_ok(self, client):
        with patch(
            "backend.routes.health.check_mongodb_health",
            new=AsyncMock(return_value=True),
        ):
            resp = client.get("/api/v1/health")
        assert resp.json()["status"] == "ok"

    def test_root_endpoint(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "running" in resp.json().get("message", "").lower()
