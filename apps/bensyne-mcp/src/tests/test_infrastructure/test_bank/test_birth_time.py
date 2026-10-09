"""Tests for the statx(2) birth-time helper (DEC-A2 age fallback).

Degradation tests run on every host (the helper must NEVER raise and must
return None wherever crtime is unavailable — including this macOS dev host).
The marshalling-contract tests run on every host too: they stub ctypes.CDLL
and assert the ctypes call contract (argtypes/restype assigned before the
call, path passed as bytes) — the bug that made production stat the wrong
inode (Task 5) is caught here without Linux.
The read-a-real-birth-time tests are Linux-only (statx(2) exists only there).
"""

from __future__ import annotations

import ctypes
import os
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


class _RecordingFunc:
    """Callable standing in for libc.statx / libc.syscall.

    Records each invocation together with the argtypes/restype visible ON THE
    FUNCTION OBJECT AT CALL TIME — proving the helper configured marshalling
    BEFORE invoking, not after.
    """

    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(
            {
                "args": args,
                "argtypes_at_call": getattr(self, "argtypes", None),
                "restype_at_call": getattr(self, "restype", None),
            }
        )
        return -1  # non-zero → helper must degrade to None, never raise


class TestStatxMarshallingContract:
    """ctypes call contract — the Task 5 defect (wrong inode via mis-marshalling).

    macOS-runnable by design: ctypes.CDLL is stubbed, no Linux required.
    Without argtypes, ctypes passes the Python str as a wide-string pointer →
    statx stats the WRONG inode; and a str path is mis-marshalled regardless.
    """

    def test_statx_path_sets_argtypes_restype_and_passes_bytes_path(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(birth_time.sys, "platform", "linux")

        statx_fn = _RecordingFunc()

        class _FakeLibc:
            statx = statx_fn

        monkeypatch.setattr(
            birth_time.ctypes, "CDLL", lambda *a, **k: _FakeLibc()
        )

        assert get_birth_time(tmp_path) is None  # stub returned -1

        assert len(statx_fn.calls) == 1
        call = statx_fn.calls[0]
        assert call["argtypes_at_call"] == [
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.POINTER(birth_time._Statx),
        ]
        assert call["restype_at_call"] is ctypes.c_int
        path_arg = call["args"][1]
        assert isinstance(path_arg, bytes), "path must be bytes, not str"
        assert path_arg == os.fsencode(str(tmp_path))

    def test_syscall_fallback_sets_argtypes_restype_and_passes_bytes_path(
        self, tmp_path, monkeypatch
    ):
        monkeypatch.setattr(birth_time.sys, "platform", "linux")
        monkeypatch.setattr(birth_time.platform, "machine", lambda: "x86_64")

        syscall_fn = _RecordingFunc()

        class _FakeLibcNoStatx:
            """hasattr(libc, 'statx') is False → syscall fallback branch."""

            syscall = syscall_fn

        monkeypatch.setattr(
            birth_time.ctypes, "CDLL", lambda *a, **k: _FakeLibcNoStatx()
        )

        assert get_birth_time(tmp_path) is None  # stub returned -1

        assert len(syscall_fn.calls) == 1
        call = syscall_fn.calls[0]
        assert call["argtypes_at_call"] == [
            ctypes.c_long,
            ctypes.c_int,
            ctypes.c_char_p,
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.POINTER(birth_time._Statx),
        ]
        assert call["restype_at_call"] is ctypes.c_int
        path_arg = call["args"][2]
        assert isinstance(path_arg, bytes), "path must be bytes, not str"
        assert path_arg == os.fsencode(str(tmp_path))


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

    def test_distinct_dirs_yield_distinct_ordered_birth_times(self, tmp_path):
        """Discriminates the wrong-inode bug (Task 5): if every path stats the
        same inode, both dirs return IDENTICAL values. Two sequentially
        created dirs must yield DISTINCT birth times in creation order."""
        dir_a = tmp_path / "bank-a"
        dir_a.mkdir()
        time.sleep(0.1)
        dir_b = tmp_path / "bank-b"
        dir_b.mkdir()

        born_a = get_birth_time(dir_a)
        born_b = get_birth_time(dir_b)

        assert born_a is not None
        assert born_b is not None
        assert born_b >= born_a, "second dir must not predate the first"
        assert born_b != born_a, "identical values ⇒ same inode was stat'ed"
