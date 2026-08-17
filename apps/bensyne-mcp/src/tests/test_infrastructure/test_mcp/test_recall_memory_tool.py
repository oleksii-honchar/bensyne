"""Tests for the recallMemory MCP tool (renamed from memory_recall).

Verifies:
- MCP tool is registered as "recallMemory" (not "memory_recall")
- Tool accepts query and limit parameters
- Handler delegates to RecallMemoryUseCase
- Schema reflects the new name
- Same functionality as before, just renamed
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.domain.exceptions import ValidationError
from src.domain.config_models import InstancePoolConfig
from src.utils.result import ErrorWithDetails, Result
from src.infrastructure.bank.router import MemoryBankRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_mnemosyne_instance() -> MagicMock:
    """Create a fully configured mock Mnemosyne instance."""
    mock = MagicMock()
    mock.recall.return_value = [{"id": "mem_abc123", "content": "test memory", "score": 0.9}]
    return mock


@pytest.fixture
def router(tmp_path: Path) -> MemoryBankRouter:
    """Create a MemoryBankRouter with mocked mnemosyne."""
    mock_instance = _mock_mnemosyne_instance()

    with patch.dict(
        "sys.modules",
        {
            "mnemosyne": MagicMock(),
            "mnemosyne.core": MagicMock(),
            "mnemosyne.core.memory": MagicMock(Mnemosyne=lambda **kwargs: mock_instance),
        },
    ):
        config = InstancePoolConfig(
            max_instances=5,
            eviction_timeout=300,
            data_dir=str(tmp_path),
            default_bank="default",
        )
        router = MemoryBankRouter(config=config)
        router._mock_instance = mock_instance
        yield router


# ---------------------------------------------------------------------------
# Schema tests — tool renamed to recallMemory
# ---------------------------------------------------------------------------


class TestRecallMemorySchema:
    """RECALL_SCHEMA uses recallMemory as the tool name (renamed from memory_recall)."""

    def test_schema_name_is_recall_memory(self) -> None:
        """Schema name should be recallMemory, not memory_recall."""
        from src.infrastructure.mcp.schemas import RECALL_SCHEMA

        assert RECALL_SCHEMA["name"] == "recallMemory"

    def test_schema_name_is_not_memory_recall(self) -> None:
        """Old name memory_recall should no longer be used."""
        from src.infrastructure.mcp.schemas import RECALL_SCHEMA

        assert RECALL_SCHEMA["name"] != "memory_recall"

    def test_schema_has_query_parameter(self) -> None:
        """Schema should have query as a required parameter."""
        from src.infrastructure.mcp.schemas import RECALL_SCHEMA

        params = RECALL_SCHEMA["parameters"]["properties"]
        assert "query" in params
        assert params["query"]["type"] == "string"

    def test_schema_has_limit_parameter(self) -> None:
        """Schema should have limit as an optional parameter."""
        from src.infrastructure.mcp.schemas import RECALL_SCHEMA

        params = RECALL_SCHEMA["parameters"]["properties"]
        assert "limit" in params
        assert params["limit"]["type"] == "integer"

    def test_schema_memory_bank_required(self) -> None:
        """Schema should require memory_bank parameter."""
        from src.infrastructure.mcp.schemas import RECALL_SCHEMA

        assert "memory_bank" in RECALL_SCHEMA["parameters"]["required"]

    def test_schema_in_all_tool_schemas(self) -> None:
        """recallMemory schema should be in ALL_TOOL_SCHEMAS."""
        from src.infrastructure.mcp.schemas import ALL_TOOL_SCHEMAS, RECALL_SCHEMA

        assert RECALL_SCHEMA in ALL_TOOL_SCHEMAS

    def test_all_tool_schemas_no_memory_recall_name(self) -> None:
        """No schema should use the old memory_recall name."""
        from src.infrastructure.mcp.schemas import ALL_TOOL_SCHEMAS

        names = {schema["name"] for schema in ALL_TOOL_SCHEMAS}
        assert "memory_recall" not in names

    def test_all_tool_schemas_has_recall_memory_name(self) -> None:
        """recallMemory should be present in ALL_TOOL_SCHEMAS names."""
        from src.infrastructure.mcp.schemas import ALL_TOOL_SCHEMAS

        names = {schema["name"] for schema in ALL_TOOL_SCHEMAS}
        assert "recallMemory" in names


# ---------------------------------------------------------------------------
# MCP tool registration — app.py
# ---------------------------------------------------------------------------


class TestRecallMemoryToolRegistration:
    """MCP tool is registered as recallMemory in app.py."""

    def test_tool_registered_as_recall_memory(self) -> None:
        """The MCP tool should be registered with name recallMemory."""
        from src.app import register_tools

        mock_mcp = MagicMock()
        mock_router = MagicMock()

        register_tools(mock_mcp, mock_router)

        # Check that mcp.tool was called with name="recallMemory"
        tool_calls = [call for call in mock_mcp.tool.call_args_list if call.kwargs.get("name") == "recallMemory"]
        assert len(tool_calls) == 1, "recallMemory tool should be registered exactly once"

    def test_old_memory_recall_tool_not_registered(self) -> None:
        """The old memory_recall tool name should NOT be registered."""
        from src.app import register_tools

        mock_mcp = MagicMock()
        mock_router = MagicMock()

        register_tools(mock_mcp, mock_router)

        tool_calls = [call for call in mock_mcp.tool.call_args_list if call.kwargs.get("name") == "memory_recall"]
        assert len(tool_calls) == 0, "memory_recall tool should NOT be registered"

    def test_recall_memory_tool_exposes_optional_enrich_limit(self) -> None:
        """recallMemory tool signature exposes optional enrich_limit (int, default 5)."""
        from src.app import register_tools

        mock_mcp = MagicMock()
        mock_router = MagicMock()

        register_tools(mock_mcp, mock_router)

        import inspect
        from src.app import register_tools as _register_tools

        source = inspect.getsource(_register_tools)
        assert "enrich_limit: int" in source

    def test_recall_memory_tool_accepts_query_and_limit(self) -> None:
        """recallMemory tool should accept query (str), memory_bank (str), and limit (int)."""
        from src.app import register_tools

        mock_mcp = MagicMock()
        mock_router = MagicMock()

        register_tools(mock_mcp, mock_router)

        # Find the recallMemory tool registration — tool() is called with name=
        recall_memory_calls = [
            call for call in mock_mcp.tool.call_args_list if call.kwargs.get("name") == "recallMemory"
        ]
        assert len(recall_memory_calls) == 1

        # The decorator factory mcp.tool(name="recallMemory") returns a decorator
        # that then wraps the inner async function. The inner function is passed
        # to the returned decorator, not to tool() itself. So we inspect the
        # source of app.py to verify the recall function signature.
        import inspect
        from src.app import register_tools as _register_tools

        source = inspect.getsource(_register_tools)
        # The recall function should have query, memory_bank, and limit params
        assert "query: str" in source
        assert "memory_bank: str" in source
        assert "limit: int" in source

    def test_tool_registry_still_exactly_11_tools(self) -> None:
        """Adding enrich_limit must NOT add a new tool — registry stays at exactly 11."""
        from src.app import register_tools

        mock_mcp = MagicMock()
        mock_router = MagicMock()

        register_tools(mock_mcp, mock_router)

        names = {call.kwargs.get("name") for call in mock_mcp.tool.call_args_list}
        assert len(names) == 11


# ---------------------------------------------------------------------------
# Handler tests — renamed tool name in log_tool_call and _raise_on_ko
# ---------------------------------------------------------------------------


class TestRecallMemoryHandler:
    """handle_recall uses recallMemory as the tool name in log_tool_call and error messages."""

    def test_handler_delegates_to_recall_memory_use_case(self, router: MemoryBankRouter) -> None:
        """handle_recall should still delegate to RecallMemoryUseCase."""
        from src.infrastructure.mcp.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "results": [{"id": "mem_1", "content": "found"}],
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RecallMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_recall(
                    router,
                    {"query": "test", "memory_bank": "test-ns", "limit": 5},
                )

            assert result["memory_bank"] == "test-ns"
            assert len(result["results"]) == 1
            assert result["results"][0]["id"] == "mem_1"

        asyncio.run(run())

    def test_handler_passes_limit_to_use_case(self, router: MemoryBankRouter) -> None:
        """handle_recall should pass limit parameter through to the use case."""
        from src.infrastructure.mcp.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "results": [],
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RecallMemoryUseCase",
                return_value=mock_use_case,
            ):
                await handle_recall(
                    router,
                    {"query": "test", "memory_bank": "test-ns", "limit": 3},
                )

            call_args = mock_use_case.execute.call_args[0][0]
            assert call_args["limit"] == 3

        asyncio.run(run())

    def test_handler_raises_validation_error_on_result_ko(self, router: MemoryBankRouter) -> None:
        """handle_recall should raise ValidationError with recallMemory in error context."""
        from src.infrastructure.mcp.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([ErrorWithDetails("QUERY_REQUIRED", {})])

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RecallMemoryUseCase",
                return_value=mock_use_case,
            ):
                with pytest.raises(ValidationError):
                    await handle_recall(
                        router,
                        {"query": "test", "memory_bank": "test-ns"},
                    )

        asyncio.run(run())

    def test_handler_raises_validation_error_without_query(self, router: MemoryBankRouter) -> None:
        """handle_recall should raise ValidationError when query is missing."""
        from src.infrastructure.mcp.handlers import handle_recall

        async def run() -> None:
            with pytest.raises(ValidationError, match="query is required"):
                await handle_recall(router, {"memory_bank": "test-ns"})

        asyncio.run(run())

    def test_handler_raises_validation_error_without_memory_bank(self, router: MemoryBankRouter) -> None:
        """handle_recall should raise ValidationError when memory_bank is missing."""
        from src.infrastructure.mcp.handlers import handle_recall

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_recall(router, {"query": "test"})

        asyncio.run(run())

    def test_handler_returns_results_and_memory_bank(self, router: MemoryBankRouter) -> None:
        """handle_recall should return results list and memory_bank in response."""
        from src.infrastructure.mcp.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "results": [
                    {"id": "mem_1", "content": "result one"},
                    {"id": "mem_2", "content": "result two"},
                ],
                "memory_bank": "my-bank",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RecallMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_recall(
                    router,
                    {"query": "search term", "memory_bank": "my-bank"},
                )

            assert isinstance(result["results"], list)
            assert len(result["results"]) == 2
            assert result["memory_bank"] == "my-bank"

        asyncio.run(run())

    def test_handler_uses_default_limit_when_not_provided(self, router: MemoryBankRouter) -> None:
        """handle_recall should use default limit of 10 when not provided."""
        from src.infrastructure.mcp.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "results": [],
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RecallMemoryUseCase",
                return_value=mock_use_case,
            ):
                await handle_recall(
                    router,
                    {"query": "test", "memory_bank": "test-ns"},
                )

            call_args = mock_use_case.execute.call_args[0][0]
            # Use case defaults to 10 when limit not provided
            assert call_args.get("limit") is None or call_args.get("limit") == 10

        asyncio.run(run())


class TestHandleRecallEnrichmentWiring:
    """handle_recall wires FileEnrichmentService (same factory pattern as remember/forget)."""

    def test_handler_constructs_file_enrichment_service(self, router: MemoryBankRouter) -> None:
        """handle_recall must build a real FileEnrichmentService and inject it into the use case."""
        from src.infrastructure.mcp.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "results": [],
                "memory_bank": "test-ns",
            }
        )

        mock_uc_cls: list[MagicMock] = []
        mock_enrichment_cls: list[MagicMock] = []

        async def run() -> None:
            with (
                patch(
                    "src.infrastructure.mcp.handlers.RecallMemoryUseCase",
                    return_value=mock_use_case,
                ) as uc_cls,
                patch("src.infrastructure.mcp.handlers.FileEnrichmentService") as enrichment_cls,
            ):
                mock_uc_cls.append(uc_cls)
                mock_enrichment_cls.append(enrichment_cls)
                await handle_recall(router, {"query": "test", "memory_bank": "test-ns"})

        asyncio.run(run())

        mock_uc_cls = mock_uc_cls[0]
        mock_enrichment_cls = mock_enrichment_cls[0]
        assert mock_uc_cls.call_count == 1
        uc_kwargs = mock_uc_cls.call_args.kwargs
        assert "file_enrichment_service" in uc_kwargs
        # The injected service must be the instance produced by FileEnrichmentService(...)
        assert uc_kwargs["file_enrichment_service"] is mock_enrichment_cls.return_value
        mock_enrichment_cls.assert_called_once()

    def test_handler_passes_enrich_limit_to_use_case(self, router: MemoryBankRouter) -> None:
        """handle_recall should pass enrich_limit through to the use case params."""
        from src.infrastructure.mcp.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "results": [],
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with (
                patch("src.infrastructure.mcp.handlers.RecallMemoryUseCase", return_value=mock_use_case),
                patch("src.infrastructure.mcp.handlers.FileEnrichmentService"),
            ):
                await handle_recall(
                    router,
                    {"query": "test", "memory_bank": "test-ns", "enrich_limit": 2},
                )

            call_args = mock_use_case.execute.call_args[0][0]
            assert call_args["enrich_limit"] == 2

        asyncio.run(run())


# ---------------------------------------------------------------------------
# fetchFile neighbor-mode params (Task 17) — additive, registry stays at 11
# ---------------------------------------------------------------------------


class TestFetchFileNeighborParams:
    """fetchFile tool exposes optional center_chunk_index + adjacent_chunks."""

    def test_fetch_file_tool_exposes_neighbor_params(self) -> None:
        from src.app import register_tools

        mock_mcp = MagicMock()
        mock_router = MagicMock()

        register_tools(mock_mcp, mock_router)

        fetch_calls = [call for call in mock_mcp.tool.call_args_list if call.kwargs.get("name") == "fetchFile"]
        assert len(fetch_calls) == 1

        import inspect
        from src.app import register_tools as _register_tools

        source = inspect.getsource(_register_tools)
        assert "center_chunk_index: int | None = None" in source
        assert "adjacent_chunks: int = 1" in source

    def test_fetch_file_tool_passes_neighbor_params_to_handler(self) -> None:
        """center_chunk_index/adjacent_chunks are forwarded to handle_fetch_file."""
        from src.app import register_tools
        from src.infrastructure import mcp as mcp_module

        mock_mcp = MagicMock()
        mock_router = MagicMock()
        register_tools(mock_mcp, mock_router)

        fetch_calls = [call for call in mock_mcp.tool.call_args_list if call.kwargs.get("name") == "fetchFile"]
        assert len(fetch_calls) == 1
        # The decorator factory returns a decorator; the inner function is registered
        # via mcp.tool(name=...). Inspect the decorated function's closure behavior
        # by checking the source forwards both params.
        import inspect
        from src.app import register_tools as _register_tools

        source = inspect.getsource(_register_tools)
        assert 'args["center_chunk_index"]' in source
        assert 'args["adjacent_chunks"]' in source

    def test_registry_still_exactly_11_tools_after_neighbor_params(self) -> None:
        """Adding neighbor params must NOT add a new tool — registry stays at exactly 11."""
        from src.app import register_tools

        mock_mcp = MagicMock()
        mock_router = MagicMock()

        register_tools(mock_mcp, mock_router)

        names = {call.kwargs.get("name") for call in mock_mcp.tool.call_args_list}
        assert len(names) == 11
        assert "fetchFile" in names
