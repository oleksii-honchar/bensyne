"""MnemosyneClient infrastructure wrapper tests — Result-returning wrapper.

Verifies:
- MnemosyneClient wraps external Mnemosyne library with Result-returning methods
- All exceptions caught and converted to Result.ko with DATABASE_ERROR
- Each method delegates to the underlying library instance
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.domain.config_models import InstancePoolConfig
from src.utils.result import ErrorWithDetails, Result
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.infrastructure.bank.router import MemoryBankRouter


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_mnemosyne_instance() -> MagicMock:
    """Create a fully configured mock Mnemosyne instance."""
    mock = MagicMock()
    mock.remember.return_value = {"memory_id": "mem_abc", "status": "stored"}
    mock.recall.return_value = [{"id": "mem_1", "content": "hello"}]
    mock.forget.return_value = {"status": "deleted", "memory_id": "mem_123"}
    mock.update.return_value = {"status": "updated", "memory_id": "mem_123"}
    mock.sleep.return_value = {"status": "consolidated", "consolidated": 5}
    mock.get_stats.return_value = {"working": 10, "episodic": 5}
    return mock


@pytest.fixture
def client(mock_mnemosyne_instance: MagicMock) -> MnemosyneClient:
    """Create a MnemosyneClient with a mocked underlying instance."""
    with patch.object(MnemosyneClient, "_create_instance", return_value=mock_mnemosyne_instance):
        c = MnemosyneClient(memory_bank="test-bank")
    return c


# ---------------------------------------------------------------------------
# Constructor
# ---------------------------------------------------------------------------


class TestMnemosyneClientConstructor:
    """MnemosyneClient initializes with memory_bank and creates wrapped instance."""

    def test_stores_memory_bank(self, mock_mnemosyne_instance: MagicMock) -> None:
        """memory_bank is stored as an attribute."""
        with patch.object(MnemosyneClient, "_create_instance", return_value=mock_mnemosyne_instance):
            c = MnemosyneClient(memory_bank="my-bank")
        assert c.memory_bank == "my-bank"

    def test_creates_wrapped_instance(self, mock_mnemosyne_instance: MagicMock) -> None:
        """_create_instance is called during construction."""
        with patch.object(MnemosyneClient, "_create_instance", return_value=mock_mnemosyne_instance) as mock_create:
            MnemosyneClient(memory_bank="test")
        mock_create.assert_called_once()

    def test_instance_error_propagates(self) -> None:
        """If _create_instance raises, the exception propagates from __init__."""
        with patch.object(MnemosyneClient, "_create_instance", side_effect=ConnectionError("timeout")):
            with pytest.raises(ConnectionError, match="timeout"):
                MnemosyneClient(memory_bank="test-bank")

    def test_accepts_optional_data_dir(self, mock_mnemosyne_instance: MagicMock) -> None:
        """data_dir parameter is accepted."""
        with patch.object(MnemosyneClient, "_create_instance", return_value=mock_mnemosyne_instance) as mock_create:
            MnemosyneClient(memory_bank="test", data_dir="/custom/data")
        # _create_instance receives data_dir
        call_kwargs = mock_create.call_args.kwargs
        assert call_kwargs["data_dir"] == "/custom/data"

    def test_default_data_dir_is_relative(
        self, mock_mnemosyne_instance: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When no data_dir or DATA_DIR is given, the client defaults to relative ./data."""
        monkeypatch.delenv("DATA_DIR", raising=False)
        with patch.object(MnemosyneClient, "_create_instance", return_value=mock_mnemosyne_instance) as mock_create:
            MnemosyneClient(memory_bank="test")
        assert mock_create.call_args.kwargs["data_dir"] == "./data"

    def test_data_dir_env_wins_over_default(
        self, mock_mnemosyne_instance: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DATA_DIR env var is honored when no explicit data_dir is given."""
        monkeypatch.setenv("DATA_DIR", "/from/env")
        with patch.object(MnemosyneClient, "_create_instance", return_value=mock_mnemosyne_instance) as mock_create:
            MnemosyneClient(memory_bank="test")
        assert mock_create.call_args.kwargs["data_dir"] == "/from/env"

    def test_explicit_data_dir_wins_over_env(
        self, mock_mnemosyne_instance: MagicMock, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An explicit data_dir (e.g. from CLI --data-dir) wins over the DATA_DIR env var."""
        monkeypatch.setenv("DATA_DIR", "/from/env")
        with patch.object(MnemosyneClient, "_create_instance", return_value=mock_mnemosyne_instance) as mock_create:
            MnemosyneClient(memory_bank="test", data_dir="/from/cli")
        assert mock_create.call_args.kwargs["data_dir"] == "/from/cli"


# ---------------------------------------------------------------------------
# remember
# ---------------------------------------------------------------------------


class TestMnemosyneClientRemember:
    """remember() returns Result.ok on success, Result.ko on error."""

    def test_returns_result_ok_on_success(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """remember() returns Result.ok with the library's response."""
        result = client.remember(content="test content", source="test")

        assert result.is_ok
        assert result.value == {"memory_id": "mem_abc", "status": "stored"}
        mock_mnemosyne_instance.remember.assert_called_once_with(content="test content", source="test")

    def test_returns_result_ko_on_exception(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """remember() returns Result.ko with DATABASE_ERROR when library raises."""
        mock_mnemosyne_instance.remember.side_effect = ConnectionError("db down")

        result = client.remember(content="test")

        assert result.is_ko
        errors = result.get_errors()
        assert len(errors) == 1
        assert errors[0].error_code == "DATABASE_ERROR"

    def test_passes_kwargs_through(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """remember() passes through arbitrary kwargs."""
        client.remember(content="test", source="custom", importance=0.9, tags=["tag1"])
        mock_mnemosyne_instance.remember.assert_called_once_with(
            content="test", source="custom", importance=0.9, tags=["tag1"]
        )


# ---------------------------------------------------------------------------
# recall
# ---------------------------------------------------------------------------


class TestMnemosyneClientRecall:
    """recall() returns Result.ok with results, Result.ko on error."""

    def test_returns_result_ok_with_results(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """recall() returns Result.ok with the list of recalled memories."""
        result = client.recall(query="hello", limit=5)

        assert result.is_ok
        assert result.value == [{"id": "mem_1", "content": "hello"}]
        mock_mnemosyne_instance.recall.assert_called_once_with(query="hello", top_k=5)

    def test_returns_result_ko_on_exception(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """recall() returns Result.ko with DATABASE_ERROR when library raises."""
        mock_mnemosyne_instance.recall.side_effect = RuntimeError("index corrupted")

        result = client.recall(query="test")

        assert result.is_ko
        errors = result.get_errors()
        assert errors[0].error_code == "DATABASE_ERROR"

    def test_default_limit(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """recall() uses default limit of 5."""
        result = client.recall(query="test")

        assert result.is_ok
        mock_mnemosyne_instance.recall.assert_called_once_with(query="test", top_k=5)


# ---------------------------------------------------------------------------
# forget
# ---------------------------------------------------------------------------


class TestMnemosyneClientForget:
    """forget() returns Result.ok on success, Result.ko on error."""

    def test_returns_result_ok_on_success(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """forget() returns Result.ok with the library's response."""
        result = client.forget(memory_id="mem_123")

        assert result.is_ok
        assert result.value == {"status": "deleted", "memory_id": "mem_123"}
        mock_mnemosyne_instance.forget.assert_called_once_with(memory_id="mem_123")

    def test_returns_result_ko_on_exception(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """forget() returns Result.ko with DATABASE_ERROR when library raises."""
        mock_mnemosyne_instance.forget.side_effect = ConnectionError("db down")

        result = client.forget(memory_id="mem_123")

        assert result.is_ko
        errors = result.get_errors()
        assert errors[0].error_code == "DATABASE_ERROR"


# ---------------------------------------------------------------------------
# update
# ---------------------------------------------------------------------------


class TestMnemosyneClientUpdate:
    """update() returns Result.ok on success, Result.ko on error."""

    def test_returns_result_ok_on_success(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """update() returns Result.ok with the library's response."""
        result = client.update(memory_id="mem_123", content="new content", importance=0.8)

        assert result.is_ok
        assert result.value == {"status": "updated", "memory_id": "mem_123"}
        mock_mnemosyne_instance.update.assert_called_once_with(
            memory_id="mem_123", content="new content", importance=0.8
        )

    def test_returns_result_ko_on_exception(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """update() returns Result.ko with DATABASE_ERROR when library raises."""
        mock_mnemosyne_instance.update.side_effect = RuntimeError("update failed")

        result = client.update(memory_id="mem_123", content="new")

        assert result.is_ko
        errors = result.get_errors()
        assert errors[0].error_code == "DATABASE_ERROR"


# ---------------------------------------------------------------------------
# sleep
# ---------------------------------------------------------------------------


class TestMnemosyneClientSleep:
    """sleep() returns Result.ok on success, Result.ko on error."""

    def test_returns_result_ok_on_success(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """sleep() returns Result.ok with the library's response."""
        result = client.sleep()

        assert result.is_ok
        assert result.value == {"status": "consolidated", "consolidated": 5}
        mock_mnemosyne_instance.sleep.assert_called_once()

    def test_returns_result_ko_on_exception(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """sleep() returns Result.ko with DATABASE_ERROR when library raises."""
        mock_mnemosyne_instance.sleep.side_effect = ConnectionError("consolidation failed")

        result = client.sleep()

        assert result.is_ko
        errors = result.get_errors()
        assert errors[0].error_code == "DATABASE_ERROR"


# ---------------------------------------------------------------------------
# get (callable contract for content composition)
# ---------------------------------------------------------------------------


class TestMnemosyneClientGet:
    """get() returns the memory dict for an id, or None on missing/error.

    Implements the callable contract used by
    FileMetadata.compose_content/compose_fetch (memory_id -> memory dict).
    """

    def test_returns_what_underlying_get_returns(
        self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock
    ) -> None:
        """get() returns exactly what the underlying instance.get returns."""
        memory = {"id": "mem_1", "content": "hello"}
        mock_mnemosyne_instance.get.return_value = memory

        result = client.get("mem_1")

        assert result == memory
        mock_mnemosyne_instance.get.assert_called_once_with("mem_1")

    def test_returns_none_when_underlying_returns_none(
        self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock
    ) -> None:
        """get() returns None when the underlying instance.get returns None."""
        mock_mnemosyne_instance.get.return_value = None

        result = client.get("missing")

        assert result is None

    def test_returns_none_when_underlying_raises(
        self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock
    ) -> None:
        """get() returns None when the underlying instance.get raises (no propagation)."""
        mock_mnemosyne_instance.get.side_effect = RuntimeError("db down")

        result = client.get("mem_1")

        assert result is None


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


class TestMnemosyneClientStats:
    """get_stats() returns Result.ok on success, Result.ko on error."""

    def test_returns_result_ok_on_success(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """get_stats() returns Result.ok with the library's response."""
        result = client.get_stats()

        assert result.is_ok
        assert result.value == {"working": 10, "episodic": 5}
        mock_mnemosyne_instance.get_stats.assert_called_once()

    def test_returns_result_ko_on_exception(self, client: MnemosyneClient, mock_mnemosyne_instance: MagicMock) -> None:
        """get_stats() returns Result.ko with DATABASE_ERROR when library raises."""
        mock_mnemosyne_instance.get_stats.side_effect = RuntimeError("stats unavailable")

        result = client.get_stats()

        assert result.is_ko
        errors = result.get_errors()
        assert errors[0].error_code == "DATABASE_ERROR"


# ---------------------------------------------------------------------------
# memory_bank_router kwarg — uniform v2 path authority (Task 4, DEC-0062/U11)
# ---------------------------------------------------------------------------


def _make_router(tmp_path: Path) -> MemoryBankRouter:
    """Create a router with a tmp data_dir and mocked client creation."""
    config = InstancePoolConfig(
        max_instances=5,
        eviction_timeout=300,
        data_dir=str(tmp_path),
        default_bank="default",
    )
    mock = MagicMock(spec=MnemosyneClient)
    mock.memory_bank = "default"
    with patch.object(MemoryBankRouter, "_create_instance", return_value=mock):
        return MemoryBankRouter(config=config)


class TestMnemosyneClientRouterKwarg:
    """_create_instance resolves db_path via the router (uniform banks/ layout)."""

    def test_default_bank_resolves_uniform_path(self, tmp_path: Path) -> None:
        """'default' with router → <tmp>/banks/default/mnemosyne.db (was <tmp>/mnemosyne.db)."""
        router = _make_router(tmp_path)
        with patch("mnemosyne.core.memory.Mnemosyne") as mock_mnemosyne_cls:
            MnemosyneClient(memory_bank="default", data_dir=str(tmp_path), memory_bank_router=router)
        mock_mnemosyne_cls.assert_called_once_with(bank="default", db_path=str(tmp_path / "banks" / "default" / "mnemosyne.db"))

    def test_custom_bank_resolves_uniform_path_and_creates_parent(self, tmp_path: Path) -> None:
        """'custom' with router → <tmp>/banks/custom/mnemosyne.db; parent dir created."""
        router = _make_router(tmp_path)
        with patch("mnemosyne.core.memory.Mnemosyne") as mock_mnemosyne_cls:
            MnemosyneClient(memory_bank="custom", data_dir=str(tmp_path), memory_bank_router=router)
        expected = tmp_path / "banks" / "custom"
        assert expected.is_dir()
        mock_mnemosyne_cls.assert_called_once_with(bank="custom", db_path=str(expected / "mnemosyne.db"))

    def test_without_router_keeps_legacy_default_path(self, tmp_path: Path) -> None:
        """No router → default bank still lands at <data_dir>/mnemosyne.db (backward-compat fallback)."""
        with patch("mnemosyne.core.memory.Mnemosyne") as mock_mnemosyne_cls:
            MnemosyneClient(memory_bank="default", data_dir=str(tmp_path))
        mock_mnemosyne_cls.assert_called_once_with(bank="default", db_path=str(tmp_path / "mnemosyne.db"))

    def test_without_router_keeps_legacy_custom_path(self, tmp_path: Path) -> None:
        """No router → custom bank still lands at <data_dir>/banks/<bank>/mnemosyne.db (fallback)."""
        with patch("mnemosyne.core.memory.Mnemosyne") as mock_mnemosyne_cls:
            MnemosyneClient(memory_bank="custom", data_dir=str(tmp_path))
        mock_mnemosyne_cls.assert_called_once_with(bank="custom", db_path=str(tmp_path / "banks" / "custom" / "mnemosyne.db"))


# ---------------------------------------------------------------------------
# get_stats router workaround (DEC-0066/S7) — canonical banks key + phantom cleanup
# ---------------------------------------------------------------------------


class TestMnemosyneClientStatsRouter:
    """get_stats() with a router overwrites banks from the canonical filesystem view."""

    def test_banks_key_overwritten_by_list_bank_dirs(self, tmp_path: Path) -> None:
        """Library's phantom banks list is replaced by router.list_bank_dirs()."""
        router = _make_router(tmp_path)
        (tmp_path / "banks" / "alpha").mkdir(parents=True)
        (tmp_path / "banks" / "zeta").mkdir(parents=True)
        mock = MagicMock()
        mock.get_stats.return_value = {"working": 10, "banks": ["phantom-bank"]}
        with patch.object(MnemosyneClient, "_create_instance", return_value=mock):
            client = MnemosyneClient(memory_bank="default", data_dir=str(tmp_path), memory_bank_router=router)

        result = client.get_stats()

        assert result.is_ok
        assert result.value["banks"] == ["alpha", "zeta"]

    def test_empty_phantom_banks_dir_removed(self, tmp_path: Path) -> None:
        """Empty nested <bank_dir>/banks/ phantom dir is removed; bank data untouched."""
        router = _make_router(tmp_path)
        bank_dir = tmp_path / "banks" / "somebank"
        phantom = bank_dir / "banks"
        phantom.mkdir(parents=True)
        data_file = bank_dir / "mnemosyne.db"
        data_file.write_text("bank data")
        mock = MagicMock()
        mock.get_stats.return_value = {"working": 10, "banks": ["somebank"]}
        with patch.object(MnemosyneClient, "_create_instance", return_value=mock):
            client = MnemosyneClient(memory_bank="somebank", data_dir=str(tmp_path), memory_bank_router=router)

        result = client.get_stats()

        assert result.is_ok
        assert not phantom.exists()
        assert data_file.read_text() == "bank data"

    def test_empty_phantom_dir_with_nested_empty_dirs_removed(self, tmp_path: Path) -> None:
        """Phantom dir empty 'at any depth' (only nested empty dirs) is still removed."""
        router = _make_router(tmp_path)
        phantom = tmp_path / "banks" / "somebank" / "banks" / "nested" / "deeper"
        phantom.mkdir(parents=True)
        mock = MagicMock()
        mock.get_stats.return_value = {"working": 10, "banks": ["somebank"]}
        with patch.object(MnemosyneClient, "_create_instance", return_value=mock):
            client = MnemosyneClient(memory_bank="somebank", data_dir=str(tmp_path), memory_bank_router=router)

        result = client.get_stats()

        assert result.is_ok
        assert not (tmp_path / "banks" / "somebank" / "banks").exists()

    def test_non_empty_phantom_dir_left_and_warns(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-empty phantom <bank_dir>/banks/ is left in place with a warning."""
        router = _make_router(tmp_path)
        phantom = tmp_path / "banks" / "somebank" / "banks"
        phantom.mkdir(parents=True)
        (phantom / "orphan.txt").write_text("precious")
        data_file = tmp_path / "banks" / "somebank" / "mnemosyne.db"
        data_file.write_text("bank data")
        mock = MagicMock()
        mock.get_stats.return_value = {"working": 10, "banks": ["somebank"]}
        with patch.object(MnemosyneClient, "_create_instance", return_value=mock):
            client = MnemosyneClient(memory_bank="somebank", data_dir=str(tmp_path), memory_bank_router=router)

        result = client.get_stats()

        assert result.is_ok
        assert phantom.is_dir()
        assert (phantom / "orphan.txt").exists()
        assert data_file.read_text() == "bank data"
        # The non-empty phantom dir is flagged with a warning (behavioral check).
        captured = capsys.readouterr().out
        assert "warning" in captured.lower()
        assert "Phantom banks dir left in place" in captured

    def test_without_router_returns_library_result_unchanged(self) -> None:
        """No router → get_stats() returns the plain library result (no crash, no rewrite)."""
        mock = MagicMock()
        mock.get_stats.return_value = {"working": 10, "banks": ["weird-list"]}
        with patch.object(MnemosyneClient, "_create_instance", return_value=mock):
            client = MnemosyneClient(memory_bank="default")

        result = client.get_stats()

        assert result.is_ok
        assert result.value == {"working": 10, "banks": ["weird-list"]}
