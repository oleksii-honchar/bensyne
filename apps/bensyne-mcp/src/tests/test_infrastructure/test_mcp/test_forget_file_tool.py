"""forgetFile MCP tool wiring tests (Task 2).

Covers the end-to-end wiring of the operator-only forgetFile tool:
- the tool is registered in the MCP registry with { file_path, memory_bank };
- calling it through the MCP interface reaches the DI container's
  forget_file_use_case factory with the per-bank dependencies (D25 pattern).

Uses a real TestContainer (in-memory logger/repos) with only the use-case
factory overridden, so the tool -> handler -> DI container path is real.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from dependency_injector import providers

from src.utils.result import Result


def _build_registry_tool_map() -> dict:
    """Build a real FastMCP server with a stub router and return name -> tool."""
    from fastmcp import FastMCP

    from src.app import register_tools

    mcp = FastMCP(name="forget-file-schema-test")
    router = MagicMock()
    register_tools(mcp, router, MagicMock(), None)

    async def _collect() -> dict:
        tools = await mcp.list_tools()
        return {t.name: t for t in tools}

    return asyncio.run(_collect())


@pytest.fixture
def router() -> MagicMock:
    router = MagicMock()
    router.get_instance = AsyncMock()
    return router


class TestForgetFileToolRegistration:
    """forgetFile is registered with the correct schema."""

    def test_forget_file_tool_registered_with_file_path_and_memory_bank(self) -> None:
        """forgetFile is in the MCP registry with file_path + memory_bank string params."""
        by_name = _build_registry_tool_map()

        assert "forgetFile" in by_name
        params = by_name["forgetFile"].parameters["properties"]
        assert params["file_path"]["type"] == "string"
        assert params["memory_bank"]["type"] == "string"


class TestForgetFileEndToEndWiring:
    """forgetFile call through the MCP interface reaches the DI-wired use case."""

    async def test_forget_file_tool_reaches_di_wired_use_case(self, router) -> None:
        """Calling forgetFile via MCP executes the container's forget_file_use_case
        factory and the use case with { file_path, memory_bank }."""
        from fastmcp import FastMCP

        from src.app import register_tools
        from src.infrastructure.di import TestContainer

        container = TestContainer()
        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({"status": "forgotten"})

        with container.override_providers(
            forget_file_use_case=providers.Factory(lambda **kwargs: mock_use_case)
        ):
            mcp = FastMCP(name="forget-file-e2e")
            register_tools(mcp, router, MagicMock(), container)

            await mcp.call_tool(
                "forgetFile",
                {"memory_bank": "default", "file_path": "/tmp/x.json"},
            )

        mock_use_case.execute.assert_called_once()
        args = mock_use_case.execute.call_args[0][0]
        assert args["file_path"] == "/tmp/x.json"
        assert args["memory_bank"] == "default"
