"""Memory bank router and instance pool tests — refactored for new MnemosyneClient."""

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
# MemoryBankRouter creation and default instance
# ---------------------------------------------------------------------------

class TestMemoryBankRouterCreation:
    """MemoryBankRouter initializes with default instance at boot."""

    def test_default_instance_created_at_boot(self, tmp_path: Path) -> None:
        """Default instance exists immediately after router creation."""
        router = _make_router(tmp_path)
        assert "default" in router.instances

    def test_default_instance_is_mnemosyne_client(self, tmp_path: Path) -> None:
        """Default instance is a MnemosyneClient."""
        router = _make_router(tmp_path)
        assert isinstance(router.instances["default"], MnemosyneClient)

    def test_default_instance_memory_bank(self, tmp_path: Path) -> None:
        """Default instance has memory_bank 'default'."""
        router = _make_router(tmp_path)
        assert router.instances["default"].memory_bank == "default"


# ---------------------------------------------------------------------------
# get_instance — caching and creation
# ---------------------------------------------------------------------------

class TestMemoryBankRouterGetInstance:
    """MemoryBankRouter.get_instance returns cached instance on second call."""

    def test_get_instance_returns_cached_instance_on_second_call(self, tmp_path: Path) -> None:
        """Second call for same memory bank returns the same instance."""
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path)

            async def run() -> None:
                first = await router.get_instance("default")
                second = await router.get_instance("default")
                assert first is second

            asyncio.run(run())

    def test_new_instance_created_for_new_memory_bank(self, tmp_path: Path) -> None:
        """First call for a new memory bank creates a new instance."""
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

    def test_get_instance_updates_last_accessed(self, tmp_path: Path) -> None:
        """get_instance updates last_accessed timestamp."""
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
# LRU eviction — oldest created non-default evicted at max_instances
# ---------------------------------------------------------------------------

class TestMemoryBankRouterLRUEviction:
    """LRU eviction works at max_instances limit."""

    def test_lru_eviction_works_at_max_instances_limit(self, tmp_path: Path) -> None:
        """When over max_instances, oldest non-default instance is evicted."""
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path, max_instances=3)

            async def run() -> None:
                # Start with default
                assert len(router.instances) == 1

                # Create ns1
                await router.get_instance("ns1")
                time.sleep(0.05)

                # Create ns2
                await router.get_instance("ns2")
                time.sleep(0.05)

                # Now at max_instances=3 (default, ns1, ns2)
                assert len(router.instances) == 3
                assert "ns1" in router.instances
                assert "ns2" in router.instances

                # Create ns3 — should trigger eviction of ns1 (oldest non-default)
                await router.get_instance("ns3")

                # ns1 evicted, ns2 and ns3 remain
                assert len(router.instances) == 3
                assert "ns1" not in router.instances
                assert "ns2" in router.instances
                assert "ns3" in router.instances

            asyncio.run(run())

    def test_default_bank_never_evicted(self, tmp_path: Path) -> None:
        """Default memory bank is never evicted, even when over limit."""
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path, max_instances=3)

            async def run() -> None:
                # Fill up to max_instances
                await router.get_instance("ns1")
                await router.get_instance("ns2")
                assert len(router.instances) == 3  # default + ns1 + ns2

                # Keep adding banks — default must survive
                await router.get_instance("ns3")
                await router.get_instance("ns4")
                await router.get_instance("ns5")

                assert "default" in router.instances

            asyncio.run(run())


# ---------------------------------------------------------------------------
# Concurrency — simultaneous requests don't create duplicates
# ---------------------------------------------------------------------------

class TestMemoryBankRouterConcurrency:
    """Simultaneous requests for same memory bank don't create duplicates."""

    def test_simultaneous_requests_same_memory_bank_no_duplicates(self, tmp_path: Path) -> None:
        """Multiple concurrent get_instance calls for same memory bank yield exactly one instance."""
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path, max_instances=10)

            async def run() -> None:
                # Fire 20 concurrent requests for "concurrent-ns"
                tasks = [router.get_instance("concurrent-ns") for _ in range(20)]
                results = await asyncio.gather(*tasks)

                # All results point to the same instance
                assert all(r is results[0] for r in results)

                # Only one entry in instances dict for this memory bank
                assert "concurrent-ns" in router.instances
                assert isinstance(router.instances["concurrent-ns"], object)

            asyncio.run(run())


# ---------------------------------------------------------------------------
# Health integration — get_active_instances and get_active_banks
# ---------------------------------------------------------------------------

class TestMemoryBankRouterHealthIntegration:
    """Router exposes instance count and memory bank list for health endpoint."""

    def test_get_active_instances_returns_count(self, tmp_path: Path) -> None:
        """get_active_instances returns the number of active instances."""
        router = _make_router(tmp_path)
        assert router.get_active_instances() == 1  # default only

    def test_get_active_banks_returns_names(self, tmp_path: Path) -> None:
        """get_active_banks returns memory bank names."""
        router = _make_router(tmp_path)
        banks = router.get_active_banks()
        assert "default" in banks

    def test_health_methods_update_after_creation(self, tmp_path: Path) -> None:
        with patch.object(MemoryBankRouter, "_create_instance", side_effect=lambda mb: _make_mock_client(mb)):
            router = _make_router(tmp_path)

            async def run() -> None:
                await router.get_instance("extra-ns")
                assert router.get_active_instances() == 2
                assert "extra-ns" in router.get_active_banks()

            asyncio.run(run())


# ---------------------------------------------------------------------------
# MemoryBankRegistry wiring
# ---------------------------------------------------------------------------

class TestMemoryBankRouterRegistryWiring:
    """MemoryBankRouter wires MemoryBankRegistry and exposes description methods."""

    def test_router_has_registry_instance(self, tmp_path: Path) -> None:
        """Router creates a MemoryBankRegistry instance in __init__."""
        from src.services.bank.registry import MemoryBankRegistry

        router = _make_router(tmp_path)
        assert hasattr(router, "registry")
        assert isinstance(router.registry, MemoryBankRegistry)

    def test_get_bank_description_for_default(self, tmp_path: Path) -> None:
        """get_bank_description returns default memory bank description immediately."""
        router = _make_router(tmp_path)
        desc = router.get_bank_description("default")
        assert desc is not None
        assert "Default personal memory" in desc

    def test_get_bank_description_for_registered(self, tmp_path: Path) -> None:
        """get_bank_description returns description for a registered memory bank."""
        router = _make_router(tmp_path)
        router.register_bank("project-x", "Project X memories")
        desc = router.get_bank_description("project-x")
        assert desc == "Project X memories"

    def test_get_bank_description_for_unknown(self, tmp_path: Path) -> None:
        """get_bank_description returns None for unregistered memory bank."""
        router = _make_router(tmp_path)
        desc = router.get_bank_description("nonexistent")
        assert desc is None

    def test_register_bank_delegates_to_registry(self, tmp_path: Path) -> None:
        """register_bank method delegates to registry.register()."""
        router = _make_router(tmp_path)
        router.register_bank("new-ns", "New bank description")
        assert router.registry.get("new-ns") == "New bank description"

    def test_register_bank_idempotent(self, tmp_path: Path) -> None:
        """register_bank is idempotent — calling twice updates description."""
        router = _make_router(tmp_path)
        router.register_bank("ns1", "first")
        assert router.get_bank_description("ns1") == "first"
        router.register_bank("ns1", "second")
        assert router.get_bank_description("ns1") == "second"
