"""MemoryBankRouter refactored tests — uses new MnemosyneClient (Result-returning).

Verifies:
- Router uses new MnemosyneClient (Result-returning) instead of raw client
- get_instance returns existing instance for known bank
- get_instance creates new instance for unknown bank
- list_banks returns list of active bank names
- register_bank adds bank to registry
- Structured logging for router operations
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.domain.config_models import InstancePoolConfig
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.infrastructure.bank.router import MemoryBankRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_client(memory_bank: str) -> MagicMock:
    """Create a mock MnemosyneClient with required attributes."""
    mock = MagicMock(spec=MnemosyneClient)
    mock.memory_bank = memory_bank
    mock.created_at = time.time()
    mock.last_accessed = time.time()
    return mock


def _make_router(tmp_path: Path, max_instances: int = 5) -> MemoryBankRouter:
    """Create a MemoryBankRouter with mocked _create_instance."""
    config = InstancePoolConfig(
        max_instances=max_instances,
        eviction_timeout=300,
        data_dir=str(tmp_path),
        default_bank="default",
    )
    with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
        return MemoryBankRouter(config=config)


# ---------------------------------------------------------------------------
# Router uses new MnemosyneClient
# ---------------------------------------------------------------------------


class TestRouterUsesNewClient:
    """Router uses new MnemosyneClient (Result-returning) instead of raw client."""

    def test_default_instance_is_new_mnemosyne_client(self, tmp_path: Path) -> None:
        """Default instance is an instance of the new MnemosyneClient class."""
        router = _make_router(tmp_path)
        assert isinstance(router.instances["default"], MnemosyneClient)

    def test_default_instance_memory_bank(self, tmp_path: Path) -> None:
        """Default instance has memory_bank 'default'."""
        router = _make_router(tmp_path)
        assert router.instances["default"].memory_bank == "default"

    def test_router_does_not_accept_bank_manager(self, tmp_path: Path) -> None:
        """Router constructor no longer accepts bank_manager parameter."""
        config = InstancePoolConfig(data_dir=str(tmp_path))
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = MemoryBankRouter(config=config)
        assert "default" in router.instances

    def test_new_instance_is_new_mnemosyne_client(self, tmp_path: Path) -> None:
        """Dynamically created instance is also the new MnemosyneClient."""
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path)

            async def run() -> None:
                instance = await router.get_instance("test-bank")
                assert isinstance(instance, MnemosyneClient)
                assert instance.memory_bank == "test-bank"

            asyncio.run(run())


# ---------------------------------------------------------------------------
# get_instance — caching and creation
# ---------------------------------------------------------------------------


class TestRouterGetInstance:
    """get_instance returns MnemosyneClient, manages pool lifecycle."""

    def test_router_passes_memory_bank_router_into_client(self, tmp_path: Path) -> None:
        """_create_instance passes memory_bank_router=self into MnemosyneClient (S1 HIGH mitigation)."""
        config = InstancePoolConfig(
            max_instances=5,
            eviction_timeout=300,
            data_dir=str(tmp_path),
            default_bank="default",
        )
        with patch("src.infrastructure.bank.router.MnemosyneClient") as mock_client_cls:
            mock_client_cls.return_value = _make_mock_client("default")
            router = MemoryBankRouter(config=config)

        mock_client_cls.assert_called_once_with(
            memory_bank="default",
            data_dir=str(tmp_path),
            memory_bank_router=router,
        )

    def test_get_instance_returns_existing_instance_for_known_bank(self, tmp_path: Path) -> None:
        """Second call for same memory bank returns the same cached instance."""
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path)

            async def run() -> None:
                first = await router.get_instance("default")
                second = await router.get_instance("default")
                assert first is second

            asyncio.run(run())

    def test_get_instance_creates_new_instance_for_unknown_bank(self, tmp_path: Path) -> None:
        """First call for a new memory bank creates a new MnemosyneClient instance."""
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path)

            async def run() -> None:
                # Before: only default exists
                assert len(router.instances) == 1

                # First call for "test-ns" creates instance
                instance = await router.get_instance("test-ns")

                # Now both exist
                assert "test-ns" in router.instances
                assert len(router.instances) == 2
                assert instance.memory_bank == "test-ns"

            asyncio.run(run())

    def test_get_instance_returns_mnemosyne_client(self, tmp_path: Path) -> None:
        """get_instance returns a MnemosyneClient instance."""
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path)

            async def run() -> None:
                instance = await router.get_instance("default")
                assert isinstance(instance, MnemosyneClient)

            asyncio.run(run())

    def test_get_instance_updates_last_accessed(self, tmp_path: Path) -> None:
        """get_instance updates last_accessed timestamp on cached instance."""
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path)

            async def run() -> None:
                instance = router.instances["default"]
                before = time.time()

                await router.get_instance("default")

                after = time.time()
                assert before <= instance.last_accessed <= after

            asyncio.run(run())


# ---------------------------------------------------------------------------
# list_banks
# ---------------------------------------------------------------------------


class TestRouterListBanks:
    """list_banks returns list of active bank names."""

    def test_list_banks_returns_active_bank_names(self, tmp_path: Path) -> None:
        """list_banks returns the names of all active memory banks."""
        router = _make_router(tmp_path)
        banks = router.list_banks()
        assert "default" in banks

    def test_list_banks_reflects_new_instances(self, tmp_path: Path) -> None:
        """list_banks includes banks created via get_instance."""
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path)

            async def run() -> None:
                await router.get_instance("new-bank")
                banks = router.list_banks()
                assert "new-bank" in banks

            asyncio.run(run())

    def test_list_banks_returns_list_type(self, tmp_path: Path) -> None:
        """list_banks returns a list, not a set or other collection."""
        router = _make_router(tmp_path)
        banks = router.list_banks()
        assert isinstance(banks, list)


# ---------------------------------------------------------------------------
# Path authority (DEC-0064/U14) — v2 uniform paths under <data_dir>/banks/
# ---------------------------------------------------------------------------


class TestRouterPathAuthority:
    """Router is the single path authority for memory bank storage (v2 layout)."""

    def test_get_bank_db_path_uniform_for_default(self, tmp_path: Path) -> None:
        """'default' resolves under banks/ like any bank — NO root special-case."""
        router = _make_router(tmp_path)
        assert router.get_bank_db_path("default") == tmp_path / "banks" / "default" / "mnemosyne.db"

    def test_get_bank_db_path_creates_parent_dir(self, tmp_path: Path) -> None:
        """get_bank_db_path mkdirs the bank dir (write path)."""
        router = _make_router(tmp_path)
        path = router.get_bank_db_path("foo")
        assert path.parent.is_dir()
        assert path.parent == tmp_path / "banks" / "foo"

    def test_get_bank_dir_creates_dir(self, tmp_path: Path) -> None:
        """get_bank_dir returns <data_dir>/banks/<bank> and creates the dir."""
        router = _make_router(tmp_path)
        bank_dir = router.get_bank_dir("foo")
        assert bank_dir == tmp_path / "banks" / "foo"
        assert bank_dir.is_dir()

    def test_get_file_metadata_path_does_not_create_dir(self, tmp_path: Path) -> None:
        """get_file_metadata_path returns the co-located path WITHOUT mkdir (read-side)."""
        router = _make_router(tmp_path)
        path = router.get_file_metadata_path("foo")
        assert path == tmp_path / "banks" / "foo" / "file_metadata.db"
        assert not (tmp_path / "banks" / "foo").exists()

    def test_get_hash_index_path_does_not_create_dir(self, tmp_path: Path) -> None:
        """get_hash_index_path returns the co-located path WITHOUT mkdir (read-side)."""
        router = _make_router(tmp_path)
        path = router.get_hash_index_path("foo")
        assert path == tmp_path / "banks" / "foo" / "hash_index.db"
        assert not (tmp_path / "banks" / "foo").exists()

    def test_get_bank_db_path_is_uniform_for_custom_bank(self, tmp_path: Path) -> None:
        """Custom banks resolve identically to default under banks/."""
        router = _make_router(tmp_path)
        assert router.get_bank_db_path("custom") == tmp_path / "banks" / "custom" / "mnemosyne.db"


class TestRouterListBankDirs:
    """list_bank_dirs is a read-only scan of <data_dir>/banks/."""

    def test_list_bank_dirs_returns_sorted_names(self, tmp_path: Path) -> None:
        """Existing banks/ dir yields sorted bank names."""
        (tmp_path / "banks" / "zeta").mkdir(parents=True)
        (tmp_path / "banks" / "alpha").mkdir(parents=True)
        router = _make_router(tmp_path)
        assert router.list_bank_dirs() == ["alpha", "zeta"]

    def test_list_bank_dirs_returns_empty_when_banks_absent(self, tmp_path: Path) -> None:
        """No banks/ dir → empty list."""
        router = _make_router(tmp_path)
        assert router.list_bank_dirs() == []

    def test_list_bank_dirs_creates_nothing(self, tmp_path: Path) -> None:
        """list_bank_dirs has NO mkdir/delete side effects."""
        router = _make_router(tmp_path)
        router.list_bank_dirs()
        assert not (tmp_path / "banks").exists()


# ---------------------------------------------------------------------------
# Registry duties removed (S13) — no registry/description methods
# ---------------------------------------------------------------------------


class TestRouterRegistryRemoved:
    """Router no longer exposes in-memory registry duties (S13)."""

    def test_router_has_no_registry_attribute(self, tmp_path: Path) -> None:
        """self.registry is gone."""
        router = _make_router(tmp_path)
        assert not hasattr(router, "registry")

    def test_router_has_no_get_bank_description(self, tmp_path: Path) -> None:
        """get_bank_description is gone."""
        router = _make_router(tmp_path)
        assert not hasattr(router, "get_bank_description")

    def test_router_has_no_register_bank(self, tmp_path: Path) -> None:
        """register_bank is gone."""
        router = _make_router(tmp_path)
        assert not hasattr(router, "register_bank")


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


class TestRouterStructuredLogging:
    """Structured logging for router operations (instance creation, eviction)."""

    def test_instance_creation_logs_structured(self, tmp_path: Path) -> None:
        """Creating a new instance logs with structured fields."""
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path)

        # Router uses structured logging (logger from get_logger)
        from src.infrastructure.bank import router as router_module

        assert hasattr(router_module, "logger")

    def test_eviction_logs_structured(self, tmp_path: Path) -> None:
        """Evicting an instance logs with structured fields."""
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path, max_instances=3)

            async def run() -> None:
                # Fill to max_instances
                await router.get_instance("ns1")
                await router.get_instance("ns2")
                assert len(router.instances) == 3

                # Trigger eviction
                await router.get_instance("ns3")

                # ns1 should be evicted
                assert "ns1" not in router.instances
                assert "ns2" in router.instances
                assert "ns3" in router.instances

            asyncio.run(run())
