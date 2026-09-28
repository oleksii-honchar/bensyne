"""Unit tests for cleanup_session_banks use case.

Tests all three phases: identification (pattern matching), eligibility (age,
active status, filesystem), and execution (dry run vs actual deletion).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import pytest

from src.application.use_cases.cleanup_session_banks import cleanup_session_banks
from src.utils.structured_logging import LoggerMock

if TYPE_CHECKING:
    from src.infrastructure.bank.router import MemoryBankRouter


def make_router(banks: list[str] | None = None) -> MagicMock:
    """Create a mock router with configured list_bank_dirs and instances."""
    router = MagicMock(spec=["list_bank_dirs", "get_bank_dir", "instances"])
    router.instances = {}
    router.list_bank_dirs.return_value = banks or []
    return router


def test_cleanup_no_banks():
    """Test cleanup when no banks exist."""
    router = make_router(banks=[])
    report = cleanup_session_banks(router, dry_run=True)

    assert report["banks_scanned"] == 0
    assert report["banks_matched"] == 0
    assert report["banks_eligible"] == 0
    assert report["banks_deleted"] == 0
    assert report["dry_run"] is True


def test_cleanup_pattern_matching():
    """Test that only session banks matching the regex are identified."""
    router = make_router(banks=[
        "agent-session-ses_abc123",
        "agent-sessions-ses_xyz789",
        "agent-session_ses_test",  # missing separator
        "default",
        "user-bank",
        "agent-session-ses_ABC",   # uppercase
        "agent-session-ses_",      # empty id
    ])
    report = cleanup_session_banks(router, dry_run=True)

    # agent-session-ses_abc123 ✓
    # agent-sessions-ses_xyz789 ✓ (optional -s)
    # Others don't match
    assert report["banks_matched"] == 2


def test_cleanup_active_banks_skipped():
    """Test that banks in the instance pool are not eligible."""
    router = make_router(banks=["agent-session-ses_active123"])
    router.instances = {"agent-session-ses_active123": MagicMock()}

    report = cleanup_session_banks(router, dry_run=True)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 0
    assert report["banks_skipped_active"] == 1


def test_cleanup_young_banks_skipped():
    """Test that banks younger than TTL are not eligible."""
    router = make_router(banks=["agent-session-ses_young123"])
    bank_dir = Path("/tmp/fake-bank-young")
    bank_dir.mkdir(exist_ok=True)
    router.get_bank_dir.return_value = bank_dir

    report = cleanup_session_banks(router, dry_run=True, ttl_days=30)

    # Bank is new (just created), so age < 30 days
    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 0

    bank_dir.rmdir()


def test_cleanup_old_banks_eligible_dry_run():
    """Test that old banks are identified as eligible in dry run."""
    router = make_router(banks=["agent-session-ses_old123"])
    bank_dir = Path("/tmp/fake-bank-old")
    bank_dir.mkdir(exist_ok=True)
    router.get_bank_dir.return_value = bank_dir

    # Fake age: set mtime to 60 days ago
    old_time = time.time() - (60 * 24 * 60 * 60)
    os.utime(bank_dir, (old_time, old_time))

    report = cleanup_session_banks(router, dry_run=True, ttl_days=30)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 1
    assert report["banks_deleted"] == 0
    assert report["dry_run"] is True
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["name"] == "agent-session-ses_old123"
    assert report["candidates"][0]["age_days"] >= 59.0

    # Bank directory should still exist (dry run)
    assert bank_dir.is_dir()
    bank_dir.rmdir()


def test_cleanup_old_banks_deleted():
    """Test that old banks are deleted when not in dry run."""
    router = make_router(banks=["agent-session-ses_del123"])
    bank_dir = Path("/tmp/fake-bank-del")
    bank_dir.mkdir(exist_ok=True)
    (bank_dir / "some_file.txt").write_text("test")
    router.get_bank_dir.return_value = bank_dir

    # Fake age: set mtime to 60 days ago
    old_time = time.time() - (60 * 24 * 60 * 60)
    os.utime(bank_dir, (old_time, old_time))

    report = cleanup_session_banks(router, dry_run=False, ttl_days=30)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 1
    assert report["banks_deleted"] == 1
    assert report["dry_run"] is False

    # Bank directory should be gone
    assert not bank_dir.is_dir()


def test_cleanup_multiple_banks_mixed():
    """Test cleanup with a mix of session banks and other banks."""
    router = make_router(banks=[
        "default",
        "agent-session-ses_old123",
        "agent-session-ses_old456",
        "user-custom-bank",
    ])

    old_dir = Path("/tmp/fake-bank-old")
    old_dir.mkdir(exist_ok=True)
    router.get_bank_dir.return_value = old_dir

    # Set all to old
    old_time = time.time() - (60 * 24 * 60 * 60)
    os.utime(old_dir, (old_time, old_time))

    report = cleanup_session_banks(router, dry_run=True, ttl_days=30)

    assert report["banks_scanned"] == 4
    assert report["banks_matched"] == 2
    assert report["banks_eligible"] == 2

    old_dir.rmdir()


def test_cleanup_bank_stat_error():
    """Test error handling when stat fails on a bank directory."""
    router = make_router(banks=["agent-session-ses_err123"])
    bank_dir = Path("/tmp/fake-bank-stat-err")
    bank_dir.mkdir(exist_ok=True)
    router.get_bank_dir.return_value = bank_dir

    with patch("os.path.getmtime", side_effect=OSError("stat failed")):
        report = cleanup_session_banks(router, dry_run=True)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 0
    assert report["banks_errored"] == 1
    assert len(report["errors"]) == 1
    assert "stat failed" in report["errors"][0]
    bank_dir.rmdir()


def test_cleanup_deletion_error_isolation():
    """Test that one bank deletion failure doesn't stop the sweep."""
    router = make_router(banks=["agent-session-ses_fail123", "agent-session-ses_ok456"])

    fail_dir = Path("/tmp/fake-bank-fail")
    ok_dir = Path("/tmp/fake-bank-ok")
    fail_dir.mkdir(exist_ok=True)
    ok_dir.mkdir(exist_ok=True)

    # Route to different dirs
    router.get_bank_dir.side_effect = [
        fail_dir,
        fail_dir,  # For fail123 eligibility check
        ok_dir,
        ok_dir,    # For ok456 eligibility check
    ]

    old_time = time.time() - (60 * 24 * 60 * 60)
    os.utime(fail_dir, (old_time, old_time))
    os.utime(ok_dir, (old_time, old_time))

    with patch("shutil.rmtree", side_effect=[OSError("rmtree failed"), None]):
        report = cleanup_session_banks(router, dry_run=False, ttl_days=30)

    assert report["banks_matched"] == 2
    assert report["banks_eligible"] == 2
    assert report["banks_deleted"] == 1
    assert report["banks_errored"] == 1
    assert "rmtree failed" in report["errors"][0]

    # Clean up
    try:
        fail_dir.rmdir()
    except FileNotFoundError:
        pass
    try:
        ok_dir.rmdir()
    except FileNotFoundError:
        pass


