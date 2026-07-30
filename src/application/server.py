"""FastMCP server implementation."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

if TYPE_CHECKING:
    from src.services.namespace_router import NamespaceRouter

# FastMCP may not be installed (requires Python 3.10+); guard import
try:
    from fastmcp import FastMCP as _FastMCP

    _FASTMCP_AVAILABLE = True
except ImportError:
    _FastMCP = None  # type: ignore
    _FASTMCP_AVAILABLE = False

logger = logging.getLogger(__name__)


def _load_version() -> str:
    """Load server version from project.yaml."""
    project_yaml_path = Path(__file__).resolve().parents[2] / "project.yaml"
    if project_yaml_path.exists():
        with open(project_yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            if isinstance(data, dict) and "version" in data:
                return str(data["version"])
    return "1.0.0"


def create_server() -> FastMCP:
    """Create and configure the FastMCP server instance.

    Returns:
        FastMCP server configured with name, version, and health routes.
    """
    version = _load_version()
    mcp = _FastMCP(name="better-mnemosyne", version=version)

    # Integrate health routes using FastMCP's custom_route API
    from src.middleware.health import health_handler, health_ready_handler, health_log_handler

    mcp.custom_route("/health", methods=["GET"])(health_handler)
    mcp.custom_route("/health/ready", methods=["GET"])(health_ready_handler)
    mcp.custom_route("/health/log", methods=["GET"])(health_log_handler)

    logger.info("FastMCP server created: name=better-mnemosyne, version=%s", version)
    return mcp


def run_server(
    host: str = "0.0.0.0",
    port: int = 3000,
    namespace_router: NamespaceRouter | None = None,
) -> None:
    """Run the FastMCP server with streamable HTTP transport.

    Args:
        host: Bind address (default: 0.0.0.0)
        port: Port number (default: 3000)
        namespace_router: Optional router for health endpoint instance info
    """
    import uvicorn

    from src.middleware.health import set_namespace_router

    if namespace_router is not None:
        set_namespace_router(namespace_router)

    mcp = create_server()

    logger.info("Starting FastMCP server on %s:%d with streamable-http transport", host, port)

    # Use FastMCP's built-in run method with streamable-http transport
    mcp.run(transport="streamable-http", host=host, port=port)
