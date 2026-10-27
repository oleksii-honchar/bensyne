"""Resource-close tests — FD-exhaustion fix (2026-10).

Covers the three leak points closed together:
- pool.evict_if_over_limit closes the evicted instance before dropping it
- MnemosyneClient.close() prefers upstream teardown, else closes the raw conn
  and compare-and-clears the library thread-local slot
- router.get_stats_for closes its transient client even when stats raises

No real sqlite/DB is touched: instances and connections are fakes.
"""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from src.domain.config_models import InstancePoolConfig
from src.infrastructure.bank.pool import evict_if_over_limit
from src.infrastructure.bank.router import MemoryBankRouter
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.utils.result import Result

MNEM_MODULE = "mnemosyne.core.memory"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeConn:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class LibraryShapedInstance:
    """What mnemosyne<=3.15 exposes: a raw sqlite conn in .conn, no teardown."""

    def __init__(self) -> None:
        self.conn = FakeConn()


class UpstreamCloseInstance:
    """A future library instance that knows how to close itself."""

    def __init__(self) -> None:
        self.conn = FakeConn()
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


def _client_wrapping(instance: object) -> MnemosyneClient:
    """A MnemosyneClient that wraps a fake library instance (no real DB)."""
    with patch.object(MnemosyneClient, "_create_instance", return_value=instance):
        return MnemosyneClient(memory_bank="unit-test", data_dir="/nonexistent-unit-test")


class _PooledInstance:
    """Pool-dict stand-in with the attributes the eviction helper reads."""

    def __init__(self, created_at: float) -> None:
        self.created_at = created_at
        self.closed = False

    def close(self) -> None:
        self.closed = True


# ---------------------------------------------------------------------------
# Pool eviction closes the evicted instance
# ---------------------------------------------------------------------------


class TestPoolEvictionCloses:
    def test_evicted_instance_is_closed_and_removed(self) -> None:
        default = _PooledInstance(1.0)
        oldest = _PooledInstance(2.0)
        newest = _PooledInstance(3.0)
        instances = {"default": default, "bank-a": oldest, "bank-b": newest}

        evict_if_over_limit(instances, InstancePoolConfig(max_instances=2))

        assert set(instances) == {"default", "bank-b"}
        assert oldest.closed is True
        assert newest.closed is False
        assert default.closed is False  # default is never evicted, never closed

    def test_evict_instance_without_close_api_does_not_raise(self) -> None:
        plain = SimpleNamespace(created_at=1.0)
        instances = {"default": _PooledInstance(0.0), "bank-x": plain}

        evict_if_over_limit(instances, InstancePoolConfig(max_instances=1))

        assert set(instances) == {"default"}


# ---------------------------------------------------------------------------
# MnemosyneClient.close() semantics
# ---------------------------------------------------------------------------


class TestMnemosyneClientClose:
    def test_noop_when_no_instance(self) -> None:
        client = MnemosyneClient.__new__(MnemosyneClient)
        client.memory_bank = "unit-test"
        client._instance = None
        client.close()  # must not raise

    def test_prefers_upstream_teardown(self) -> None:
        instance = UpstreamCloseInstance()
        _client_wrapping(instance).close()
        assert instance.close_calls == 1
        assert instance.conn.closed is False  # no double-close from our side

    def test_closes_raw_conn_and_clears_matching_thread_local(self, monkeypatch) -> None:
        instance = LibraryShapedInstance()
        fake_mod = SimpleNamespace(
            _thread_local=SimpleNamespace(conn=instance.conn, db_path="/x/mnemosyne.db")
        )
        monkeypatch.setitem(sys.modules, MNEM_MODULE, fake_mod)

        _client_wrapping(instance).close()

        assert instance.conn.closed is True
        assert fake_mod._thread_local.conn is None
        assert fake_mod._thread_local.db_path is None

    def test_thread_local_holding_other_conn_is_untouched(self, monkeypatch) -> None:
        instance = LibraryShapedInstance()
        other = FakeConn()
        fake_mod = SimpleNamespace(
            _thread_local=SimpleNamespace(conn=other, db_path="/other/mnemosyne.db")
        )
        monkeypatch.setitem(sys.modules, MNEM_MODULE, fake_mod)

        _client_wrapping(instance).close()

        assert instance.conn.closed is True
        assert fake_mod._thread_local.conn is other
        assert other.closed is False

    def test_close_is_safe_when_library_module_not_imported(self, monkeypatch) -> None:
        monkeypatch.delitem(sys.modules, MNEM_MODULE, raising=False)
        instance = LibraryShapedInstance()

        _client_wrapping(instance).close()  # must not raise

        assert instance.conn.closed is True


# ---------------------------------------------------------------------------
# Transient stats clients are always closed
# ---------------------------------------------------------------------------


def _router_with_bank_db(tmp_path: Path, bank: str) -> MemoryBankRouter:
    config = InstancePoolConfig(data_dir=str(tmp_path))
    with patch.object(
        MemoryBankRouter,
        "_create_instance",
        side_effect=lambda mb: MagicMock(spec=MnemosyneClient),
    ):
        router = MemoryBankRouter(config=config)
    db_path = router.get_mnemosyne_db_path(bank)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.write_bytes(b"")
    return router


