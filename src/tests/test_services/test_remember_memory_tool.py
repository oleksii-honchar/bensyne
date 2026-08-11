"""Tests for the rememberMemory MCP tool (renamed from memory_remember).

Verifies:
- MCP tool is registered as "rememberMemory" (not "memory_remember")
- Tool accepts content, source?, scope?, importance? parameters
- Handler delegates to ProcessMemoryUseCase
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
from src.domain.result import ErrorWithDetails, Result
from src.services.bank.router import MemoryBankRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_mnemosyne_instance() -> MagicMock:
    """Create a fully configured mock Mnemosyne instance."""
    mock = MagicMock()
    mock.remember.return_value = "mem_abc123"
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
        router = MemoryBankRouter(config=config)
        router._mock_instance = mock_instance
        yield router


# ---------------------------------------------------------------------------
# Schema tests — tool renamed to rememberMemory
# ---------------------------------------------------------------------------


class TestRememberMemorySchema:
    """REMEMBER_SCHEMA uses rememberMemory as the tool name (renamed from memory_remember)."""

    def test_schema_name_is_remember_memory(self) -> None:
        """Schema name should be rememberMemory, not memory_remember."""
        from src.services.tools.schemas import REMEMBER_SCHEMA

        assert REMEMBER_SCHEMA["name"] == "rememberMemory"

    def test_schema_name_is_not_memory_remember(self) -> None:
        """Old name memory_remember should no longer be used."""
        from src.services.tools.schemas import REMEMBER_SCHEMA

        assert REMEMBER_SCHEMA["name"] != "memory_remember"

    def test_schema_has_content_parameter(self) -> None:
        """Schema should have content as a required parameter."""
        from src.services.tools.schemas import REMEMBER_SCHEMA

        params = REMEMBER_SCHEMA["parameters"]["properties"]
        assert "content" in params
        assert params["content"]["type"] == "string"

    def test_schema_has_importance_parameter(self) -> None:
        """Schema should have importance as an optional parameter."""
        from src.services.tools.schemas import REMEMBER_SCHEMA

        params = REMEMBER_SCHEMA["parameters"]["properties"]
        assert "importance" in params
        assert params["importance"]["type"] == "number"

    def test_schema_has_source_parameter(self) -> None:
        """Schema should have source as an optional parameter."""
        from src.services.tools.schemas import REMEMBER_SCHEMA

        params = REMEMBER_SCHEMA["parameters"]["properties"]
        assert "source" in params
        assert params["source"]["type"] == "string"

    def test_schema_has_scope_parameter(self) -> None:
        """Schema should have scope as an optional parameter."""
        from src.services.tools.schemas import REMEMBER_SCHEMA

        params = REMEMBER_SCHEMA["parameters"]["properties"]
        assert "scope" in params

    def test_schema_memory_bank_required(self) -> None:
        """Schema should require memory_bank parameter."""
        from src.services.tools.schemas import REMEMBER_SCHEMA

        assert "memory_bank" in REMEMBER_SCHEMA["parameters"]["required"]

    def test_schema_content_required(self) -> None:
        """Schema should require content parameter."""
        from src.services.tools.schemas import REMEMBER_SCHEMA

        assert "content" in REMEMBER_SCHEMA["parameters"]["required"]

    def test_schema_in_all_tool_schemas(self) -> None:
        """rememberMemory schema should be in ALL_TOOL_SCHEMAS."""
        from src.services.tools.schemas import ALL_TOOL_SCHEMAS, REMEMBER_SCHEMA

        assert REMEMBER_SCHEMA in ALL_TOOL_SCHEMAS

    def test_all_tool_schemas_no_memory_remember_name(self) -> None:
        """No schema should use the old memory_remember name."""
        from src.services.tools.schemas import ALL_TOOL_SCHEMAS

        names = {schema["name"] for schema in ALL_TOOL_SCHEMAS}
        assert "memory_remember" not in names

    def test_all_tool_schemas_has_remember_memory_name(self) -> None:
        """rememberMemory should be present in ALL_TOOL_SCHEMAS names."""
        from src.services.tools.schemas import ALL_TOOL_SCHEMAS

        names = {schema["name"] for schema in ALL_TOOL_SCHEMAS}
        assert "rememberMemory" in names


# ---------------------------------------------------------------------------
# MCP tool registration — app.py
# ---------------------------------------------------------------------------


class TestRememberMemoryToolRegistration:
    """MCP tool is registered as rememberMemory in app.py."""

    def test_tool_registered_as_remember_memory(self) -> None:
        """The MCP tool should be registered with name rememberMemory."""
        from src.app import register_tools

        mock_mcp = MagicMock()
        mock_router = MagicMock()

        register_tools(mock_mcp, mock_router)

        # Check that mcp.tool was called with name="rememberMemory"
        tool_calls = [
            call for call in mock_mcp.tool.call_args_list
            if call.kwargs.get("name") == "rememberMemory"
        ]
        assert len(tool_calls) == 1, "rememberMemory tool should be registered exactly once"

    def test_old_memory_remember_tool_not_registered(self) -> None:
        """The old memory_remember tool name should NOT be registered."""
        from src.app import register_tools

        mock_mcp = MagicMock()
        mock_router = MagicMock()

        register_tools(mock_mcp, mock_router)

        tool_calls = [
            call for call in mock_mcp.tool.call_args_list
            if call.kwargs.get("name") == "memory_remember"
        ]
        assert len(tool_calls) == 0, "memory_remember tool should NOT be registered"

    def test_remember_memory_tool_accepts_content_and_optional_params(self) -> None:
        """rememberMemory tool should accept content, memory_bank, and optional params."""
        from src.app import register_tools

        mock_mcp = MagicMock()
        mock_router = MagicMock()

        register_tools(mock_mcp, mock_router)

        # Find the rememberMemory tool registration
        remember_memory_calls = [
            call for call in mock_mcp.tool.call_args_list
            if call.kwargs.get("name") == "rememberMemory"
        ]
        assert len(remember_memory_calls) == 1

        # Inspect the source of app.py to verify the remember function signature
        import inspect
        from src.app import register_tools as _register_tools
        source = inspect.getsource(_register_tools)
        # The remember function should have content, memory_bank, and optional params
        assert "content: str" in source
        assert "memory_bank: str" in source
        assert "importance: float" in source
        assert "source: str" in source
        assert "scope: str" in source


# ---------------------------------------------------------------------------
# Handler tests — renamed tool name in log_tool_call and _raise_on_ko
# ---------------------------------------------------------------------------


class TestRememberMemoryHandler:
    """handle_remember uses rememberMemory as the tool name in log_tool_call and error messages."""

    def test_handler_delegates_to_process_memory_use_case(self, router: MemoryBankRouter) -> None:
        """handle_remember should still delegate to ProcessMemoryUseCase."""
        from src.services.tools.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "stored",
            "memory_id": "mem_abc123",
            "memory_bank": "test-ns",
        })

        async def run() -> None:
            with patch(
                "src.services.tools.handlers.ProcessMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_remember(
                    router,
                    {"content": "test memory", "memory_bank": "test-ns"},
                )

            assert result["status"] == "stored"
            assert result["memory_id"] == "mem_abc123"
            assert result["memory_bank"] == "test-ns"

        asyncio.run(run())

    def test_handler_passes_importance_to_use_case(self, router: MemoryBankRouter) -> None:
        """handle_remember should pass importance parameter through to the use case."""
        from src.services.tools.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "stored",
            "memory_id": "mem_abc123",
            "memory_bank": "test-ns",
        })

        async def run() -> None:
            with patch(
                "src.services.tools.handlers.ProcessMemoryUseCase",
                return_value=mock_use_case,
            ):
                await handle_remember(
                    router,
                    {
                        "content": "test",
                        "memory_bank": "test-ns",
                        "importance": 0.8,
                    },
                )

            call_args = mock_use_case.execute.call_args[0][0]
            assert call_args["importance"] == 0.8

        asyncio.run(run())

    def test_handler_passes_source_to_use_case(self, router: MemoryBankRouter) -> None:
        """handle_remember should pass source parameter through to the use case."""
        from src.services.tools.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "stored",
            "memory_id": "mem_abc123",
            "memory_bank": "test-ns",
        })

        async def run() -> None:
            with patch(
                "src.services.tools.handlers.ProcessMemoryUseCase",
                return_value=mock_use_case,
            ):
                await handle_remember(
                    router,
                    {
                        "content": "test",
                        "memory_bank": "test-ns",
                        "source": "user",
                    },
                )

            call_args = mock_use_case.execute.call_args[0][0]
            assert call_args["source"] == "user"

        asyncio.run(run())

    def test_handler_passes_scope_to_use_case(self, router: MemoryBankRouter) -> None:
        """handle_remember should pass scope parameter through to the use case."""
        from src.services.tools.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "stored",
            "memory_id": "mem_abc123",
            "memory_bank": "test-ns",
        })

        async def run() -> None:
            with patch(
                "src.services.tools.handlers.ProcessMemoryUseCase",
                return_value=mock_use_case,
            ):
                await handle_remember(
                    router,
                    {
                        "content": "test",
                        "memory_bank": "test-ns",
                        "scope": "project",
                    },
                )

            call_args = mock_use_case.execute.call_args[0][0]
            assert call_args["scope"] == "project"

        asyncio.run(run())

    def test_handler_raises_validation_error_on_result_ko(self, router: MemoryBankRouter) -> None:
        """handle_remember should raise ValidationError with rememberMemory in error context."""
        from src.services.tools.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([
            ErrorWithDetails("CONTENT_REQUIRED", {})
        ])

        async def run() -> None:
            with patch(
                "src.services.tools.handlers.ProcessMemoryUseCase",
                return_value=mock_use_case,
            ):
                with pytest.raises(ValidationError):
                    await handle_remember(
                        router,
                        {"content": "test", "memory_bank": "test-ns"},
                    )

        asyncio.run(run())

    def test_handler_raises_validation_error_without_content(self, router: MemoryBankRouter) -> None:
        """handle_remember should raise ValidationError when content is missing."""
        from src.services.tools.handlers import handle_remember

        async def run() -> None:
            with pytest.raises(ValidationError, match="content is required"):
                await handle_remember(router, {"memory_bank": "test-ns"})

        asyncio.run(run())

    def test_handler_raises_validation_error_without_memory_bank(self, router: MemoryBankRouter) -> None:
        """handle_remember should raise ValidationError when memory_bank is missing."""
        from src.services.tools.handlers import handle_remember

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_remember(router, {"content": "test"})

        asyncio.run(run())

    def test_handler_returns_status_and_memory_id(self, router: MemoryBankRouter) -> None:
        """handle_remember should return status, memory_id, and memory_bank in response."""
        from src.services.tools.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "stored",
            "memory_id": "mem_xyz789",
            "memory_bank": "my-bank",
        })

        async def run() -> None:
            with patch(
                "src.services.tools.handlers.ProcessMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_remember(
                    router,
                    {"content": "test memory", "memory_bank": "my-bank"},
                )

            assert result["status"] == "stored"
            assert result["memory_id"] == "mem_xyz789"
            assert result["memory_bank"] == "my-bank"

        asyncio.run(run())

    def test_handler_handles_deduplication_result(self, router: MemoryBankRouter) -> None:
        """handle_remember should handle deduplication status from use case."""
        from src.services.tools.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "deduplicated",
            "memory_id": "mem_existing",
            "memory_bank": "test-ns",
        })

        async def run() -> None:
            with patch(
                "src.services.tools.handlers.ProcessMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_remember(
                    router,
                    {
                        "content": "test",
                        "memory_bank": "test-ns",
                        "metadata": {"fileHash": "sha256_abc"},
                    },
                )

            assert result["status"] == "deduplicated"
            assert result["memory_id"] == "mem_existing"

        asyncio.run(run())

    def test_handler_uses_remember_memory_in_log_tool_call(self) -> None:
        """handle_remember should use rememberMemory in @log_tool_call decorator."""
        import inspect
        from src.services.tools.handlers import handle_remember
        source = inspect.getsource(handle_remember.__wrapped__ if hasattr(handle_remember, '__wrapped__') else handle_remember)
        # The @log_tool_call decorator should use "rememberMemory"
        assert "rememberMemory" in source
