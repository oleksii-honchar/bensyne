"""Application factory.

Wires all components: FastMCP server, MCP tool handlers, health endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from src.domain.models import AppConfig
    from src.services.namespace.router import NamespaceRouter


def create_application(config: AppConfig, router: NamespaceRouter) -> FastMCP:
    """Create and wire the complete application.

    Args:
        config: Application configuration.
        router: Namespace router for routing tool calls.

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


def register_tools(mcp: FastMCP, router: NamespaceRouter) -> None:
    """Register all MCP tool handlers with the server.

    Args:
        mcp: FastMCP server instance.
        router: Namespace router injected into all handlers.
    """
    from src.services.tools import handlers

    # Bind router to each handler via wrapper functions (fastmcp @tool requires callable, not partial)
    # FastMCP 3.x generates JSON schema from function signature; use explicit params to match MCP protocol
    @mcp.tool(name="mnemosyne_remember")
    async def remember(content: str, namespace: str = "default", importance: float | None = None,
                       source: str | None = None, scope: str | None = None, valid_until: str | None = None,
                       extract_entities: bool | None = None, extract: bool | None = None,
                       metadata: dict | None = None, veracity: float | None = None):
        args = {"content": content, "namespace": namespace}
        for k, v in [("importance", importance), ("source", source), ("scope", scope),
                     ("valid_until", valid_until), ("extract_entities", extract_entities),
                     ("extract", extract), ("metadata", metadata), ("veracity", veracity)]:
            if v is not None:
                args[k] = v
        return await handlers.handle_remember(router, args)

    @mcp.tool(name="mnemosyne_recall")
    async def recall(query: str, namespace: str = "default", limit: int = 5):
        return await handlers.handle_recall(router, {"query": query, "namespace": namespace, "limit": limit})

    @mcp.tool(name="mnemosyne_forget")
    async def forget(memory_id: str, namespace: str = "default"):
        return await handlers.handle_forget(router, {"memory_id": memory_id, "namespace": namespace})

    @mcp.tool(name="mnemosyne_update")
    async def update(memory_id: str, namespace: str = "default", content: str | None = None,
                     importance: float | None = None):
        args = {"memory_id": memory_id, "namespace": namespace}
        if content is not None:
            args["content"] = content
        if importance is not None:
            args["importance"] = importance
        return await handlers.handle_update(router, args)

    @mcp.tool(name="mnemosyne_sleep")
    async def sleep_tool(namespace: str = "default"):
        return await handlers.handle_sleep(router, {"namespace": namespace})

    @mcp.tool(name="mnemosyne_stats")
    async def stats(namespace: str = "default"):
        return await handlers.handle_stats(router, {"namespace": namespace})

    @mcp.tool(name="mnemosyne_list_namespaces")
    async def list_namespaces():
        return await handlers.handle_list_namespaces(router, {})


def mount_health_routes(mcp: FastMCP, router: NamespaceRouter) -> None:
    """Mount health check endpoints onto the FastMCP server.

    Args:
        mcp: FastMCP server instance.
        router: Namespace router for health endpoint queries.
    """
    from src.middleware.health import set_namespace_router

    set_namespace_router(router)
