"""Application factory.

Wires all components: FastMCP server, MCP tool handlers, health endpoints.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

if TYPE_CHECKING:
    from fastmcp import FastMCP

    from src.domain.config_models import AppConfig
    from src.infrastructure.bank.router import MemoryBankRouter
    from src.infrastructure.di import Container

# ---------------------------------------------------------------------------
# Parameter descriptions (surfaced in the MCP tool schema via Annotated).
#
# These teach agents the write discipline even when they do NOT load the
# bensyne skill:
#   * the DEFAULT non-file bank is the only bank agents may WRITE to
#     (rememberMemory / updateMemory / forgetMemory);
#   * source-type banks (agent-sessions, vault, obsidian) are Racochu-managed
#     and RECALL-ONLY;
#   * recall/read is allowed in every bank;
#   * run listMemoryBanks first to discover banks.
# ---------------------------------------------------------------------------
_MEMORY_BANK_WRITE_DESC = (
    "Required. The memory bank (namespace) to write to. "
    "USE ONLY THE DEFAULT non-file bank ('default' or a newly user-created bank). "
    "Source-type banks ('agent-sessions', 'vault', 'obsidian') are Racochu-managed and "
    "RECALL-ONLY - writing to them via this tool is wrong. "
    "Run listMemoryBanks first to confirm which banks exist."
)
_MEMORY_BANK_READ_DESC = (
    "Required. The memory bank (namespace) to read from. "
    "Read/recall is allowed in EVERY bank. Typical banks: 'default' (the user profile "
    "bank) plus Racochu-managed source banks 'agent-sessions', 'vault', 'obsidian' "
    "(recall-only). Run listMemoryBanks first to see live banks. "
    "At task start, recall 'agent-sessions' and 'default' first to build awareness."
)
_MEMORY_BANK_FILE_DESC = (
    "Required. The memory bank (namespace) holding the file memories. "
    "Source-type banks ('agent-sessions', 'vault', 'obsidian') hold Racochu-ingested "
    "file memories and are READ-ONLY. Run listMemoryBanks first to confirm the bank."
)


def create_application(
    config: AppConfig, router: MemoryBankRouter, container: Container | None = None
) -> FastMCP:
    """Create and wire the complete application.

    Args:
        config: Application configuration.
        router: Memory bank router for routing tool calls.
        container: DI container for per-bank file-metadata dependencies (D25).
            When omitted, handlers fall back to a per-call ProductionContainer.

    Returns:
        Fully configured FastMCP server instance.
    """
    mcp = create_server(config)

    # Register MCP tools
    register_tools(mcp, router, container)

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


def register_tools(
    mcp: FastMCP, router: MemoryBankRouter, container: Container | None = None
) -> None:
    """Register all MCP tool handlers with the server.

    Args:
        mcp: FastMCP server instance.
        router: Memory bank router injected into all handlers.
        container: DI container plumbed to file-path handlers (D25).
    """
    from src.infrastructure.mcp import handlers

    # Bind router to each handler via wrapper functions (fastmcp @tool requires callable, not partial)
    # FastMCP 3.x generates JSON schema from function signature; docstrings + Annotated
    # parameter descriptions are surfaced in the MCP tool schema so agents get correct
    # usage guidance directly from the schema (even without the bensyne skill).

    @mcp.tool(name="rememberMemory")
    async def remember(
        content: Annotated[
            str,
            "Required. The user-specific memory to store - e.g. a user preference, habit, "
            "personal fact, recurring decision about the user, or a piece of the user's "
            "environment story (where they work, what projects they run).",
        ],
        memory_bank: Annotated[str, _MEMORY_BANK_WRITE_DESC],
        importance: Annotated[
            float | None,
            "Optional. Relative importance 0.0-1.0; higher = more likely to be recalled. "
            "Use high values for durable user facts. Don't over-remember trivialities.",
        ] = None,
        source: Annotated[str | None, "Optional. Free-text origin/context of this memory."] = None,
        scope: Annotated[str | None, "Optional. Scope tag for grouping/segmenting the memory."] = None,
        valid_until: Annotated[
            str | None,
            "Optional. ISO-8601 datetime when this memory becomes obsolete and should be dropped.",
        ] = None,
        extract_entities: Annotated[bool | None, "Optional. Auto-extract entities from the content."] = None,
        extract: Annotated[bool | None, "Optional. Whether to run extraction on the content."] = None,
        metadata: Annotated[dict | None, "Optional. Key/value metadata attached to the memory."] = None,
        veracity: Annotated[float | None, "Optional. Confidence 0.0-1.0 in the memory's correctness."] = None,
    ):
        """Store a new memory in the DEFAULT (non-file) bank.

        When to use: capturing USER-SPECIFIC knowledge that should persist:
          - The user's profile/image: preferences, habits, communication style,
            personal facts, recurring decisions about the user.
          - The user's environment story: where they work, what projects they run
            (e.g. a homelab's hosts/services at a narrative level).

        When NOT to use / HARD RULE:
          - The default bank is NOT the canonical source of truth for technical
            details. Canonical technical truth lives in the source-type banks
            (agent-sessions, vault) and in the codebase itself.
          - Source-type banks ('agent-sessions', 'vault', 'obsidian') are
            Racochu-managed and RECALL-ONLY. Writing to them via this tool is wrong.
          Use 'default' (or an explicitly new user-created bank) for memory_bank.

        Prefer this over re-asking the user something already knowable from prior context.
        """
        args = {"content": content, "memory_bank": memory_bank}
        for k, v in [
            ("importance", importance),
            ("source", source),
            ("scope", scope),
            ("valid_until", valid_until),
            ("extract_entities", extract_entities),
            ("extract", extract),
            ("metadata", metadata),
            ("veracity", veracity),
        ]:
            if v is not None:
                args[k] = v
        return await handlers.handle_remember(router, args, container)

    @mcp.tool(name="recallMemory")
    async def recall(
        query: Annotated[str, "Required. Natural-language query to match against memories."],
        memory_bank: Annotated[str, _MEMORY_BANK_READ_DESC],
        limit: Annotated[int, "Optional. Maximum memories to return. Default 5."] = 5,
        enrich_limit: Annotated[int, "Optional. Maximum enrichment items per memory. Default 5."] = 5,
    ):
        """Recall relevant memories by semantic search over a bank.

        When to use: ALWAYS, at the start of a task, to build awareness. Before working,
        recall the 'agent-sessions' bank (prior decisions/context) and the 'default' bank
        (user profile/environment). You cannot know if a task relates to prior memories
        without recalling first.

        Recall is allowed in EVERY bank, including the Racochu-managed source banks
        ('agent-sessions', 'vault', 'obsidian') - use them to consult prior session
        history, architecture/ADRs, and personal notes.

        Use recallMemory (not rememberMemory) to READ anything that already exists in memory.
        Pass the right memory_bank.
        """
        return await handlers.handle_recall(
            router,
            {"query": query, "memory_bank": memory_bank, "limit": limit, "enrich_limit": enrich_limit},
            container,
        )

    @mcp.tool(name="forgetMemory")
    async def forget(
        memory_id: Annotated[str, "Required. ID of the memory to delete (from recallMemory results)."],
        memory_bank: Annotated[str, _MEMORY_BANK_WRITE_DESC],
    ):
        """Permanently delete a memory by ID from a bank.

        When to use: removing stale, wrong, or unwanted USER-SPECIFIC memories from the
        DEFAULT bank (e.g. an outdated preference or fact about the user).

        When NOT to use / HARD RULE:
          - Write discipline: only the DEFAULT non-file bank should be written to.
          - Source-type banks ('agent-sessions', 'vault', 'obsidian') are Racochu-managed
            and RECALL-ONLY - do not delete from them.
          - The default bank holds user profile/environment context, never the canonical
            source of truth for technical details.

        Find the memory_id via recallMemory first.
        """
        return await handlers.handle_forget(
            router, {"memory_id": memory_id, "memory_bank": memory_bank}, None, container
        )

    @mcp.tool(name="updateMemory")
    async def update(
        memory_id: Annotated[str, "Required. ID of the memory to update (from recallMemory results)."],
        memory_bank: Annotated[str, _MEMORY_BANK_WRITE_DESC],
        content: Annotated[str | None, "Optional. New content for the memory."] = None,
        importance: Annotated[
            float | None,
            "Optional. New relative importance 0.0-1.0 for the memory.",
        ] = None,
    ):
        """Update an existing memory's content and/or importance by ID.

        When to use: correcting or refining an existing USER-SPECIFIC memory in the
        DEFAULT bank (e.g. an updated preference or environment fact).

        When NOT to use / HARD RULE:
          - Write discipline: only the DEFAULT non-file bank may be written to.
          - Source-type banks ('agent-sessions', 'vault', 'obsidian') are Racochu-managed
            and RECALL-ONLY - do not update them.
          - The default bank stores user profile/environment, never technical canonical
            truth.

        Find the memory_id via recallMemory first.
        """
        args = {"memory_id": memory_id, "memory_bank": memory_bank}
        if content is not None:
            args["content"] = content
        if importance is not None:
            args["importance"] = importance
        return await handlers.handle_update(router, args)

    @mcp.tool(name="sleep")
    async def sleep_tool(memory_bank: Annotated[str, _MEMORY_BANK_READ_DESC]):
        """Trigger memory consolidation ('sleep') for a bank.

        When to use: after a batch of writes or at a natural stopping point, to let the
        memory system consolidate, deduplicate, and rank memories. It is optional
        housekeeping - not required for read-only workflows.

        Use 'default' (the user profile bank) for memory_bank when consolidating user memories.
        """
        return await handlers.handle_sleep(router, {"memory_bank": memory_bank})

    @mcp.tool(name="getMemoryStats")
    async def stats(memory_bank: Annotated[str, _MEMORY_BANK_READ_DESC]):
        """Get usage statistics for a memory bank.

        When to use: inspecting how many memories a bank holds, its size, or health.
        Useful for observability and capacity checks. Read-only.

        Pass the memory_bank to inspect (e.g. 'default').
        """
        return await handlers.handle_stats(router, {"memory_bank": memory_bank})

    @mcp.tool(name="listMemoryBanks")
    async def list_banks():
        """List all available memory banks.

        When to use: ALWAYS first - before any recall/write - to discover which banks
        (namespaces) exist and to pick the right memory_bank for your next call.
        Banks typically include 'default' (the user profile bank, writable) plus
        Racochu-managed source banks 'agent-sessions', 'vault', 'obsidian' (recall-only).

        Call this tool first in any memory workflow to see live banks.
        """
        return await handlers.handle_list_banks(router, {})

    @mcp.tool(name="registerMemoryBank")
    async def register_bank(
        name: Annotated[str, "Required. Unique name for the new memory bank."],
        description: Annotated[str, "Required. Short description of the bank's purpose."],
    ):
        """Register a new memory bank (namespace).

        When to use: creating a dedicated bank for a new project or context so its user
        memories stay isolated. A new bank is writable for user memories.

        When NOT to use: do NOT create banks to store technical canonical truth - that
        belongs in the vault/codebase. Do not create duplicates of the existing source-type
        banks (agent-sessions/vault/obsidian), which Racochu manages.

        Provide a unique name and a short description of its purpose.
        """
        return await handlers.handle_register_bank(router, {"name": name, "description": description})

    @mcp.tool(name="searchFiles")
    async def search_files(
        query: Annotated[
            str,
            "Required. Natural-language query to match against source-embedded (file) memories.",
        ],
        memory_bank: Annotated[str, _MEMORY_BANK_FILE_DESC],
        limit: Annotated[int, "Optional. Maximum files to return. Default 10."] = 10,
        source_type: Annotated[
            str | None,
            "Optional. Filter by source type (e.g. 'agent-sessions', 'vault', 'obsidian').",
        ] = None,
        file_role: Annotated[str | None, "Optional. Filter by file role."] = None,
        include_relations: Annotated[
            bool,
            "Optional. Whether to include file relations in the response. Default False.",
        ] = False,
    ):
        """Search source-embedded (file) memories across a bank.

        When to use: finding memories that were ingested FROM files (e.g. vault knowledge
        files, session-history chunks) rather than stored as standalone user memories.
        Returns matching files with a file_id and matched chunk info.

        Use for source-type banks ('agent-sessions', 'vault', 'obsidian') to LOCATE the
        file(s) holding relevant knowledge, then use fetchFile / expandFileRelations to
        read or traverse them. Read-only over ingested files.
        """
        args = {"query": query, "memory_bank": memory_bank, "limit": limit, "include_relations": include_relations}
        if source_type is not None:
            args["source_type"] = source_type
        if file_role is not None:
            args["file_role"] = file_role
        return await handlers.handle_search_files(router, args, container)

    @mcp.tool(name="expandFileRelations")
    async def expand_file_relations(
        file_id: Annotated[str, "Required. ID of the file whose relations to expand (from searchFiles)."],
        memory_bank: Annotated[str, _MEMORY_BANK_FILE_DESC],
        relation_types: Annotated[
            list[str] | None,
            "Optional. Only expand these relation types (e.g. references, depends-on).",
        ] = None,
        summary_only: Annotated[
            bool,
            "Optional. Return relation summaries only (cheaper). Default False.",
        ] = False,
    ):
        """Expand file relations for a source-embedded (file) memory.

        When to use: after searchFiles/fetchFile locate a file_id, to discover related files
        (e.g. references, dependents) in the same bank and navigate the knowledge graph.

        Use to follow links between ingested files (vault docs, session notes) to reconstruct
        broader context. Read-only.
        """
        args = {"file_id": file_id, "memory_bank": memory_bank, "summary_only": summary_only}
        if relation_types is not None:
            args["relation_types"] = relation_types
        return await handlers.handle_expand_file_relations(router, args, container)

    @mcp.tool(name="fetchFile")
    async def fetch_file(
        file_id: Annotated[
            str,
            "Required. ID of the file to fetch (from searchFiles/expandFileRelations/recallMemory).",
        ],
        memory_bank: Annotated[str, _MEMORY_BANK_FILE_DESC],
        include_metadata: Annotated[
            bool,
            "Optional. Include file metadata in the response. Default False.",
        ] = False,
        center_chunk_index: Annotated[
            int | None,
            "Optional. The `chunk_index` VALUE of the center chunk, as returned by "
            "fetchFile/searchFiles/recallMemory (0-based; round-trip it, don't compute a "
            "position). Error if no chunk has that value (details carry "
            "available_chunk_indexes). Default None (whole file).",
        ] = None,
        adjacent_chunks: Annotated[
            int,
            "Optional. Number of chunks on each side of the center in neighbor mode. "
            "Valid range 0-5. Default 1.",
        ] = 1,
    ):
        """Fetch and reconstruct file content from its memory chunks.

        When to use: reading the actual content of a source-embedded (file) memory you found
        via searchFiles/expandFileRelations/recallMemory.

        By default (no center_chunk_index) the whole file is reconstructed from all chunks.
        With center_chunk_index set, only the clamped neighbor window around the matched
        center chunk is returned, each chunk with content, position (chunk_index,
        start_line/end_line) and section_header.

        Read-only over ingested source files.
        """
        args = {"file_id": file_id, "memory_bank": memory_bank, "include_metadata": include_metadata}
        if center_chunk_index is not None:
            args["center_chunk_index"] = center_chunk_index
            args["adjacent_chunks"] = adjacent_chunks
        return await handlers.handle_fetch_file(router, args, container)


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
