"""MCP tool handlers tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.domain.exceptions import ValidationError
from src.domain.models import InstancePoolConfig
from src.infrastructure.mnemosyne.bank_manager import BankManager
from src.services.namespace.router import NamespaceRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_mnemosyne_instance() -> MagicMock:
    """Create a fully configured mock Mnemosyne instance."""
    mock = MagicMock()
    mock.remember.return_value = "mem_abc123"
    mock.recall.return_value = [
        {"id": "mem_abc123", "content": "test memory", "score": 0.9}
    ]
    mock.forget.return_value = True
    mock.update.return_value = True
    mock.sleep.return_value = {"status": "ok", "consolidated": 0}
    mock.get_stats.return_value = {"working": 5, "episodic": 2}
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


@pytest.fixture
def router(tmp_path: Path) -> NamespaceRouter:
    """Create a NamespaceRouter with mocked mnemosyne — patch persists across tests."""
    mock_instance = _mock_mnemosyne_instance()

    # Patch mnemosyne.core.memory.Mnemosyne class directly in sys.modules
    # so lazy import in client.py always returns our mock
    with patch.dict(
        "sys.modules",
        {
            "mnemosyne": MagicMock(),
            "mnemosyne.core": MagicMock(),
            "mnemosyne.core.memory": MagicMock(
                Mnemosyne=lambda **kwargs: mock_instance
            ),
        },
    ):
        config = InstancePoolConfig(
            max_instances=5,
            eviction_timeout=300,
            data_dir=str(tmp_path),
            default_bank="default",
        )
        bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
        router = NamespaceRouter(config=config, bank_manager=bank_manager)
        router._mock_instance = mock_instance  # expose for test assertions
        yield router


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------


class TestToolSchemas:
    """Tool schemas include namespace parameter (default: 'default')."""

    def test_remember_schema_has_namespace_param(self) -> None:
        from src.services.tools.schemas import REMEMBER_SCHEMA

        params = REMEMBER_SCHEMA["parameters"]["properties"]
        assert "namespace" in params
        assert params["namespace"]["default"] == "default"

    def test_recall_schema_has_namespace_param(self) -> None:
        from src.services.tools.schemas import RECALL_SCHEMA

        params = RECALL_SCHEMA["parameters"]["properties"]
        assert "namespace" in params
        assert params["namespace"]["default"] == "default"

    def test_forget_schema_has_namespace_param(self) -> None:
        from src.services.tools.schemas import FORGET_SCHEMA

        params = FORGET_SCHEMA["parameters"]["properties"]
        assert "namespace" in params
        assert params["namespace"]["default"] == "default"

    def test_update_schema_has_namespace_param(self) -> None:
        from src.services.tools.schemas import UPDATE_SCHEMA

        params = UPDATE_SCHEMA["parameters"]["properties"]
        assert "namespace" in params
        assert params["namespace"]["default"] == "default"

    def test_sleep_schema_has_namespace_param(self) -> None:
        from src.services.tools.schemas import SLEEP_SCHEMA

        params = SLEEP_SCHEMA["parameters"]["properties"]
        assert "namespace" in params
        assert params["namespace"]["default"] == "default"

    def test_stats_schema_has_namespace_param(self) -> None:
        from src.services.tools.schemas import STATS_SCHEMA

        params = STATS_SCHEMA["parameters"]["properties"]
        assert "namespace" in params
        assert params["namespace"]["default"] == "default"

    def test_list_namespaces_schema_no_namespace_param(self) -> None:
        from src.services.tools.schemas import LIST_NAMESPACES_SCHEMA

        params = LIST_NAMESPACES_SCHEMA["parameters"]["properties"]
        assert "namespace" not in params


# ---------------------------------------------------------------------------
# Remember handler
# ---------------------------------------------------------------------------


class TestHandleRemember:
    """remember handler stores to correct namespace bank."""

    def test_remember_stores_to_correct_namespace_bank(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_remember

        async def run() -> None:
            result = await handle_remember(router, {"content": "test memory", "namespace": "test-ns"})

            assert result["status"] == "stored"
            assert result["memory_id"] == "mem_abc123"
            assert result["namespace"] == "test-ns"
            assert "test-ns" in router.instances

        asyncio.run(run())

    def test_remember_falls_back_to_default_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_remember

        async def run() -> None:
            result = await handle_remember(router, {"content": "test memory"})

            assert result["status"] == "stored"
            assert result["namespace"] == "default"

        asyncio.run(run())

    def test_remember_raises_validation_error_without_content(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_remember

        async def run() -> None:
            with pytest.raises(ValidationError, match="content is required"):
                await handle_remember(router, {"namespace": "test-ns"})

        asyncio.run(run())

    def test_remember_passes_extra_params(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_remember

        async def run() -> None:
            await handle_remember(
                router,
                {
                    "content": "test",
                    "namespace": "test-ns",
                    "importance": 0.8,
                    "source": "user",
                },
            )

            client = router.instances["test-ns"]
            client._instance.remember.assert_called_once()
            call_kwargs = client._instance.remember.call_args.kwargs
            assert call_kwargs["importance"] == 0.8
            assert call_kwargs["source"] == "user"

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Recall handler
# ---------------------------------------------------------------------------


class TestHandleRecall:
    """recall handler queries correct namespace bank."""

    def test_recall_queries_correct_namespace_bank(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_recall

        async def run() -> None:
            result = await handle_recall(router, {"query": "test", "namespace": "test-ns"})

            assert result["namespace"] == "test-ns"
            assert len(result["results"]) == 1
            assert result["results"][0]["id"] == "mem_abc123"
            assert "test-ns" in router.instances

        asyncio.run(run())

    def test_recall_falls_back_to_default_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_recall

        async def run() -> None:
            result = await handle_recall(router, {"query": "test"})

            assert result["namespace"] == "default"

        asyncio.run(run())

    def test_recall_raises_validation_error_without_query(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_recall

        async def run() -> None:
            with pytest.raises(ValidationError, match="query is required"):
                await handle_recall(router, {})

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Forget handler
# ---------------------------------------------------------------------------


class TestHandleForget:
    """forget handler deletes from correct namespace bank."""

    def test_forget_deletes_from_correct_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_forget

        async def run() -> None:
            result = await handle_forget(router, {"memory_id": "mem_abc123", "namespace": "test-ns"})

            assert result["status"] == "deleted"
            assert result["memory_id"] == "mem_abc123"
            assert result["namespace"] == "test-ns"

        asyncio.run(run())

    def test_forget_falls_back_to_default_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_forget

        async def run() -> None:
            result = await handle_forget(router, {"memory_id": "mem_abc123"})

            assert result["namespace"] == "default"

        asyncio.run(run())

    def test_forget_raises_validation_error_without_memory_id(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_forget

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_id is required"):
                await handle_forget(router, {})

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Update handler
# ---------------------------------------------------------------------------


class TestHandleUpdate:
    """update handler updates in correct namespace bank."""

    def test_update_updates_in_correct_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_update

        async def run() -> None:
            result = await handle_update(
                router,
                {"memory_id": "mem_abc123", "content": "updated", "namespace": "test-ns"},
            )

            assert result["status"] == "updated"
            assert result["namespace"] == "test-ns"

        asyncio.run(run())

    def test_update_falls_back_to_default_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_update

        async def run() -> None:
            result = await handle_update(router, {"memory_id": "mem_abc123", "importance": 0.9})

            assert result["namespace"] == "default"

        asyncio.run(run())

    def test_update_raises_validation_error_without_memory_id(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_update

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_id is required"):
                await handle_update(router, {})

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Sleep handler
# ---------------------------------------------------------------------------


class TestHandleSleep:
    """sleep handler consolidates in correct namespace bank."""

    def test_sleep_consolidates_in_correct_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_sleep

        async def run() -> None:
            result = await handle_sleep(router, {"namespace": "test-ns"})

            assert result["namespace"] == "test-ns"
            assert result["status"] == "ok"

        asyncio.run(run())

    def test_sleep_falls_back_to_default_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_sleep

        async def run() -> None:
            result = await handle_sleep(router, {})

            assert result["namespace"] == "default"

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Stats handler
# ---------------------------------------------------------------------------


class TestHandleStats:
    """stats handler returns stats from correct namespace bank."""

    def test_stats_returns_from_correct_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_stats

        async def run() -> None:
            result = await handle_stats(router, {"namespace": "test-ns"})

            assert result["namespace"] == "test-ns"
            assert result["stats"]["working"] == 5

        asyncio.run(run())

    def test_stats_falls_back_to_default_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_stats

        async def run() -> None:
            result = await handle_stats(router, {})

            assert result["namespace"] == "default"

        asyncio.run(run())


# ---------------------------------------------------------------------------
# List Namespaces handler
# ---------------------------------------------------------------------------


class TestHandleListNamespaces:
    """list_namespaces returns all active namespaces."""

    def test_list_namespaces_returns_all_active_namespaces(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_list_namespaces

        async def run() -> None:
            # Pre-create some instances
            await router.get_instance("ns1")
            await router.get_instance("ns2")

            result = await handle_list_namespaces(router, {})

            assert len(result["namespaces"]) == 3
            names = {ns["name"] for ns in result["namespaces"]}
            assert names == {"default", "ns1", "ns2"}

            # Each entry has required fields
            for ns in result["namespaces"]:
                assert "name" in ns
                assert "bank" in ns
                assert "status" in ns
                assert "memory_count" in ns

        asyncio.run(run())

    def test_list_namespaces_no_namespace_param_needed(self) -> None:
        from src.services.tools.schemas import LIST_NAMESPACES_SCHEMA

        # Schema should not require namespace parameter
        params = LIST_NAMESPACES_SCHEMA["parameters"]
        assert params["type"] == "object"
        assert "namespace" not in params.get("properties", {})


# ---------------------------------------------------------------------------
# Integration: full tool call round-trip via MCP protocol
# ---------------------------------------------------------------------------


class TestToolCallIntegration:
    """Full tool call round-trip via MCP protocol."""

    @pytest.fixture
    def router(self, tmp_path: Path) -> NamespaceRouter:
        mock_instance = _mock_mnemosyne_instance()

        with patch.dict(
            "sys.modules",
            {
                "mnemosyne": MagicMock(),
                "mnemosyne.core": MagicMock(),
                "mnemosyne.core.memory": MagicMock(
                    Mnemosyne=lambda **kwargs: mock_instance
                ),
            },
        ):
            config = InstancePoolConfig(
                max_instances=10,
                eviction_timeout=300,
                data_dir=str(tmp_path),
                default_bank="default",
            )
            bank_manager = BankManager(data_dir=str(tmp_path), default_bank="default")
            router = NamespaceRouter(config=config, bank_manager=bank_manager)
            router._mock_instance = mock_instance
            yield router

    def test_full_remember_recall_round_trip(self, router: NamespaceRouter) -> None:
        """Remember then recall in same namespace returns the memory."""
        from src.services.tools.handlers import handle_remember, handle_recall

        async def run() -> None:
            # Remember
            remember_result = await handle_remember(
                router,
                {"content": "user prefers dark mode", "namespace": "user-123"},
            )
            assert remember_result["status"] == "stored"
            assert remember_result["namespace"] == "user-123"

            # Recall
            recall_result = await handle_recall(
                router,
                {"query": "dark mode", "namespace": "user-123"},
            )
            assert recall_result["namespace"] == "user-123"
            assert len(recall_result["results"]) == 1

        asyncio.run(run())

    def test_namespace_isolation_between_remember_and_recall(
        self, router: NamespaceRouter
    ) -> None:
        """Memories stored in one namespace are not visible in another."""
        from src.services.tools.handlers import handle_remember

        async def run() -> None:
            # Store in ns-a
            await handle_remember(router, {"content": "ns-a secret", "namespace": "ns-a"})

            # Store in ns-b
            await handle_remember(router, {"content": "ns-b secret", "namespace": "ns-b"})

            # Verify different clients per namespace
            assert router.instances["ns-a"] is not router.instances["ns-b"]

        asyncio.run(run())

    def test_mcp_response_format_matches_spec(self, router: NamespaceRouter) -> None:
        """Response format matches MCP spec with namespace field included."""
        from src.services.tools.handlers import (
            handle_remember,
            handle_recall,
            handle_forget,
            handle_update,
            handle_sleep,
            handle_stats,
        )

        async def run() -> None:
            # remember response
            r = await handle_remember(router, {"content": "test", "namespace": "spec-ns"})
            assert "status" in r
            assert "memory_id" in r
            assert "namespace" in r
            assert isinstance(r["status"], str)
            assert isinstance(r["memory_id"], str)
            assert isinstance(r["namespace"], str)

            # recall response
            r = await handle_recall(router, {"query": "test", "namespace": "spec-ns"})
            assert "results" in r
            assert "namespace" in r
            assert isinstance(r["results"], list)

            # forget response
            r = await handle_forget(router, {"memory_id": "x", "namespace": "spec-ns"})
            assert "status" in r
            assert "memory_id" in r
            assert "namespace" in r

            # update response
            r = await handle_update(router, {"memory_id": "x", "namespace": "spec-ns"})
            assert "status" in r
            assert "memory_id" in r
            assert "namespace" in r

            # sleep response
            r = await handle_sleep(router, {"namespace": "spec-ns"})
            assert "namespace" in r

            # stats response
            r = await handle_stats(router, {"namespace": "spec-ns"})
            assert "stats" in r
            assert "namespace" in r

        asyncio.run(run())

    def test_namespace_fallback_to_default_when_not_provided(self, router: NamespaceRouter) -> None:
        """All handlers fall back to 'default' namespace when not provided."""
        from src.services.tools.handlers import (
            handle_remember,
            handle_recall,
            handle_forget,
            handle_update,
            handle_sleep,
            handle_stats,
        )

        async def run() -> None:
            assert (await handle_remember(router, {"content": "x"}))["namespace"] == "default"
            assert (await handle_recall(router, {"query": "x"}))["namespace"] == "default"
            assert (await handle_forget(router, {"memory_id": "x"}))["namespace"] == "default"
            assert (await handle_update(router, {"memory_id": "x"}))["namespace"] == "default"
            assert (await handle_sleep(router, {}))["namespace"] == "default"
            assert (await handle_stats(router, {}))["namespace"] == "default"

        asyncio.run(run())
