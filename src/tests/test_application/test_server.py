"""Tests for FastMCP server and health endpoints."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestServerCreation:
    """Test that the server can be created without errors."""

    def test_create_server_without_errors(self) -> None:
        """Server instance creates successfully with correct name and version."""
        import importlib
        import src.application.server as server_module

        mock_fastmcp_instance = MagicMock()
        mock_fastmcp_instance.name = "better-mnemosyne"
        mock_fastmcp_instance.version = "1.0.0"

        # Patch _FastMCP on the already-loaded module, then reload to pick it up
        server_module._FastMCP = MagicMock(return_value=mock_fastmcp_instance)
        importlib.reload(server_module)
        # Re-apply patch after reload
        server_module._FastMCP = MagicMock(return_value=mock_fastmcp_instance)

        mcp_server = server_module.create_server()

        assert mcp_server is not None
        assert mcp_server.name == "better-mnemosyne"
        assert mcp_server.version == "1.0.0"


class TestHealthEndpoint:
    """Test /health endpoint behavior."""

    @pytest.fixture
    def health_app(self) -> None:
        """Provide a Starlette app with health routes for testing."""
        from src.middleware.health import create_health_app

        return create_health_app()

    def test_health_returns_expected_json(self, health_app) -> None:
        """GET /health returns 200 with status and instances count."""
        from starlette.testclient import TestClient

        client = TestClient(health_app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "instances" in data
        assert isinstance(data["instances"], int)
        assert data["instances"] >= 0

    def test_health_returns_banks_list(self, health_app) -> None:
        """GET /health includes banks array."""
        from starlette.testclient import TestClient

        client = TestClient(health_app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "banks" in data
        assert isinstance(data["banks"], list)


class TestHealthReadyEndpoint:
    """Test /health/ready endpoint behavior."""

    @pytest.fixture(autouse=True)
    def reset_health_state(self) -> None:
        """Reset health state before each test."""
        import src.middleware.health as health_module

        health_module._default_instance_ready = False

    @pytest.fixture
    def health_app(self) -> None:
        """Provide a Starlette app with health routes for testing."""
        from src.middleware.health import create_health_app

        return create_health_app()

    def test_health_ready_returns_503_when_not_ready(self, health_app) -> None:
        """GET /health/ready returns 503 during startup (before default instance ready)."""
        from starlette.testclient import TestClient

        client = TestClient(health_app)
        response = client.get("/health/ready")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "starting"

    def test_health_ready_returns_200_when_ready(self, health_app) -> None:
        """GET /health/ready returns 200 after default instance is marked ready."""
        from starlette.testclient import TestClient
        from src.middleware.health import mark_default_instance_ready

        mark_default_instance_ready()

        client = TestClient(health_app)
        response = client.get("/health/ready")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ready"


class TestHealthLogEndpoint:
    """Test /health/log endpoint behavior."""

    @pytest.fixture
    def health_app(self) -> None:
        """Provide a Starlette app with health routes for testing."""
        from src.middleware.health import create_health_app

        return create_health_app()

    def test_health_log_returns_log_level_and_entries(self, health_app) -> None:
        """GET /health/log returns current log level and recent log entries."""
        from starlette.testclient import TestClient

        client = TestClient(health_app)
        response = client.get("/health/log")

        assert response.status_code == 200
        data = response.json()
        assert "log_level" in data
        assert isinstance(data["log_level"], str)
        assert "recent_logs" in data
        assert isinstance(data["recent_logs"], list)
