"""Namespace router and instance pool tests."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest

from src.domain.models import InstancePoolConfig
from src.infrastructure.mnemosyne.bank_manager import BankManager
from src.services.namespace.router import NamespaceRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_mnemosyne_instance() -> MagicMock:
    """Create a fully configured mock Mnemosyne instance."""
    mock = MagicMock()
    mock.remember.return_value = "mem_abc"
    mock.recall.return_value = []
    mock.forget.return_value = True
    mock.update.return_value = True
    mock.sleep.return_value = {"status": "ok"}
    mock.get_stats.return_value = {"working": 0, "episodic": 0}
    mock.get.return_value = None
    return mock


def _patch_mnemosyne_class(mock_instance: MagicMock) -> Any:
    """Context manager that patches mnemosyne.core.memory.Mnemosyne."""
    return patch.dict(
        "sys.modules",
        {
            "mnemosyne": MagicMock(),
            "mnemosyne.core": MagicMock(),
            "mnemosyne.core.memory": MagicMock(Mnemosyne=MagicMock(return_value=mock_instance)),
        },
    )


# ---------------------------------------------------------------------------
# NamespaceRouter creation and default instance
# ---------------------------------------------------------------------------


class TestNamespaceRouterCreation:
    """NamespaceRouter initializes with default instance at boot."""

    @pytest.fixture
    def router(self, tmp_path: Path) -> NamespaceRouter:
        mock_instance = _mock_mnemosyne_instance()
        with _patch_mnemosyne_class(mock_instance):
            config = InstancePoolConfig(
                max_instances=5,
                eviction_timeout=300,
                data_dir=str(tmp_path),
                default_bank="default",
            )
            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            return NamespaceRouter(config=config, bank_manager=bank_manager)

    def test_default_instance_created_at_boot(self, router: NamespaceRouter) -> None:
        """Default instance exists immediately after router creation."""
        assert "default" in router.instances

    def test_default_instance_is_mnemosyne_client(self, router: NamespaceRouter) -> None:
        """Default instance is a MnemosyneClient."""
        from src.infrastructure.mnemosyne.client import MnemosyneClient

        assert isinstance(router.instances["default"], MnemosyneClient)

    def test_default_instance_namespace(self, router: NamespaceRouter) -> None:
        """Default instance has namespace 'default'."""
        assert router.instances["default"].namespace == "default"


# ---------------------------------------------------------------------------
# get_instance — caching and creation
# ---------------------------------------------------------------------------


class TestNamespaceRouterGetInstance:
    """NamespaceRouter.get_instance returns cached instance on second call."""

    @pytest.fixture
    def router(self, tmp_path: Path) -> NamespaceRouter:
        mock_instance = _mock_mnemosyne_instance()
        with _patch_mnemosyne_class(mock_instance):
            config = InstancePoolConfig(
                max_instances=5,
                eviction_timeout=300,
                data_dir=str(tmp_path),
                default_bank="default",
            )
            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            return NamespaceRouter(config=config, bank_manager=bank_manager)

    def test_get_instance_returns_cached_instance_on_second_call(self, router: NamespaceRouter) -> None:
        """Second call for same namespace returns the same instance."""

        async def run() -> None:
            first = await router.get_instance("default")
            second = await router.get_instance("default")
            assert first is second

        asyncio.run(run())

    def test_new_instance_created_for_new_namespace(self, router: NamespaceRouter, tmp_path: Path) -> None:
        """First call for a new namespace creates a new instance."""

        async def run() -> None:
            # Before: only default exists
            assert len(router.instances) == 1

            # First call for "test-ns" creates instance
            instance = await router.get_instance("test-ns")

            # Now both exist
            assert "test-ns" in router.instances
            assert len(router.instances) == 2
            assert instance.namespace == "test-ns"

        asyncio.run(run())

    def test_get_instance_updates_last_accessed(self, router: NamespaceRouter) -> None:
        """get_instance updates last_accessed timestamp."""

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


class TestNamespaceRouterLRUEviction:
    """LRU eviction works at max_instances limit."""

    @pytest.fixture
    def router(self, tmp_path: Path) -> NamespaceRouter:
        """Router with max_instances=3 (default + 2 allowed)."""
        mock_instance = _mock_mnemosyne_instance()
        with _patch_mnemosyne_class(mock_instance):
            config = InstancePoolConfig(
                max_instances=3,
                eviction_timeout=300,
                data_dir=str(tmp_path),
                default_bank="default",
            )
            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            return NamespaceRouter(config=config, bank_manager=bank_manager)

    def test_lru_eviction_works_at_max_instances_limit(self, router: NamespaceRouter) -> None:
        """When over max_instances, oldest non-default instance is evicted."""

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

    def test_default_namespace_never_evicted(self, router: NamespaceRouter) -> None:
        """Default namespace is never evicted, even when over limit."""

        async def run() -> None:
            # Fill up to max_instances
            await router.get_instance("ns1")
            await router.get_instance("ns2")
            assert len(router.instances) == 3  # default + ns1 + ns2

            # Keep adding namespaces — default must survive
            await router.get_instance("ns3")
            await router.get_instance("ns4")
            await router.get_instance("ns5")

            assert "default" in router.instances

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Concurrency — simultaneous requests don't create duplicates
# ---------------------------------------------------------------------------


class TestNamespaceRouterConcurrency:
    """Simultaneous requests for same namespace don't create duplicates."""

    @pytest.fixture
    def router(self, tmp_path: Path) -> NamespaceRouter:
        mock_instance = _mock_mnemosyne_instance()
        with _patch_mnemosyne_class(mock_instance):
            config = InstancePoolConfig(
                max_instances=10,
                eviction_timeout=300,
                data_dir=str(tmp_path),
                default_bank="default",
            )
            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            return NamespaceRouter(config=config, bank_manager=bank_manager)

    def test_simultaneous_requests_same_namespace_no_duplicates(self, router: NamespaceRouter) -> None:
        """Multiple concurrent get_instance calls for same namespace yield exactly one instance."""

        async def run() -> None:
            # Fire 20 concurrent requests for "concurrent-ns"
            tasks = [router.get_instance("concurrent-ns") for _ in range(20)]
            results = await asyncio.gather(*tasks)

            # All results point to the same instance
            assert all(r is results[0] for r in results)

            # Only one entry in instances dict for this namespace
            assert "concurrent-ns" in router.instances
            assert isinstance(router.instances["concurrent-ns"], object)

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Health integration — get_active_instances and get_active_namespaces
# ---------------------------------------------------------------------------