class TestTransientStatsLifecycle:
    def test_get_stats_for_closes_transient_client(self, tmp_path: Path) -> None:
        bank = "stats-bank"
        router = _router_with_bank_db(tmp_path, bank)
        closed: list[bool] = []

        class FakeStatsClient:
            def get_stats(self) -> Result:
                return Result.ok({"memories": 0})

            def close(self) -> None:
                closed.append(True)

        with patch.object(router, "_create_instance", lambda mb: FakeStatsClient()):
            result = router.get_stats_for(bank)

        assert result.is_ok
        assert result.value == {"memories": 0}
        assert closed == [True]

    def test_get_stats_for_closes_transient_even_when_stats_raises(self, tmp_path: Path) -> None:
        bank = "boom-bank"
        router = _router_with_bank_db(tmp_path, bank)
        closed: list[bool] = []

        class BoomClient:
            def get_stats(self) -> Result:
                raise RuntimeError("stats blew up")

            def close(self) -> None:
                closed.append(True)

        with patch.object(router, "_create_instance", lambda mb: BoomClient()):
            with pytest.raises(RuntimeError):
                router.get_stats_for(bank)

        assert closed == [True]

    def test_get_stats_for_without_db_never_creates_client(self, tmp_path: Path) -> None:
        router = _router_with_bank_db(tmp_path, "existing")
        with patch.object(
            router, "_create_instance", side_effect=AssertionError("must not be called")
        ):
            result = router.get_stats_for("ghost-bank")

        assert result.is_ko


# ---------------------------------------------------------------------------
# Teardown fallback order (close > shutdown > dispose)
# ---------------------------------------------------------------------------


class BothTeardownsInstance:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def close(self) -> None:
        self.calls.append("close")

    def shutdown(self) -> None:
        self.calls.append("shutdown")

    def dispose(self) -> None:
        self.calls.append("dispose")


class OnlyShutdownInstance:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def shutdown(self) -> None:
        self.calls.append("shutdown")


class OnlyDisposeInstance:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def dispose(self) -> None:
        self.calls.append("dispose")


class TestTeardownFallbackOrder:
    def test_close_wins_over_shutdown_and_dispose(self) -> None:
        instance = BothTeardownsInstance()
        _client_wrapping(instance).close()
        assert instance.calls == ["close"]

    def test_shutdown_used_when_close_absent(self) -> None:
        instance = OnlyShutdownInstance()
        _client_wrapping(instance).close()
        assert instance.calls == ["shutdown"]

    def test_dispose_used_as_last_fallback(self) -> None:
        instance = OnlyDisposeInstance()
        _client_wrapping(instance).close()
        assert instance.calls == ["dispose"]


# ---------------------------------------------------------------------------
# Error paths — teardown is best-effort but must never corrupt bookkeeping
# ---------------------------------------------------------------------------


class RaisingConn:
    def __init__(self) -> None:
        self.close_attempts = 0

    def close(self) -> None:
        self.close_attempts += 1
        raise RuntimeError("close failed")


class RaisingTeardownInstance:
    def __init__(self) -> None:
        self.close_attempts = 0

    def close(self) -> None:
        self.close_attempts += 1
        raise RuntimeError("upstream teardown failed")


class TestCloseErrorPaths:
    def test_upstream_teardown_raise_is_swallowed(self) -> None:
        instance = RaisingTeardownInstance()
        _client_wrapping(instance).close()  # must not propagate
        assert instance.close_attempts == 1

    def test_conn_close_failure_does_not_clear_thread_local(self, monkeypatch) -> None:
        """If closing failed, the connection may still be open — do NOT drop
        the library thread-local tracking of it."""

        class InstanceWithBadConn:
            def __init__(self) -> None:
                self.conn = RaisingConn()

        instance = InstanceWithBadConn()
        fake_mod = SimpleNamespace(
            _thread_local=SimpleNamespace(conn=instance.conn, db_path="/x/mnemosyne.db")
        )
        monkeypatch.setitem(sys.modules, MNEM_MODULE, fake_mod)

        _client_wrapping(instance).close()  # must not raise

        assert instance.conn.close_attempts == 1
        assert fake_mod._thread_local.conn is instance.conn  # tracking kept
        assert fake_mod._thread_local.db_path == "/x/mnemosyne.db"


# ---------------------------------------------------------------------------
# Pool eviction loop — closes ALL excess, survives close() failures
# ---------------------------------------------------------------------------


class RaisingClosePooled:
    def __init__(self, created_at: float) -> None:
        self.created_at = created_at
        self.close_attempts = 0

    def close(self) -> None:
        self.close_attempts += 1
        raise RuntimeError("close failed")


class TestPoolEvictionLoopAndErrors:
    def test_multi_excess_eviction_closes_every_excess(self) -> None:
        default = _PooledInstance(0.0)
        a = _PooledInstance(1.0)
        b = _PooledInstance(2.0)
        c = _PooledInstance(3.0)
        instances = {"default": default, "bank-a": a, "bank-b": b, "bank-c": c}

        evict_if_over_limit(instances, InstancePoolConfig(max_instances=1))

        assert set(instances) == {"default"}
        assert a.closed and b.closed and c.closed
        assert default.closed is False

    def test_close_raise_still_removes_instances_and_continues(self) -> None:
        default = _PooledInstance(0.0)
        bad_a = RaisingClosePooled(1.0)
        bad_b = RaisingClosePooled(2.0)
        keep = _PooledInstance(3.0)
        instances = {"default": default, "bank-a": bad_a, "bank-b": bad_b, "bank-c": keep}

        evict_if_over_limit(instances, InstancePoolConfig(max_instances=1))  # must not raise

        assert set(instances) == {"default"}  # drains to cap like the non-raising case
        assert bad_a.close_attempts == 1
        assert bad_b.close_attempts == 1
        assert keep.closed is True  # bank-c is also over-cap and gets closed
