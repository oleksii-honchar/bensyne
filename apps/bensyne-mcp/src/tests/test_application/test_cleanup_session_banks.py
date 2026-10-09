"""Unit tests for cleanup_session_banks use case.

Tests all three phases: identification (pattern matching), eligibility (age
resolution chain — ``.bank_created`` marker → birth time → unknown — plus
active status and filesystem checks), and execution (dry run vs actual deletion).

Age fixtures use real ``.bank_created`` marker files in ``tmp_path`` dirs
(DEC-A2); the birth-time fallback is driven via monkeypatched ``get_birth_time``
because the dev host (macOS) has no statx(2).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

from src.application.use_cases.cleanup_session_banks import cleanup_session_banks
from src.infrastructure.bank.router import BANK_CREATED_MARKER


def make_router(banks: list[str] | None = None) -> MagicMock:
    """Create a mock router with configured list_bank_dirs and instances."""
    router = MagicMock(spec=["list_bank_dirs", "get_bank_dir", "instances"])
    router.instances = {}
    router.list_bank_dirs.return_value = banks or []
    return router


def make_bank_dir(tmp_path: Path, name: str) -> Path:
    """Create a bank directory under tmp_path."""
    bank_dir = tmp_path / name
    bank_dir.mkdir()
    return bank_dir


def write_marker(
    bank_dir: Path,
    *,
    age_days: float | None = None,
    content: str | None = None,
) -> Path:
    """Write a ``.bank_created`` marker into bank_dir.

    Exactly one of age_days (ISO-8601 UTC timestamp that many days old, same
    format the router writes) or content (raw marker bytes, e.g. corrupt data).
    """
    marker = bank_dir / BANK_CREATED_MARKER
    if content is not None:
        marker.write_text(content, encoding="utf-8")
    else:
        assert age_days is not None
        created = datetime.now(timezone.utc) - timedelta(days=age_days)
        marker.write_text(created.isoformat() + "\n", encoding="utf-8")
    return marker


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
    """Only banks with a mandatory ``ses_`` segment are identified as session banks.

    Real OpenCode session IDs are mixed-case base62 and on-disk names use both
    hyphen and underscore separators (DEC-A1), so those variants MUST match.
    Names without a ``ses_`` segment (user/persona/default banks) and empty IDs
    MUST NOT match.
    """
    must_match = [
        "agent-session-ses_abc123",
        "agent-sessions-ses_xyz789",
        "agent-session-ses_ABC",   # uppercase — real IDs are mixed-case base62
        "agent-session-ses_ee35956e4ffeWKu8JTvmReHF0X",  # real production ID
        "agent-sessions_ses_x",    # underscore separator variant
        "agent-session_ses_test",  # underscore variant, singular form
    ]
    must_not_match = [
        "agent-sessions_oleksii",  # user-scoped recall bank — no ses_ segment
        "user_oleksii",
        "default",
        "agent-persona_architect",
        "agent-session-ses_",      # empty id — anchored + must reject
        "session-ses_x",           # out-of-scope one-off
        "ses_x",                   # bare ses_ — out of scope
    ]

    for bank_name in must_match:
        router = make_router(banks=[bank_name])
        report = cleanup_session_banks(router, dry_run=True)
        assert report["banks_matched"] == 1, f"expected to match: {bank_name}"

    for bank_name in must_not_match:
        router = make_router(banks=[bank_name])
        report = cleanup_session_banks(router, dry_run=True)
        assert report["banks_matched"] == 0, f"expected NOT to match: {bank_name}"


def test_cleanup_active_banks_skipped():
    """Test that banks in the instance pool are not eligible."""
    router = make_router(banks=["agent-session-ses_active123"])
    router.instances = {"agent-session-ses_active123": MagicMock()}

    report = cleanup_session_banks(router, dry_run=True)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 0
    assert report["banks_skipped_active"] == 1


def test_cleanup_young_banks_skipped(tmp_path):
    """A bank with a recent marker is younger than TTL and not eligible."""
    bank_name = "agent-session-ses_young123"
    router = make_router(banks=[bank_name])
    bank_dir = make_bank_dir(tmp_path, bank_name)
    write_marker(bank_dir, age_days=1)
    router.get_bank_dir.return_value = bank_dir

    report = cleanup_session_banks(router, dry_run=True, ttl_days=30)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 0
    assert report["banks_skipped_unknown_age"] == 0


def test_cleanup_old_banks_eligible_dry_run(tmp_path):
    """An old marker makes the bank eligible; age comes from the marker."""
    bank_name = "agent-session-ses_old123"
    router = make_router(banks=[bank_name])
    bank_dir = make_bank_dir(tmp_path, bank_name)
    # Directory mtime is NOW (tmp_path); only the marker says 60 days old.
    write_marker(bank_dir, age_days=60)
    router.get_bank_dir.return_value = bank_dir

    report = cleanup_session_banks(router, dry_run=True, ttl_days=30)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 1
    assert report["banks_deleted"] == 0
    assert report["dry_run"] is True
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["name"] == bank_name
    assert report["candidates"][0]["age_days"] >= 59.0
    assert report["candidates"][0]["age_source"] == "marker"

    # Bank directory should still exist (dry run)
    assert bank_dir.is_dir()


def test_cleanup_old_banks_deleted(tmp_path):
    """An old marker makes the bank eligible and it is deleted when not dry run."""
    bank_name = "agent-session-ses_del123"
    router = make_router(banks=[bank_name])
    bank_dir = make_bank_dir(tmp_path, bank_name)
    (bank_dir / "some_file.txt").write_text("test")
    write_marker(bank_dir, age_days=60)
    router.get_bank_dir.return_value = bank_dir

    report = cleanup_session_banks(router, dry_run=False, ttl_days=30)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 1
    assert report["banks_deleted"] == 1
    assert report["dry_run"] is False

    # Bank directory should be gone
    assert not bank_dir.is_dir()


def test_cleanup_multiple_banks_mixed(tmp_path):
    """Test cleanup with a mix of session banks and other banks."""
    old_a = "agent-session-ses_old123"
    old_b = "agent-session-ses_old456"
    router = make_router(banks=[
        "default",
        old_a,
        old_b,
        "user-custom-bank",
    ])

    dir_a = make_bank_dir(tmp_path, old_a)
    dir_b = make_bank_dir(tmp_path, old_b)
    write_marker(dir_a, age_days=60)
    write_marker(dir_b, age_days=60)
    dirs = {old_a: dir_a, old_b: dir_b}
    router.get_bank_dir.side_effect = lambda name: dirs[name]

    report = cleanup_session_banks(router, dry_run=True, ttl_days=30)

    assert report["banks_scanned"] == 4
    assert report["banks_matched"] == 2
    assert report["banks_eligible"] == 2


def test_cleanup_bank_stat_error(tmp_path):
    """Birth-time statx failure is reported as an error, not a crash.

    Re-targeted from the removed os.path.getmtime patch (DEC-A2): with no
    marker present the chain falls through to get_birth_time; an OSError there
    must land in banks_errored/errors.
    """
    bank_name = "agent-session-ses_err123"
    router = make_router(banks=[bank_name])
    bank_dir = make_bank_dir(tmp_path, bank_name)  # no marker
    router.get_bank_dir.return_value = bank_dir

    with patch(
        "src.application.use_cases.cleanup_session_banks.get_birth_time",
        side_effect=OSError("stat failed"),
    ):
        report = cleanup_session_banks(router, dry_run=True)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 0
    assert report["banks_errored"] == 1
    assert len(report["errors"]) == 1
    assert "stat failed" in report["errors"][0]


def test_cleanup_deletion_error_isolation(tmp_path):
    """Test that one bank deletion failure doesn't stop the sweep."""
    fail_name = "agent-session-ses_fail123"
    ok_name = "agent-session-ses_ok456"
    router = make_router(banks=[fail_name, ok_name])

    fail_dir = make_bank_dir(tmp_path, fail_name)
    ok_dir = make_bank_dir(tmp_path, ok_name)
    write_marker(fail_dir, age_days=60)
    write_marker(ok_dir, age_days=60)

    dirs = {fail_name: fail_dir, ok_name: ok_dir}
    router.get_bank_dir.side_effect = lambda name: dirs[name]

    with patch("shutil.rmtree", side_effect=[OSError("rmtree failed"), None]):
        report = cleanup_session_banks(router, dry_run=False, ttl_days=30)

    assert report["banks_matched"] == 2
    assert report["banks_eligible"] == 2
    assert report["banks_deleted"] == 1
    assert report["banks_errored"] == 1
    assert "rmtree failed" in report["errors"][0]