class TestNamespaceRouterHealthIntegration:
    """Router exposes instance count and namespace list for health endpoint."""

    @pytest.fixture
    def router(self, tmp_path: Path) -> NamespaceRouter:
        mock_instance = _mock_mnemosyne_instance()
        with _patch_mnemosyne_class(mock_instance):
            config = InstancePoolConfig(
                max_instances=5,
                eviction_timeout=300,
                data_dir=str(tmp_path),
                default_bank="default",
            )
            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            return NamespaceRouter(config=config, bank_manager=bank_manager)

    def test_get_active_instances_returns_count(self, router: NamespaceRouter) -> None:
        """get_active_instances returns the number of active instances."""
        assert router.get_active_instances() == 1  # default only

    def test_get_active_namespaces_returns_names(self, router: NamespaceRouter) -> None:
        """get_active_namespaces returns namespace names."""
        namespaces = router.get_active_namespaces()
        assert "default" in namespaces

    def test_health_methods_update_after_creation(self, router: NamespaceRouter) -> None:

        async def run() -> None:
            await router.get_instance("extra-ns")
            assert router.get_active_instances() == 2
            assert "extra-ns" in router.get_active_namespaces()

        asyncio.run(run())


# ---------------------------------------------------------------------------
# NamespaceRegistry wiring — Task 3
# ---------------------------------------------------------------------------


class TestNamespaceRouterRegistryWiring:
    """NamespaceRouter wires NamespaceRegistry and exposes description methods."""

    @pytest.fixture
    def router(self, tmp_path: Path) -> NamespaceRouter:
        mock_instance = _mock_mnemosyne_instance()
        with _patch_mnemosyne_class(mock_instance):
            config = InstancePoolConfig(
                max_instances=5,
                eviction_timeout=300,
                data_dir=str(tmp_path),
                default_bank="default",
            )
            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            return NamespaceRouter(config=config, bank_manager=bank_manager)

    def test_router_has_registry_instance(self, router: NamespaceRouter) -> None:
        """Router creates a NamespaceRegistry instance in __init__."""
        from src.services.namespace.registry import NamespaceRegistry

        assert hasattr(router, "registry")
        assert isinstance(router.registry, NamespaceRegistry)

    def test_get_namespace_description_for_default(self, router: NamespaceRouter) -> None:
        """get_namespace_description returns default namespace description immediately."""
        desc = router.get_namespace_description("default")
        assert desc is not None
        assert "Default personal memory" in desc

    def test_get_namespace_description_for_registered(self, router: NamespaceRouter) -> None:
        """get_namespace_description returns description for a registered namespace."""
        router.register_namespace("project-x", "Project X memories")
        desc = router.get_namespace_description("project-x")
        assert desc == "Project X memories"

    def test_get_namespace_description_for_unknown(self, router: NamespaceRouter) -> None:
        """get_namespace_description returns None for unregistered namespace."""
        desc = router.get_namespace_description("nonexistent")
        assert desc is None

    def test_register_namespace_delegates_to_registry(self, router: NamespaceRouter) -> None:
        """register_namespace method delegates to registry.register()."""
        router.register_namespace("new-ns", "New namespace description")
        assert router.registry.get("new-ns") == "New namespace description"

    def test_register_namespace_idempotent(self, router: NamespaceRouter) -> None:
        """register_namespace is idempotent — calling twice updates description."""
        router.register_namespace("ns1", "first")
        assert router.get_namespace_description("ns1") == "first"
        router.register_namespace("ns1", "second")
        assert router.get_namespace_description("ns1") == "second"
