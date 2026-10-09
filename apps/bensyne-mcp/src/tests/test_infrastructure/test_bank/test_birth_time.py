"""Tests for the statx(2) birth-time helper (DEC-A2 age fallback).

Degradation tests run on every host (the helper must NEVER raise and must
return None wherever crtime is unavailable — including this macOS dev host).
The read-a-real-birth-time test is Linux-only (statx(2) exists only there).
"""

from __future__ import annotations

import sys
import time

import pytest

from src.infrastructure.bank import birth_time
from src.infrastructure.bank.birth_time import get_birth_time


class TestGetBirthTimeDegradation:
    """Any unavailable/failing case must degrade to None, never raise."""

    def test_returns_none_on_non_linux(self, tmp_path, monkeypatch):
        """Non-Linux platforms have no statx(2) — helper returns None."""
        monkeypatch.setattr(birth_time.sys, "platform", "darwin")
        assert get_birth_time(tmp_path) is None

    @pytest.mark.skipif(sys.platform == "linux", reason="macOS dev-host behavior")
    def test_returns_none_on_macos_host(self, tmp_path):
        """On this dev host (macOS) the helper degrades gracefully."""
        assert get_birth_time(tmp_path) is None

    def test_returns_none_for_nonexistent_path(self, tmp_path):
        assert get_birth_time(tmp_path / "does-not-exist") is None

    def test_returns_none_for_path_with_null_byte(self, tmp_path):
        """Odd input (ValueError from os layer) also degrades to None."""
        assert get_birth_time(tmp_path / "bad\x00path") is None

    def test_accepts_str_path(self, tmp_path, monkeypatch):
        """Both str and Path inputs are accepted (still None on non-Linux)."""
        monkeypatch.setattr(birth_time.sys, "platform", "darwin")
        assert get_birth_time(str(tmp_path)) is None


@pytest.mark.skipif(sys.platform != "linux", reason="statx(2) is Linux-only")
class TestGetBirthTimeLinux:
    """Integration: on Linux (ext4) read a known, recent birth time."""

    def test_reads_recent_birth_time(self, tmp_path):
        bank_dir = tmp_path / "fresh-bank"
        bank_dir.mkdir()

        born = get_birth_time(bank_dir)

        assert born is not None
        assert isinstance(born, float)
        # Directory was just created — birth time must be within the last 5 min.
        assert time.time() - born < 300
        assert born <= time.time() + 5
