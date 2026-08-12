"""Application factory.

Wires all components: FastMCP server, MCP tool handlers, health endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from src.domain.config_models import AppConfig
    from src.infrastructure.bank.router import MemoryBankRouter


def create_application(config: AppConfig, router: MemoryBankRouter) -> FastMCP:
    """Create and wire the complete application.

    Args:
        config: Application configuration.
        router: Memory bank router for routing tool calls.

    Returns:
        Fully configured FastMCP server instance.
    """
    mcp = create_server(config)

    # Register MCP tools
    register_tools(mcp, router)

    # Mount health check endpoints
    mount_health_routes(mcp, router)

    return mcp


def create_server(config: AppConfig) -> FastMCP:
    """Create the FastMCP server with configuration.

    Args:
        config: Application configuration for server settings.

    Returns:
        FastMCP server instance.
    """
    from src.application.server import create_server as _create_server

    return _create_server()


def register_tools(mcp: FastMCP, router: MemoryBankRouter) -> None:
    """Register all MCP tool handlers with the server.

    Args:
        mcp: FastMCP server instance.
        router: Memory bank router injected into all handlers.
    """
    from src.infrastructure.mcp import handlers

    # Bind router to each handler via wrapper functions (fastmcp @tool requires callable, not partial)
    # FastMCP 3.x generates JSON schema from function signature; use explicit params to match MCP protocol
    @mcp.tool(name="rememberMemory")
    async def remember(content: str, memory_bank: str, importance: float | None = None,
                       source: str | None = None, scope: str | None = None, valid_until: str | None = None,
                       extract_entities: bool | None = None, extract: bool | None = None,
                       metadata: dict | None = None, veracity: float | None = None):
        args = {"content": content, "memory_bank": memory_bank}
        for k, v in [("importance", importance), ("source", source), ("scope", scope),
                     ("valid_until", valid_until), ("extract_entities", extract_entities),
                     ("extract", extract), ("metadata", metadata), ("veracity", veracity)]:
            if v is not None:
                args[k] = v
        return await handlers.handle_remember(router, args)

    @mcp.tool(name="recallMemory")
    async def recall(query: str, memory_bank: str, limit: int = 5):
        return await handlers.handle_recall(router, {"query": query, "memory_bank": memory_bank, "limit": limit})

    @mcp.tool(name="forgetMemory")
    async def forget(memory_id: str, memory_bank: str):
        return await handlers.handle_forget(router, {"memory_id": memory_id, "memory_bank": memory_bank})

    @mcp.tool(name="updateMemory")
    async def update(memory_id: str, memory_bank: str, content: str | None = None,
                     importance: float | None = None):
        args = {"memory_id": memory_id, "memory_bank": memory_bank}
        if content is not None:
            args["content"] = content
        if importance is not None:
            args["importance"] = importance
        return await handlers.handle_update(router, args)

    @mcp.tool(name="sleep")
    async def sleep_tool(memory_bank: str):
        return await handlers.handle_sleep(router, {"memory_bank": memory_bank})

    @mcp.tool(name="getMemoryStats")
    async def stats(memory_bank: str):
        return await handlers.handle_stats(router, {"memory_bank": memory_bank})

    @mcp.tool(name="listMemoryBanks")
    async def list_banks():
        return await handlers.handle_list_banks(router, {})

    @mcp.tool(name="registerMemoryBank")
    async def register_bank(name: str, description: str):
        return await handlers.handle_register_bank(router, {"name": name, "description": description})

    @mcp.tool(name="searchFiles")
    async def search_files(query: str, memory_bank: str, limit: int = 10,
                           source_type: str | None = None, file_role: str | None = None,
                           include_relations: bool = False):
        args = {"query": query, "memory_bank": memory_bank, "limit": limit,
                "include_relations": include_relations}
        if source_type is not None:
            args["source_type"] = source_type
        if file_role is not None:
            args["file_role"] = file_role
        return await handlers.handle_search_files(router, args)

    @mcp.tool(name="expandFileRelations")
    async def expand_file_relations(file_id: str, memory_bank: str,
                                      relation_types: list[str] | None = None,
                                      summary_only: bool = False):
        args = {"file_id": file_id, "memory_bank": memory_bank,
                "summary_only": summary_only}
        if relation_types is not None:
            args["relation_types"] = relation_types
        return await handlers.handle_expand_file_relations(router, args)

    @mcp.tool(name="fetchFile")
    async def fetch_file(file_id: str, memory_bank: str,
                         include_metadata: bool = False):
        args = {"file_id": file_id, "memory_bank": memory_bank,
                "include_metadata": include_metadata}
        return await handlers.handle_fetch_file(router, args)


def mount_health_routes(mcp: FastMCP, router: MemoryBankRouter) -> None:
    """Mount health check endpoints onto the FastMCP server using custom_route.

    Args:
        mcp: FastMCP server instance.
        router: Memory bank router for health endpoint queries.
    """
    from src.middleware.health import (
        health_handler,
        health_log_handler,
        health_ready_handler,
        set_memory_bank_router,
    )

    set_memory_bank_router(router)

    # Register health endpoints as custom HTTP routes
    mcp.custom_route("/health", methods=["GET"], name="health")(health_handler)
    mcp.custom_route("/health/ready", methods=["GET"], name="health_ready")(health_ready_handler)
    mcp.custom_route("/health/log", methods=["GET"], name="health_log")(health_log_handler)
