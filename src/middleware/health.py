"""Health check middleware and endpoints."""

from __future__ import annotations

import logging
from collections import deque
from typing import TYPE_CHECKING, Deque, List

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

if TYPE_CHECKING:
    from src.services.bank_router import MemoryBankRouter

# ---------------------------------------------------------------------------
# Global state for health tracking
# ---------------------------------------------------------------------------

_default_instance_ready = False
_log_entries: Deque[str] = deque(maxlen=100)
_memory_bank_router: MemoryBankRouter | None = None

logger = logging.getLogger(__name__)


def mark_default_instance_ready() -> None:
    """Mark the default mnemosyne instance as initialized and ready."""
    global _default_instance_ready
    _default_instance_ready = True
    _add_log("default_instance", "Default instance marked as ready")


def set_memory_bank_router(router: MemoryBankRouter) -> None:
    """Register the memory bank router for health endpoint instance/bank info."""
    global _memory_bank_router
    _memory_bank_router = router


def _add_log(source: str, message: str) -> None:
    """Append a log entry to the in-memory buffer."""
    entry = f"[{source}] {message}"
    _log_entries.append(entry)
    logger.info(entry)


# ---------------------------------------------------------------------------
# Health route handlers
# ---------------------------------------------------------------------------

async def health_handler(request: Request) -> JSONResponse:
    """GET /health — returns overall health status with instance count."""
    instances = 0
    banks: List[str] = []

    if _memory_bank_router is not None:
        instances = _memory_bank_router.get_active_instances()
        banks = list(_memory_bank_router.get_active_banks())

    return JSONResponse(
        status_code=200,
        content={
            "status": "healthy",
            "instances": instances,
            "banks": banks,
        },
    )


async def health_ready_handler(request: Request) -> JSONResponse:
    """GET /health/ready — returns 200 when default instance ready, 503 during startup."""
    if not _default_instance_ready:
        return JSONResponse(
            status_code=503,
            content={"status": "starting"},
        )

    return JSONResponse(
        status_code=200,
        content={"status": "ready"},
    )


async def health_log_handler(request: Request) -> JSONResponse:
    """GET /health/log — returns current log level and recent log entries."""
    root_logger = logging.getLogger()
    log_level = logging.getLevelName(root_logger.getEffectiveLevel())

    return JSONResponse(
        status_code=200,
        content={
            "log_level": log_level,
            "recent_logs": list(_log_entries),
        },
    )


# ---------------------------------------------------------------------------
# Starlette app factory
# ---------------------------------------------------------------------------

def create_health_app() -> Starlette:
    """Create a Starlette app with health check routes.

    These routes are at /health, /health/ready, /health/log — matching the
    spec. They can be mounted into the main FastMCP/Starlette app.
    """
    return Starlette(
        routes=[
            Route("/health", endpoint=health_handler, methods=["GET"]),
            Route("/health/ready", endpoint=health_ready_handler, methods=["GET"]),
            Route("/health/log", endpoint=health_log_handler, methods=["GET"]),
        ],
    )
