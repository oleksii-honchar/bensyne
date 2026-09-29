"""prune_phantom_edge_stub MCP tool wiring tests.

Covers the end-to-end wiring of the prune_phantom_edge_stub tool:
- the tool is registered in the MCP registry with source_file_id, target_file_id, memory_bank
- calling it through the MCP interface reaches the DI container with the correct dependencies
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

    mcp = FastMCP(name="prune-edge-stub-schema-test")
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


class TestPrunePhantomEdgeStubToolRegistration:
    """prune_phantom_edge_stub is registered with the correct schema."""

    def test_prune_phantom_edge_stub_tool_registered(self) -> None:
        """prune_phantom_edge_stub is in the MCP registry with required params."""
        by_name = _build_registry_tool_map()

        assert "prune_phantom_edge_stub" in by_name
        params = by_name["prune_phantom_edge_stub"].parameters["properties"]
        assert params["source_file_id"]["type"] == "string"
        assert params["target_file_id"]["type"] == "string"
        assert params["memory_bank"]["type"] == "string"
        # relation_type is optional and nullable (str | None), so FastMCP generates anyOf
        rt_param = params["relation_type"]
        assert "type" in rt_param or "anyOf" in rt_param

    def test_prune_phantom_edge_stub_required_params(self) -> None:
        """source_file_id, target_file_id, memory_bank are required."""
        by_name = _build_registry_tool_map()

        required = by_name["prune_phantom_edge_stub"].parameters["required"]
        assert "source_file_id" in required
        assert "target_file_id" in required
        assert "memory_bank" in required


class TestPrunePhantomEdgeStubEndToEndWiring:
    """prune_phantom_edge_stub call through the MCP interface reaches the DI container."""

    async def test_prune_phantom_edge_stub_reaches_file_service(self, router) -> None:
        """Calling prune_phantom_edge_stub via MCP executes the file service method."""
        from fastmcp import FastMCP

        from src.app import register_tools
        from src.infrastructure.di import TestContainer

        container = TestContainer()

        # Mock the FileService
        mock_file_service = MagicMock()
        mock_file_service.prune_phantom_edge_stub.return_value = Result.ok(True)

        with container.override_providers(
            file_service=providers.Factory(lambda **kwargs: mock_file_service)
        ):
            mcp = FastMCP(name="prune-edge-stub-e2e")
            register_tools(mcp, router, MagicMock(), container)

            result = await mcp.call_tool(
                "prune_phantom_edge_stub",
                {
                    "source_file_id": "file_source",
                    "target_file_id": "file_target",
                    "memory_bank": "test_bank",
                },
            )

            # Check the result is successful
            assert any("true" in str(c).lower() for c in result.content)
            # Check the service method was called with the correct args
            mock_file_service.prune_phantom_edge_stub.assert_called_once_with(
                "file_source", "file_target", None
            )

    async def test_prune_phantom_edge_stub_with_relation_type(self, router) -> None:
        """Relation type parameter is passed through correctly."""
        from fastmcp import FastMCP

        from src.app import register_tools
        from src.infrastructure.di import TestContainer

        container = TestContainer()

        mock_file_service = MagicMock()
        mock_file_service.prune_phantom_edge_stub.return_value = Result.ok(True)

        with container.override_providers(
            file_service=providers.Factory(lambda **kwargs: mock_file_service)
        ):
            mcp = FastMCP(name="prune-edge-stub-type-e2e")
            register_tools(mcp, router, MagicMock(), container)

            result = await mcp.call_tool(
                "prune_phantom_edge_stub",
                {
                    "source_file_id": "file_source",
                    "target_file_id": "file_target",
                    "relation_type": "decision_next",
                    "memory_bank": "test_bank",
                },
            )

            assert any("true" in str(c).lower() for c in result.content)
            # Check relation_type was passed (it's parsed into a RelationType in the handler)
            call_args = mock_file_service.prune_phantom_edge_stub.call_args
            assert call_args[0][0] == "file_source"
            assert call_args[0][1] == "file_target"
            # The handler converts the string to a RelationType enum
            from src.domain.file_relation_entity import RelationType
            assert call_args[0][2] == RelationType.DECISION_NEXT

    async def test_prune_phantom_edge_stub_no_match(self, router) -> None:
        """Returns false when no matching relation was found."""
        from fastmcp import FastMCP

        from src.app import register_tools
        from src.infrastructure.di import TestContainer

        container = TestContainer()

        mock_file_service = MagicMock()
        mock_file_service.prune_phantom_edge_stub.return_value = Result.ok(False)

        with container.override_providers(
            file_service=providers.Factory(lambda **kwargs: mock_file_service)
        ):
            mcp = FastMCP(name="prune-edge-stub-nomatch-e2e")
            register_tools(mcp, router, MagicMock(), container)

            result = await mcp.call_tool(
                "prune_phantom_edge_stub",
                {
                    "source_file_id": "file_source",
                    "target_file_id": "file_target",
                    "memory_bank": "test_bank",
                },
            )

            assert any("false" in str(c).lower() for c in result.content)

    async def test_prune_phantom_edge_stub_validation(self, router) -> None:
        """Validation: source_file_id and target_file_id are required."""
        from fastmcp import FastMCP
        from fastmcp.exceptions import ValidationError

        from src.app import register_tools
        from src.infrastructure.di import TestContainer

        container = TestContainer()

        mcp = FastMCP(name="prune-edge-stub-validation-e2e")
        register_tools(mcp, router, MagicMock(), container)

        # Missing target_file_id should fail validation
        with pytest.raises(ValidationError, match="target_file_id"):
            await mcp.call_tool(
                "prune_phantom_edge_stub",
                {
                    "source_file_id": "file_source",
                    "memory_bank": "test_bank",
                },
            )