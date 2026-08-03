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
    """Tool schemas include namespace parameter as required (no default)."""

    def test_remember_schema_namespace_required_no_default(self) -> None:
        from src.services.tools.schemas import REMEMBER_SCHEMA

        params = REMEMBER_SCHEMA["parameters"]["properties"]
        assert "namespace" in params
        assert "default" not in params["namespace"]
        assert "namespace" in REMEMBER_SCHEMA["parameters"]["required"]

    def test_recall_schema_namespace_required_no_default(self) -> None:
        from src.services.tools.schemas import RECALL_SCHEMA

        params = RECALL_SCHEMA["parameters"]["properties"]
        assert "namespace" in params
        assert "default" not in params["namespace"]
        assert "namespace" in RECALL_SCHEMA["parameters"]["required"]

    def test_forget_schema_namespace_required_no_default(self) -> None:
        from src.services.tools.schemas import FORGET_SCHEMA

        params = FORGET_SCHEMA["parameters"]["properties"]
        assert "namespace" in params
        assert "default" not in params["namespace"]
        assert "namespace" in FORGET_SCHEMA["parameters"]["required"]

    def test_update_schema_namespace_required_no_default(self) -> None:
        from src.services.tools.schemas import UPDATE_SCHEMA

        params = UPDATE_SCHEMA["parameters"]["properties"]
        assert "namespace" in params
        assert "default" not in params["namespace"]
        assert "namespace" in UPDATE_SCHEMA["parameters"]["required"]

    def test_sleep_schema_namespace_required_no_default(self) -> None:
        from src.services.tools.schemas import SLEEP_SCHEMA

        params = SLEEP_SCHEMA["parameters"]["properties"]
        assert "namespace" in params
        assert "default" not in params["namespace"]
        assert "namespace" in SLEEP_SCHEMA["parameters"]["required"]

    def test_stats_schema_namespace_required_no_default(self) -> None:
        from src.services.tools.schemas import STATS_SCHEMA

        params = STATS_SCHEMA["parameters"]["properties"]
        assert "namespace" in params
        assert "default" not in params["namespace"]
        assert "namespace" in STATS_SCHEMA["parameters"]["required"]

    def test_namespace_param_description_says_required(self) -> None:
        from src.services.tools.schemas import NAMESPACE_PARAM

        assert "required" in NAMESPACE_PARAM["namespace"]["description"].lower()

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

    def test_remember_raises_validation_error_without_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_remember

        async def run() -> None:
            with pytest.raises(ValidationError, match="namespace parameter is required"):
                await handle_remember(router, {"content": "test memory"})

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

    def test_recall_raises_validation_error_without_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_recall

        async def run() -> None:
            with pytest.raises(ValidationError, match="namespace parameter is required"):
                await handle_recall(router, {"query": "test"})

        asyncio.run(run())

    def test_recall_raises_validation_error_without_query(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_recall

        async def run() -> None:
            with pytest.raises(ValidationError, match="query is required"):
                await handle_recall(router, {"namespace": "test-ns"})

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

    def test_forget_raises_validation_error_without_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_forget

        async def run() -> None:
            with pytest.raises(ValidationError, match="namespace parameter is required"):
                await handle_forget(router, {"memory_id": "mem_abc123"})

        asyncio.run(run())

    def test_forget_raises_validation_error_without_memory_id(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_forget

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_id is required"):
                await handle_forget(router, {"namespace": "test-ns"})

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

    def test_update_raises_validation_error_without_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_update

        async def run() -> None:
            with pytest.raises(ValidationError, match="namespace parameter is required"):
                await handle_update(router, {"memory_id": "mem_abc123", "importance": 0.9})

        asyncio.run(run())

    def test_update_raises_validation_error_without_memory_id(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_update

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_id is required"):
                await handle_update(router, {"namespace": "test-ns"})

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

    def test_sleep_raises_validation_error_without_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_sleep

        async def run() -> None:
            with pytest.raises(ValidationError, match="namespace parameter is required"):
                await handle_sleep(router, {})

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

    def test_stats_raises_validation_error_without_namespace(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_stats

        async def run() -> None:
            with pytest.raises(ValidationError, match="namespace parameter is required"):
                await handle_stats(router, {})

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

    def test_list_namespaces_includes_description_from_registry(self, router: NamespaceRouter) -> None:
        """Each namespace entry includes description field from registry."""
        from src.services.tools.handlers import handle_list_namespaces

        async def run() -> None:
            # Register a custom namespace description
            router.register_namespace("custom-ns", "My custom description")
            await router.get_instance("custom-ns")

            result = await handle_list_namespaces(router, {})

            # Find entries
            default_ns = next(ns for ns in result["namespaces"] if ns["name"] == "default")
            custom_ns = next(ns for ns in result["namespaces"] if ns["name"] == "custom-ns")

            # Default has hardcoded description
            assert "description" in default_ns
            assert default_ns["description"] == "Default personal memory — general conversation context, preferences, and facts"

            # Custom has registered description
            assert "description" in custom_ns
            assert custom_ns["description"] == "My custom description"

        asyncio.run(run())

    def test_list_namespaces_includes_memory_count_from_stats(self, router: NamespaceRouter) -> None:
        """Each namespace entry includes memory_count from client.stats()."""
        from src.services.tools.handlers import handle_list_namespaces

        async def run() -> None:
            # Mock stats returns working + episodic counts
            router._mock_instance.get_stats.return_value = {"working": 10, "episodic": 5}

            await router.get_instance("counted-ns")

            result = await handle_list_namespaces(router, {})

            counted_ns = next(ns for ns in result["namespaces"] if ns["name"] == "counted-ns")

            assert "memory_count" in counted_ns
            assert counted_ns["memory_count"] == 15

        asyncio.run(run())

    def test_list_namespaces_memory_count_handles_missing_keys(self, router: NamespaceRouter) -> None:
        """memory_count sums available keys, handles missing working/episodic gracefully."""
        from src.services.tools.handlers import handle_list_namespaces

        async def run() -> None:
            # Stats with different key names or missing keys
            router._mock_instance.get_stats.return_value = {"total": 42}

            await router.get_instance("sparse-ns")

            result = await handle_list_namespaces(router, {})

            sparse_ns = next(ns for ns in result["namespaces"] if ns["name"] == "sparse-ns")

            # Should not crash, memory_count should be 0 when expected keys missing
            assert "memory_count" in sparse_ns
            assert isinstance(sparse_ns["memory_count"], int)

        asyncio.run(run())

    def test_list_namespaces_response_shape_has_all_required_fields(self, router: NamespaceRouter) -> None:
        """Response shape: {namespaces: [{name, bank, description, memory_count}, ...]}."""
        from src.services.tools.handlers import handle_list_namespaces

        async def run() -> None:
            await router.get_instance("shape-ns")

            result = await handle_list_namespaces(router, {})

            assert "namespaces" in result
            assert isinstance(result["namespaces"], list)

            for ns in result["namespaces"]:
                assert "name" in ns
                assert isinstance(ns["name"], str)
                assert "bank" in ns
                assert isinstance(ns["bank"], str)
                assert "description" in ns
                assert isinstance(ns["description"], str)
                assert "memory_count" in ns
                assert isinstance(ns["memory_count"], int)

        asyncio.run(run())

    def test_list_namespaces_default_always_appears_with_hardcoded_description(self, router: NamespaceRouter) -> None:
        """Default namespace always appears with its hardcoded description."""
        from src.services.tools.handlers import handle_list_namespaces

        async def run() -> None:
            result = await handle_list_namespaces(router, {})

            default_ns = next(ns for ns in result["namespaces"] if ns["name"] == "default")

            assert default_ns["description"] == "Default personal memory — general conversation context, preferences, and facts"

        asyncio.run(run())

    def test_list_namespaces_unregistered_namespace_has_none_description(self, router: NamespaceRouter) -> None:
        """Namespaces without registered description show None or empty description."""
        from src.services.tools.handlers import handle_list_namespaces

        async def run() -> None:
            # Create instance without registering description
            await router.get_instance("unregistered-ns")

            result = await handle_list_namespaces(router, {})

            unreg_ns = next(ns for ns in result["namespaces"] if ns["name"] == "unregistered-ns")

            # Should have description field (None or empty string acceptable)
            assert "description" in unreg_ns

        asyncio.run(run())


class TestRegisterNamespaceSchema:
    """register_namespace schema has name and description as required fields."""

    def test_register_namespace_schema_exists(self) -> None:
        from src.services.tools.schemas import REGISTER_NAMESPACE_SCHEMA

        assert REGISTER_NAMESPACE_SCHEMA is not None

    def test_register_namespace_schema_has_correct_name(self) -> None:
        from src.services.tools.schemas import REGISTER_NAMESPACE_SCHEMA

        assert REGISTER_NAMESPACE_SCHEMA["name"] == "mnemosyne_register_namespace"

    def test_register_namespace_schema_has_description(self) -> None:
        from src.services.tools.schemas import REGISTER_NAMESPACE_SCHEMA

        assert "description" in REGISTER_NAMESPACE_SCHEMA
        assert len(REGISTER_NAMESPACE_SCHEMA["description"]) > 0

    def test_register_namespace_schema_has_name_parameter(self) -> None:
        from src.services.tools.schemas import REGISTER_NAMESPACE_SCHEMA

        params = REGISTER_NAMESPACE_SCHEMA["parameters"]["properties"]
        assert "name" in params
        assert params["name"]["type"] == "string"

    def test_register_namespace_schema_has_description_parameter(self) -> None:
        from src.services.tools.schemas import REGISTER_NAMESPACE_SCHEMA

        params = REGISTER_NAMESPACE_SCHEMA["parameters"]["properties"]
        assert "description" in params
        assert params["description"]["type"] == "string"

    def test_register_namespace_schema_requires_name_and_description(self) -> None:
        from src.services.tools.schemas import REGISTER_NAMESPACE_SCHEMA

        required = REGISTER_NAMESPACE_SCHEMA["parameters"]["required"]
        assert "name" in required
        assert "description" in required

    def test_register_namespace_schema_in_all_tool_schemas(self) -> None:
        from src.services.tools.schemas import ALL_TOOL_SCHEMAS, REGISTER_NAMESPACE_SCHEMA

        assert REGISTER_NAMESPACE_SCHEMA in ALL_TOOL_SCHEMAS


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

    def test_namespace_required_no_fallback_to_default(self, router: NamespaceRouter) -> None:
        """All handlers raise ValidationError when namespace not provided (no fallback)."""
        from src.services.tools.handlers import (
            handle_remember,
            handle_recall,
            handle_forget,
            handle_update,
            handle_sleep,
            handle_stats,
        )

        async def run() -> None:
            with pytest.raises(ValidationError, match="namespace parameter is required"):
                await handle_remember(router, {"content": "x"})
            with pytest.raises(ValidationError, match="namespace parameter is required"):
                await handle_recall(router, {"query": "x"})
            with pytest.raises(ValidationError, match="namespace parameter is required"):
                await handle_forget(router, {"memory_id": "x"})
            with pytest.raises(ValidationError, match="namespace parameter is required"):
                await handle_update(router, {"memory_id": "x"})
            with pytest.raises(ValidationError, match="namespace parameter is required"):
                await handle_sleep(router, {})
            with pytest.raises(ValidationError, match="namespace parameter is required"):
                await handle_stats(router, {})

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Register Namespace handler
# ---------------------------------------------------------------------------


class TestHandleRegisterNamespace:
    """register_namespace handler validates args and registers via router."""

    def test_register_namespace_success(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_register_namespace

        async def run() -> None:
            result = await handle_register_namespace(
                router,
                {"name": "my-ns", "description": "My custom namespace"},
            )

            assert result["status"] == "registered"
            assert result["name"] == "my-ns"
            # Verify registry was updated
            assert router.registry.get("my-ns") == "My custom namespace"

        asyncio.run(run())

    def test_register_namespace_idempotent_updates_description(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_register_namespace

        async def run() -> None:
            # First registration
            await handle_register_namespace(
                router,
                {"name": "my-ns", "description": "Original description"},
            )
            assert router.registry.get("my-ns") == "Original description"

            # Second registration with same name updates description
            result = await handle_register_namespace(
                router,
                {"name": "my-ns", "description": "Updated description"},
            )
            assert result["status"] == "registered"
            assert result["name"] == "my-ns"
            assert router.registry.get("my-ns") == "Updated description"

        asyncio.run(run())

    def test_register_namespace_raises_when_name_missing(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_register_namespace

        async def run() -> None:
            with pytest.raises(ValidationError, match="name is required"):
                await handle_register_namespace(router, {"description": "no name"})

        asyncio.run(run())

    def test_register_namespace_raises_when_description_missing(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_register_namespace

        async def run() -> None:
            with pytest.raises(ValidationError, match="description is required"):
                await handle_register_namespace(router, {"name": "no-desc"})

        asyncio.run(run())

    def test_register_namespace_raises_when_both_missing(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_register_namespace

        async def run() -> None:
            with pytest.raises(ValidationError, match="name is required"):
                await handle_register_namespace(router, {})

        asyncio.run(run())

    def test_register_namespace_returns_correct_shape(self, router: NamespaceRouter) -> None:
        from src.services.tools.handlers import handle_register_namespace

        async def run() -> None:
            result = await handle_register_namespace(
                router,
                {"name": "test-ns", "description": "Test"},
            )

            assert set(result.keys()) == {"status", "name"}
            assert isinstance(result["status"], str)
            assert isinstance(result["name"], str)

        asyncio.run(run())