def test_cleanup_bank_not_in_filesystem():
    """Test that banks not on filesystem are skipped."""
    router = make_router(banks=["agent-session-ses_missing"])
    missing_dir = Path("/tmp/fake-bank-missing")
    # Don't create the directory
    router.get_bank_dir.return_value = missing_dir

    report = cleanup_session_banks(router, dry_run=True)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 0


def test_cleanup_custom_ttl(tmp_path):
    """Test custom TTL threshold against marker-derived age."""
    bank_name = "agent-session-ses_ttl123"
    router = make_router(banks=[bank_name])
    bank_dir = make_bank_dir(tmp_path, bank_name)
    write_marker(bank_dir, age_days=10)
    router.get_bank_dir.return_value = bank_dir

    # Marker age 10 days: TTL of 5 days -> eligible
    report = cleanup_session_banks(router, dry_run=True, ttl_days=5)
    assert report["banks_eligible"] == 1

    # Marker age 10 days: TTL of 30 days -> not eligible
    report = cleanup_session_banks(router, dry_run=True, ttl_days=30)
    assert report["banks_eligible"] == 0


def test_cleanup_candidate_details_dry_run(tmp_path):
    """Dry-run candidates carry name, path, marker-derived age and age_source."""
    bank_name = "agent-session-ses_det123"
    router = make_router(banks=[bank_name])
    bank_dir = make_bank_dir(tmp_path, bank_name)
    write_marker(bank_dir, age_days=45)
    router.get_bank_dir.return_value = bank_dir

    report = cleanup_session_banks(router, dry_run=True, ttl_days=30)

    assert len(report["candidates"]) == 1
    candidate = report["candidates"][0]
    assert candidate["name"] == bank_name
    assert candidate["path"] == str(bank_dir)
    assert candidate["age_days"] >= 44.0
    assert candidate["age_source"] == "marker"


