"""Tests that every bensyne-mcp tool (and its ``memory_bank`` parameter) ships with an
elaborate, non-empty description in the MCP tool schema.

Rationale: agents may use bensyne via the gateway *without* loading the bensyne skill.
The tool schema is therefore the authoritative place to teach:
  * what each tool does, when to use it, when NOT to use it;
  * the write discipline (default non-file bank only for writes);
  * that source-type banks (agent-sessions / vault / obsidian) are recall-only;
  * recall-first awareness (recall agent-sessions + default bank at task start).

These tests introspect the live FastMCP tool registry so the schema — not just source
docstrings — is what is guaranteed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastmcp import FastMCP

from src.app import register_tools

# The 11 tools that must be exposed.
EXPECTED_TOOLS = {
    "rememberMemory",
    "recallMemory",
    "forgetMemory",
    "updateMemory",
    "sleep",
    "getMemoryStats",
    "listMemoryBanks",
    "registerMemoryBank",
    "searchFiles",
    "expandFileRelations",
    "fetchFile",
}

# Tools that accept a ``memory_bank`` parameter.
MEMORY_BANK_TOOLS = {
    "rememberMemory",
    "recallMemory",
    "forgetMemory",
    "updateMemory",
    "sleep",
    "getMemoryStats",
    "searchFiles",
    "expandFileRelations",
    "fetchFile",
}


@pytest.fixture
async def mcp_tools() -> dict[str, object]:
    """Build a real FastMCP server, register all tools with a stub router, and return
    a name -> tool map (with ``.name``, ``.description``, ``.parameters``).

    pytest is configured with ``asyncio_mode = "auto"``, so this async fixture runs
    on a managed event loop (no manual asyncio.run needed)."""
    mcp = FastMCP(name="bensyne-description-test")
    router = MagicMock()
    register_tools(mcp, router, None)
    tools = await mcp.list_tools()
    return {t.name: t for t in tools}


def _tool_descriptions(mcp_tools: dict[str, object]) -> dict[str, str]:
    return {name: (tool.description or "").strip() for name, tool in mcp_tools.items()}


def _memory_bank_param_desc(mcp_tools: dict[str, object]) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, tool in mcp_tools.items():
        props = tool.parameters.get("properties", {}) if hasattr(tool, "parameters") else {}
        mb = props.get("memory_bank") or {}
        result[name] = (mb.get("description") or "").strip()
    return result


class TestToolRegistrationCompleteness:
    async def test_all_eleven_tools_are_registered(self, mcp_tools) -> None:
        """All 11 bensyne tools must be present in the tool registry."""
        missing = EXPECTED_TOOLS - set(mcp_tools)
        assert not missing, f"Missing tools in registry: {sorted(missing)}"


class TestToolDescriptions:
    async def test_every_tool_has_a_nonempty_elaborate_description(self, mcp_tools) -> None:
        """Every registered tool must carry a non-empty, non-trivial description."""
        descs = _tool_descriptions(mcp_tools)
        bad = [
            name
            for name in EXPECTED_TOOLS
            if name not in descs or len(descs[name]) < 40
        ]
        assert not bad, (
            "Tools with empty or non-elaborate descriptions (need >=40 chars): "
            + ", ".join(sorted(bad))
        )

    async def test_descriptions_mention_usage_guidance(self, mcp_tools) -> None:
        """Descriptions must guide usage: say what the tool does AND when to use it.

        We assert each tool description contains at least one "when/usage" cue so the
        schema teaches usage to agents that never load the bensyne skill.
        """
        descs = _tool_descriptions(mcp_tools)
        cues = ("use", "when", "call", "run", "for ")
        bad = [
            name
            for name in EXPECTED_TOOLS
            if not any(cue in descs.get(name, "").lower() for cue in cues)
        ]
        assert not bad, f"Tool descriptions lacking usage guidance: {sorted(bad)}"


class TestMemoryBankParamDescriptions:
    async def test_memory_bank_param_has_nonempty_description_where_present(
        self, mcp_tools
    ) -> None:
        """Every tool taking ``memory_bank`` must describe it (which banks exist,
        which are recall-only)."""
        descs = _memory_bank_param_desc(mcp_tools)
        missing = [
            name
            for name in MEMORY_BANK_TOOLS
            if len(descs.get(name, "")) < 20
        ]
        assert not missing, (
            "Tools whose memory_bank param lacks a description: " + ", ".join(sorted(missing))
        )


class TestWriteDisciplineEncoded:
    """Content requirements: the schema must encode write discipline, recall-only
    source banks, and recall-first awareness."""

    async def test_recall_memory_encodes_recall_first_awareness(self, mcp_tools) -> None:
        """recallMemory must teach: recall is allowed in every bank; at task start,
        recall agent-sessions + default bank first to build awareness."""
        desc = _tool_descriptions(mcp_tools)["recallMemory"].lower()
        assert "agent-sessions" in desc, "recallMemory must reference the agent-sessions bank"
        assert "default" in desc, "recallMemory must reference the default bank"
        assert ("first" in desc or "start" in desc), (
            "recallMemory must teach recall-first awareness (task start)"
        )

    async def test_write_tools_encode_default_bank_only(self, mcp_tools) -> None:
        """rememberMemory/updateMemory/forgetMemory must teach: write only the default
        non-file bank; source-type banks are recall-only; never technical truth."""
        descs = {n: _tool_descriptions(mcp_tools)[n].lower() for n in
                 ("rememberMemory", "updateMemory", "forgetMemory")}
        for name, desc in descs.items():
            assert "default" in desc, f"{name} must reference the default bank"
            assert (
                "recall-only" in desc or "read-only" in desc or "never write" in desc
            ), f"{name} must state that source-type banks are recall-only"
            assert "technical" in desc or "canonical" in desc or "source of truth" in desc, (
                f"{name} must warn against storing technical canonical truth"
            )

    async def test_source_banks_listed_as_recall_only_on_write_tools(self, mcp_tools) -> None:
        """Write-tool descriptions should name the recall-only source-type banks."""
        recall_only_banks = ("agent-sessions", "vault", "obsidian")
        remember_desc = _tool_descriptions(mcp_tools)["rememberMemory"].lower()
        # At least the primary source banks should be named.
        assert "agent-sessions" in remember_desc, (
            "rememberMemory must name the agent-sessions (recall-only) bank"
        )
        assert "vault" in remember_desc, "rememberMemory must name the vault (recall-only) bank"

    async def test_list_memory_banks_encodes_discovery_first(self, mcp_tools) -> None:
        """listMemoryBanks must teach: run it first to discover available banks."""
        desc = _tool_descriptions(mcp_tools)["listMemoryBanks"].lower()
        assert "first" in desc or "discover" in desc or "before" in desc, (
            "listMemoryBanks must teach running it first to discover banks"
        )

    async def test_file_tools_explain_source_embedded_memories(self, mcp_tools) -> None:
        """searchFiles/fetchFile/expandFileRelations must explain they access
        source-embedded (file) memories."""
        descs = {
            n: _tool_descriptions(mcp_tools)[n].lower()
            for n in ("searchFiles", "fetchFile", "expandFileRelations")
        }
        for name, desc in descs.items():
            assert "file" in desc or "source" in desc, (
                f"{name} must explain it works on file/source memories"
            )
