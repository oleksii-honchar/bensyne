"""Admin endpoints for session bank management."""

from __future__ import annotations

import logging
import json
from typing import TYPE_CHECKING

from starlette.requests import Request
from starlette.responses import JSONResponse

from src.application.use_cases.cleanup_session_banks import cleanup_session_banks_async

if TYPE_CHECKING:
    from src.infrastructure.bank.router import MemoryBankRouter

logger = logging.getLogger(__name__)

# Global reference to the router, set at startup
_admin_router: MemoryBankRouter | None = None


def set_admin_router(router: MemoryBankRouter) -> None:
    """Register the memory bank router for admin endpoints."""
    global _admin_router
    _admin_router = router


async def cleanup_session_banks_endpoint(request: Request) -> JSONResponse:
    """POST /api/v1/banks/cleanup — identify and optionally delete old session banks.

    Request body (all optional):
        {
            "dry_run": true,
            "ttl_days": 30,
            "pattern": "agent-session-ses_"
        }

    Returns 200 with cleanup report.
    """
    logger.info("Cleanup endpoint called")

    if _admin_router is None:
        return JSONResponse(
            status_code=500,
            content={"error": "Admin router not initialized"},
        )

    # Parse request body with defaults
    dry_run = True
    ttl_days = 30
    pattern = "agent-session-ses_"

    try:
        body = await request.json()
        if isinstance(body, dict):
            if "dry_run" in body:
                dry_run = bool(body["dry_run"])
            if "ttl_days" in body:
                ttl_days = int(body["ttl_days"])
                if ttl_days < 1:
                    raise ValueError("ttl_days must be >= 1")
            if "pattern" in body:
                pattern = str(body["pattern"])
    except json.JSONDecodeError:
        # Empty body or invalid JSON is OK — use defaults
        pass
    except ValueError as e:
        return JSONResponse(
            status_code=400,
            content={"error": str(e)},
        )
    except Exception as e:
        logger.error("Error parsing cleanup request body", error=str(e))
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid request body: {e}"},
        )

    try:
        report = await cleanup_session_banks_async(
            router=_admin_router,
            dry_run=dry_run,
            ttl_days=ttl_days,
            pattern=pattern,
        )
        return JSONResponse(status_code=200, content=report)
    except Exception as e:
        logger.error("Cleanup endpoint failed", error=str(e), exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error": f"Cleanup failed: {e}"},
        )