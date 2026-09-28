"""Integration tests for the /api/v1/banks/cleanup admin endpoint.

Starts a real Bensyne server in a subprocess, sends HTTP requests to the
cleanup endpoint, and validates the responses.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

# Project root is two levels up from this file
PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="module")
def server_url() -> str:
    """Return the server URL for admin endpoint tests."""
    return "http://127.0.0.1:3011"


@pytest.fixture(scope="module")
def test_data_dir(tmp_path_factory) -> Path:
    """Create isolated test data directory."""
    data_dir = tmp_path_factory.mktemp("admin-endpoint-test-data")
    yield data_dir
    shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture(scope="module")
def server_process(test_data_dir: Path, server_url: str) -> subprocess.Popen:
    """Start server subprocess for admin endpoint tests."""
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(
        [
            sys.executable,
            str(PROJECT_ROOT / "main.py"),
            "--port",
            "3011",
            "--data-dir",
            str(test_data_dir),
            "--log-level",
            "DEBUG",
        ],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    # Wait for server to be ready
    client = httpx.Client(timeout=5.0)
    for _ in range(60):
        try:
            resp = client.get(f"{server_url}/health")
            if resp.status_code == 200:
                break
        except (httpx.ConnectError, httpx.ReadTimeout):
            time.sleep(0.5)
    else:
        process.kill()
        stdout, stderr = process.communicate()
        raise RuntimeError(
            f"Server failed to start within 30s.\n" f"stdout: {stdout.decode()}\nstderr: {stderr.decode()}"
        )

    yield process

    # Cleanup
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


@pytest.fixture(scope="module")
def client(server_process: subprocess.Popen, server_url: str) -> httpx.Client:
    """HTTP client for admin endpoint tests."""
    return httpx.Client(base_url=server_url, timeout=10.0)


class TestCleanupEndpoint:
    """Tests for POST /api/v1/banks/cleanup."""

    def test_endpoint_exists(self, client: httpx.Client) -> None:
        """Verify the endpoint accepts POST requests and returns 200."""
        resp = client.post("/api/v1/banks/cleanup")
        assert resp.status_code == 200

    def test_defaults_returned(self, client: httpx.Client) -> None:
        """Verify the default parameters are used when body is empty."""
        resp = client.post("/api/v1/banks/cleanup")
        assert resp.status_code == 200
        data = resp.json()

        # Defaults: dry_run=true, ttl_days=30
        assert data["dry_run"] is True
        assert data["ttl_days"] == 30

        # Required report fields
        assert "banks_scanned" in data
        assert "banks_matched" in data
        assert "banks_eligible" in data
        assert "banks_deleted" in data
        assert "banks_skipped_active" in data
        assert "banks_errored" in data
        assert "errors" in data
        assert "candidates" in data

    def test_custom_ttl_and_dry_run(self, client: httpx.Client) -> None:
        """Verify custom parameters are accepted and reflected in the response."""
        body = {"dry_run": False, "ttl_days": 7}
        resp = client.post("/api/v1/banks/cleanup", json=body)
        assert resp.status_code == 200
        data = resp.json()
        assert data["dry_run"] is False
        assert data["ttl_days"] == 7

    def test_invalid_ttl_returns_400(self, client: httpx.Client) -> None:
        """Verify invalid ttl_days returns 400."""
        body = {"ttl_days": 0}
        resp = client.post("/api/v1/banks/cleanup", json=body)
        assert resp.status_code == 400
        data = resp.json()
        assert "error" in data

    def test_custom_pattern(self, client: httpx.Client) -> None:
        """Verify custom pattern parameter is accepted."""
        body = {"pattern": "my-custom-prefix"}
        resp = client.post("/api/v1/banks/cleanup", json=body)
        assert resp.status_code == 200
        data = resp.json()
        # With a non-matching pattern, no banks should be matched
        assert data["banks_matched"] == 0