def test_cleanup_unknown_age_never_deleted(tmp_path, monkeypatch):
    """No marker + no birth time -> unknown age: never eligible, never deleted."""
    bank_name = "agent-session-ses_unknown1"
    router = make_router(banks=[bank_name])
    bank_dir = make_bank_dir(tmp_path, bank_name)  # no marker
    router.get_bank_dir.return_value = bank_dir
    monkeypatch.setattr(
        "src.application.use_cases.cleanup_session_banks.get_birth_time",
        lambda path: None,
    )

    # Even with dry_run=False an unknown-age bank must never be deleted.
    report = cleanup_session_banks(router, dry_run=False, ttl_days=30)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 0
    assert report["banks_deleted"] == 0
    assert report["banks_skipped_unknown_age"] == 1
    assert report["candidates"] == []
    assert bank_dir.is_dir()


def test_cleanup_unknown_age_reported_in_dry_run(tmp_path, monkeypatch):
    """Unknown-age banks are counted in the report and never in candidates."""
    bank_name = "agent-session-ses_unknown2"
    router = make_router(banks=[bank_name])
    bank_dir = make_bank_dir(tmp_path, bank_name)
    router.get_bank_dir.return_value = bank_dir
    monkeypatch.setattr(
        "src.application.use_cases.cleanup_session_banks.get_birth_time",
        lambda path: None,
    )

    report = cleanup_session_banks(router, dry_run=True, ttl_days=30)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 0
    assert report["banks_skipped_unknown_age"] == 1
    assert report["candidates"] == []


def test_cleanup_corrupt_marker_falls_through_to_unknown(tmp_path, monkeypatch):
    """A corrupt (unparseable) marker is treated as absent — no crash."""
    bank_name = "agent-session-ses_corrupt1"
    router = make_router(banks=[bank_name])
    bank_dir = make_bank_dir(tmp_path, bank_name)
    write_marker(bank_dir, content="not a timestamp \x00 garbage")
    router.get_bank_dir.return_value = bank_dir
    monkeypatch.setattr(
        "src.application.use_cases.cleanup_session_banks.get_birth_time",
        lambda path: None,
    )

    report = cleanup_session_banks(router, dry_run=False, ttl_days=30)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 0
    assert report["banks_deleted"] == 0
    assert report["banks_errored"] == 0
    assert report["banks_skipped_unknown_age"] == 1
    assert bank_dir.is_dir()


def test_cleanup_candidate_age_source_birth_time(tmp_path, monkeypatch):
    """Without a marker, a birth-time age is used and reported as birth_time."""
    bank_name = "agent-session-ses_birth1"
    router = make_router(banks=[bank_name])
    bank_dir = make_bank_dir(tmp_path, bank_name)  # no marker
    router.get_bank_dir.return_value = bank_dir
    born = (datetime.now(timezone.utc) - timedelta(days=60)).timestamp()
    monkeypatch.setattr(
        "src.application.use_cases.cleanup_session_banks.get_birth_time",
        lambda path: born,
    )

    report = cleanup_session_banks(router, dry_run=True, ttl_days=30)

    assert report["banks_matched"] == 1
    assert report["banks_eligible"] == 1
    assert report["banks_skipped_unknown_age"] == 0
    assert len(report["candidates"]) == 1
    assert report["candidates"][0]["age_source"] == "birth_time"
    assert report["candidates"][0]["age_days"] >= 59.0
