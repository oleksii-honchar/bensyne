"""E2E test fixtures.

Starts the Bensyne server in a subprocess, waits for readiness,
and provides an HTTP client for sending MCP requests via streamable HTTP transport.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

import httpx
import pytest

# Project root is two levels up from this file: src/tests/e2e/conftest.py -> project_root
PROJECT_ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def server_url() -> str:
    """Return the server URL for e2e tests."""
    return "http://127.0.0.1:3001"


@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory) -> Path:
    """Create isolated test data directory."""
    data_dir = tmp_path_factory.mktemp("mnemosyne-e2e-data")
    yield data_dir
    shutil.rmtree(data_dir, ignore_errors=True)


@pytest.fixture(scope="session")
def server_process(test_data_dir: Path, server_url: str) -> subprocess.Popen:
    """Start server subprocess for e2e tests."""
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(PROJECT_ROOT / "src")
    env["PYTHONUNBUFFERED"] = "1"

    process = subprocess.Popen(
        [
            sys.executable,
            str(PROJECT_ROOT / "main.py"),
            "--port",
            "3001",
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


@pytest.fixture(scope="session")
def mcp_client(server_process: subprocess.Popen, server_url: str) -> httpx.Client:
    """HTTP client for sending MCP requests via streamable HTTP transport.

    Uses JSON-RPC compatible headers required by FastMCP streamable-http.
    """
    client = httpx.Client(
        base_url=server_url,
        timeout=10.0,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
    )
    yield client