def test_cleanup_bank_not_in_filesystem():
    """Test that banks not on filesystem are skipped."""
    router = make_router(banks=["agent-session-ses_missing"])
    missing_dir = Path("/tmp/fake-bank-missing")
    # Don't create the directory
    router.get_bank_dir.return_value = missing_dir

    report = cleanup_session_banks(router, dry_run=True)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 0


def test_cleanup_custom_ttl():
    """Test custom TTL threshold."""
    router = make_router(banks=["agent-session-ses_ttl123"])
    bank_dir = Path("/tmp/fake-bank-ttl")
    bank_dir.mkdir(exist_ok=True)
    router.get_bank_dir.return_value = bank_dir

    # Set age to 10 days
    old_time = time.time() - (10 * 24 * 60 * 60)
    os.utime(bank_dir, (old_time, old_time))

    # TTL of 5 days: bank is older than 5 days -> eligible
    report = cleanup_session_banks(router, dry_run=True, ttl_days=5)
    assert report["banks_eligible"] == 1

    # TTL of 30 days: bank is younger than 30 days -> not eligible
    report = cleanup_session_banks(router, dry_run=True, ttl_days=30)
    assert report["banks_eligible"] == 0

    bank_dir.rmdir()


def test_cleanup_candidate_details_dry_run():
    """Test that dry run reports include candidate details."""
    router = make_router(banks=["agent-session-ses_det123"])
    bank_dir = Path("/tmp/fake-bank-det")
    bank_dir.mkdir(exist_ok=True)
    router.get_bank_dir.return_value = bank_dir

    old_time = time.time() - (45 * 24 * 60 * 60)
    os.utime(bank_dir, (old_time, old_time))

    report = cleanup_session_banks(router, dry_run=True, ttl_days=30)

    assert len(report["candidates"]) == 1
    candidate = report["candidates"][0]
    assert candidate["name"] == "agent-session-ses_det123"
    assert candidate["path"] == str(bank_dir)
    assert candidate["age_days"] >= 44.0

    bank_dir.rmdir()
