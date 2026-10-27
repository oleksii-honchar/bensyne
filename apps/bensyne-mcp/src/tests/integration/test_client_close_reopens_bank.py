"""Integration: closing a client frees the library thread-local slot so the
same bank re-opens cleanly in the SAME thread.

Real `mnemosyne` library on a temp dir (no network, no embeddings — stats are
pure SQL). This is the end-to-end guard for the 2026-10 FD-exhaustion fix:
without `MnemosyneClient.close()`'s compare-and-clear of
``mnemosyne.core.memory._thread_local``, a later client in the same thread
would either inherit the closed sqlite connection (ProgrammingError) or
accumulate another one (the fd leak itself).
"""

from __future__ import annotations

import sqlite3
from collections.abc import Generator
from pathlib import Path

import pytest

from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient

BANK = "unit-close-reopen"


@pytest.fixture(autouse=True)
def _isolate_library_thread_local() -> Generator[None, None, None]:
    """Neuter any connection this test leaves behind so sibling tests in the
    same worker never inherit our thread-local slot."""
    yield
    try:
        from mnemosyne.core import memory as memory_mod
    except Exception:  # pragma: no cover - library always present in this env
        return
    thread_local = getattr(memory_mod, "_thread_local", None)
    if thread_local is None:
        return
    conn = getattr(thread_local, "conn", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:
            pass
    thread_local.conn = None
    if hasattr(thread_local, "db_path"):
        thread_local.db_path = None


def _execute(conn: sqlite3.Connection) -> None:
    conn.execute("SELECT 1")


def test_close_then_reopen_same_bank(tmp_path: Path) -> None:
    data_dir = str(tmp_path / "data")

    client_one = MnemosyneClient(memory_bank=BANK, data_dir=data_dir)
    first_stats = client_one.get_stats()
    assert first_stats.is_ok, first_stats.errors
    conn_one = client_one._instance.conn

    client_one.close()

    # The connection really is closed...
    with pytest.raises(sqlite3.ProgrammingError):
        _execute(conn_one)

    # ...and the library's thread-local slot was cleared for this thread.
    from mnemosyne.core import memory as memory_mod

    thread_local = getattr(memory_mod, "_thread_local", None)
    assert thread_local is not None
    assert getattr(thread_local, "conn", None) is None

    # A fresh client for the SAME bank works — it must not inherit the corpse.
    client_two = MnemosyneClient(memory_bank=BANK, data_dir=data_dir)
    second_stats = client_two.get_stats()
    assert second_stats.is_ok, second_stats.errors
    assert client_two._instance.conn is not conn_one

    client_two.close()
