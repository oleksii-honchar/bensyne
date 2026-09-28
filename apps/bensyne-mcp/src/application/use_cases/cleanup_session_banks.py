"""Cleanup session banks use case.

Identifies, evaluates eligibility, and optionally deletes old agent session
banks. Banks are eligible if:
- Their name matches the session bank pattern (default: agent-session-ses_*)
- They are older than the TTL (default 30 days)
- They are not currently active in the router's instance pool
- Their directory exists on the filesystem

Three phases:
1. Identification: scan all banks, filter by pattern
2. Eligibility: check age, active status, filesystem existence
3. Execution: delete eligible banks (unless dry_run=True)
"""

from __future__ import annotations

import asyncio
import os
import re
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

from src.utils.structured_logging import get_logger

if TYPE_CHECKING:
    from src.infrastructure.bank.router import MemoryBankRouter

logger = get_logger(__name__)

# Default TTL in days
DEFAULT_TTL_DAYS = 30

# Default pattern for session banks
DEFAULT_PATTERN = "agent-session-ses_"

# Compile the regex once
_SESSION_BANK_RE = re.compile(r"^agent-sessions?-ses_[a-z0-9]+$")


def cleanup_session_banks(
    router: MemoryBankRouter,
    dry_run: bool = True,
    ttl_days: int = DEFAULT_TTL_DAYS,
    pattern: str = DEFAULT_PATTERN,
) -> dict:
    """Identify and optionally delete old agent session banks.

    Args:
        router: MemoryBankRouter to access instance pool and filesystem paths.
        dry_run: If True, only identify candidates without deleting.
        ttl_days: Age threshold in days; banks older than this are eligible.
        pattern: Prefix pattern for session banks (used for logging only;
            regex validation is pattern-independent).

    Returns:
        CleanupReport dict with counts and candidate details.
    """
    logger.info(
        "Session bank cleanup started",
        dry_run=dry_run,
        ttl_days=ttl_days,
        pattern=pattern,
    )

    now = time.time()
    ttl_seconds = ttl_days * 24 * 60 * 60

    report = {
        "dry_run": dry_run,
        "ttl_days": ttl_days,
        "banks_scanned": 0,
        "banks_matched": 0,
        "banks_eligible": 0,
        "banks_deleted": 0,
        "banks_skipped_active": 0,
        "banks_errored": 0,
        "errors": [],
        "candidates": [],
    }

    # Phase 1: Identification — scan all banks, filter by pattern
    all_banks = router.list_bank_dirs()
    report["banks_scanned"] = len(all_banks)

    matched_banks = []
    for bank_name in all_banks:
        if _SESSION_BANK_RE.match(bank_name):
            matched_banks.append(bank_name)

    report["banks_matched"] = len(matched_banks)

    if not matched_banks:
        logger.info("No session banks matched pattern; cleanup complete")
        return report

    logger.info(
        "Session banks matched pattern",
        count=len(matched_banks),
    )

    # Phase 2: Eligibility — check age, active status, filesystem
    eligible_banks = []
    for bank_name in matched_banks:
        # Check if active in pool
        if bank_name in router.instances:
            report["banks_skipped_active"] += 1
            logger.debug(
                "Bank skipped (active in pool)",
                memory_bank=bank_name,
            )
            continue

        # Check filesystem existence
        bank_path = router.get_bank_dir(bank_name)
        if not bank_path.is_dir():
            logger.debug(
                "Bank skipped (directory does not exist)",
                memory_bank=bank_name,
            )
            continue

        # Check age via directory mtime
        try:
            dir_mtime = os.path.getmtime(bank_path)
            age_seconds = now - dir_mtime
            age_days = age_seconds / 86400.0
        except OSError as e:
            report["banks_errored"] += 1
            report["errors"].append(f"Could not stat {bank_name}: {e}")
            logger.error(
                "Bank stat failed",
                memory_bank=bank_name,
                error=str(e),
            )
            continue

        if age_seconds < ttl_seconds:
            logger.debug(
                "Bank skipped (too recent)",
                memory_bank=bank_name,
                age_days=round(age_days, 1),
                ttl_days=ttl_days,
            )
            continue

        # Eligible for cleanup
        report["banks_eligible"] += 1
        eligible_banks.append((bank_name, bank_path, age_days))
        logger.debug(
            "Bank eligible for cleanup",
            memory_bank=bank_name,
            age_days=round(age_days, 1),
        )

    # Phase 3: Execution — delete eligible banks (unless dry_run)
    if dry_run:
        # Build candidate details for dry run
        for bank_name, bank_path, age_days in eligible_banks:
            report["candidates"].append({
                "name": bank_name,
                "path": str(bank_path),
                "age_days": round(age_days, 1),
            })
        logger.info(
            "Cleanup dry run complete; no banks deleted",
            eligible=len(eligible_banks),
        )
    else:
        for bank_name, bank_path, age_days in eligible_banks:
            try:
                shutil.rmtree(bank_path)
                report["banks_deleted"] += 1
                logger.info(
                    "Session bank deleted",
                    memory_bank=bank_name,
                    age_days=round(age_days, 1),
                    path=str(bank_path),
                )
            except OSError as e:
                report["banks_errored"] += 1
                report["errors"].append(f"Failed to delete {bank_name}: {e}")
                logger.error(
                    "Bank deletion failed",
                    memory_bank=bank_name,
                    error=str(e),
                )

    logger.info(
        "Session bank cleanup completed",
        scanned=report["banks_scanned"],
        matched=report["banks_matched"],
        eligible=report["banks_eligible"],
        deleted=report["banks_deleted"],
        skipped_active=report["banks_skipped_active"],
        errored=report["banks_errored"],
        dry_run=dry_run,
    )

    return report


# Also expose as async for use in async contexts
async def cleanup_session_banks_async(
    router: MemoryBankRouter,
    dry_run: bool = True,
    ttl_days: int = DEFAULT_TTL_DAYS,
    pattern: str = DEFAULT_PATTERN,
) -> dict:
    """Async wrapper around cleanup_session_banks."""
    # Use a thread pool to avoid blocking the event loop
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        None,
        cleanup_session_banks,
        router,
        dry_run,
        ttl_days,
        pattern,
    )
