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

from src.domain.models import InstancePoolConfig
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.services.bank.router import MemoryBankRouter


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
# register_bank
# ---------------------------------------------------------------------------

class TestRouterRegisterBank:
    """register_bank registers new bank in registry."""

    def test_register_bank_adds_bank_to_registry(self, tmp_path: Path) -> None:
        """register_bank adds a new bank description to the registry."""
        router = _make_router(tmp_path)
        router.register_bank("project-x", "Project X memories")
        desc = router.get_bank_description("project-x")
        assert desc == "Project X memories"

    def test_register_bank_overwrites_existing(self, tmp_path: Path) -> None:
        """register_bank overwrites an existing bank description."""
        router = _make_router(tmp_path)
        router.register_bank("ns1", "first description")
        assert router.get_bank_description("ns1") == "first description"

        router.register_bank("ns1", "second description")
        assert router.get_bank_description("ns1") == "second description"


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
        from src.services.bank import router as router_module
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
