"""Tests that every bensyne-mcp tool (and its ``memory_bank`` parameter) ships with an
elaborate, non-empty description in the MCP tool schema.

Rationale: agents may use bensyne via the gateway *without* loading the bensyne skill.
The tool schema is therefore the authoritative place to teach:
  * what each tool does, when to use it, when NOT to use it;
  * the write discipline (the resolved user bank 'user_<id>' only for writes);
  * that source-type banks (agent-sessions_{user_id} / vault / obsidian) are recall-only;
  * recall-first awareness (recall user_<id> + agent-sessions_{user_id} at task start);
  * that 'default' / 'agent-sessions' are legacy shells and must not be used.

These tests introspect the live FastMCP tool registry so the schema — not just source
docstrings — is what is guaranteed.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from fastmcp import FastMCP

from src.app import register_tools
from src.infrastructure.mcp.schemas import MEMORY_BANK_PARAM

# The 15 tools that must be exposed.
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
    "forgetFile",
    "getFileChunks",
    "getPersonaStatus",
    "searchMemoryBank",
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
    "forgetFile",
    "getFileChunks",
    "getPersonaStatus",
}


@pytest.fixture
async def mcp_tools() -> dict[str, object]:
    """Build a real FastMCP server, register all tools with a stub router, and return
    a name -> tool map (with ``.name``, ``.description``, ``.parameters``).

    pytest is configured with ``asyncio_mode = "auto"``, so this async fixture runs
    on a managed event loop (no manual asyncio.run needed)."""
    mcp = FastMCP(name="bensyne-description-test")
    router = MagicMock()
    register_tools(mcp, router, MagicMock(), None)
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
    async def test_all_twelve_tools_are_registered(self, mcp_tools) -> None:
        """All 12 bensyne tools must be present in the tool registry."""
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
        recall user_<id> + agent-sessions_{user_id} first to build awareness."""
        desc = _tool_descriptions(mcp_tools)["recallMemory"].lower()
        assert "agent-sessions_{user_id}" in desc, (
            "recallMemory must reference the agent-sessions_{user_id} bank"
        )
        assert "user_<id>" in desc, "recallMemory must reference the user_<id> bank"
        assert ("first" in desc or "start" in desc), (
            "recallMemory must teach recall-first awareness (task start)"
        )

    async def test_recall_memory_marks_legacy_banks(self, mcp_tools) -> None:
        """recallMemory must mark 'default'/'agent-sessions' as legacy shells
        (deleted 2026-08-29), not as banks to use."""
        desc = _tool_descriptions(mcp_tools)["recallMemory"].lower()
        assert "legacy" in desc, (
            "recallMemory must mark default/agent-sessions as legacy"
        )
        assert "deleted" in desc, (
            "recallMemory must note the legacy banks were deleted"
        )

    async def test_write_tools_encode_resolved_user_bank_only(self, mcp_tools) -> None:
        """rememberMemory/updateMemory/forgetMemory must teach: write to the RESOLVED
        user bank 'user_<id>' only; source-type banks are recall-only; never technical
        truth."""
        descs = {n: _tool_descriptions(mcp_tools)[n].lower() for n in
                 ("rememberMemory", "updateMemory", "forgetMemory")}
        for name, desc in descs.items():
            assert "user_<id>" in desc, f"{name} must name the resolved user bank"
            assert "resolved user bank" in desc, (
                f"{name} must teach the resolved user bank as the write target"
            )
            assert (
                "recall-only" in desc or "read-only" in desc or "never write" in desc
            ), f"{name} must state that source-type banks are recall-only"
            assert "technical" in desc or "canonical" in desc or "source of truth" in desc, (
                f"{name} must warn against storing technical canonical truth"
            )

    async def test_source_banks_listed_as_recall_only_on_write_tools(self, mcp_tools) -> None:
        """Write-tool descriptions should name the recall-only user-suffixed
        source-type banks."""
        remember_desc = _tool_descriptions(mcp_tools)["rememberMemory"].lower()
        # At least the primary source banks should be named with the user-suffixed
        # session bank (not the bare legacy 'agent-sessions').
        assert "agent-sessions_{user_id}" in remember_desc, (
            "rememberMemory must name the agent-sessions_{user_id} (recall-only) bank"
        )
        assert "vault" in remember_desc, "rememberMemory must name the vault (recall-only) bank"

    async def test_stats_and_list_banks_teach_empty_bank_note(self, mcp_tools) -> None:
        """getMemoryStats / listMemoryBanks must name 'user_<id>' as the user profile
        bank and teach that an empty bank means 'no context yet' (not authoritative)."""
        descs = _tool_descriptions(mcp_tools)
        for name in ("getMemoryStats", "listMemoryBanks"):
            desc = descs[name].lower()
            assert "user_<id>" in desc, (
                f"{name} must name the user_<id> user profile bank"
            )
            assert "empty" in desc and "no context yet" in desc, (
                f"{name} must teach the empty-bank = no-context-yet note"
            )

    async def test_search_memory_bank_names_user_suffixed_inclusion(self, mcp_tools) -> None:
        """searchMemoryBank must teach that user-suffixed banks are always included in
        results so the user profile and prior-session context are never hidden."""
        desc = _tool_descriptions(mcp_tools)["searchMemoryBank"].lower()
        assert "user_<id>" in desc, (
            "searchMemoryBank must name the user_<id> bank"
        )
        assert "agent-sessions_{user_id}" in desc, (
            "searchMemoryBank must name the agent-sessions_{user_id} bank"
        )
        assert "always included" in desc or "never hidden" in desc, (
            "searchMemoryBank must teach user-suffixed banks are always included"
        )

    async def test_recall_memory_param_names_resolved_and_legacy_banks(self, mcp_tools) -> None:
        """The memory_bank parameter on recallMemory (from _MEMORY_BANK_READ_DESC) must
        name user_<id> / agent-sessions_{user_id} and mark default/agent-sessions legacy."""
        desc = _memory_bank_param_desc(mcp_tools)["recallMemory"].lower()
        assert "user_<id>" in desc, "recallMemory memory_bank param must name user_<id>"
        assert "agent-sessions_{user_id}" in desc, (
            "recallMemory memory_bank param must name agent-sessions_{user_id}"
        )
        assert "legacy" in desc, (
            "recallMemory memory_bank param must mark default/agent-sessions as legacy"
        )

    async def test_list_memory_banks_marks_diagnostic(self, mcp_tools) -> None:
        """listMemoryBanks must teach: it is diagnostic / full enumeration — NOT the
        default first-step discovery tool (that role is now searchMemoryBank's)."""
        desc = _tool_descriptions(mcp_tools)["listMemoryBanks"].lower()
        assert "diagnostic" in desc or "enumeration" in desc, (
            "listMemoryBanks must mark itself as diagnostic or full enumeration"
        )
        # Must NOT teach "run it first" / "before" — those cues are now searchMemoryBank's.
        assert not (
            "first - before" in desc or "call this tool first" in desc
        ), (
            "listMemoryBanks must NOT teach 'run it first'; that wording is reserved "
            "for searchMemoryBank"
        )

    async def test_search_memory_bank_encodes_prefer(self, mcp_tools) -> None:
        """searchMemoryBank must teach: prefer it over listMemoryBanks for scoped
        discovery; listMemoryBanks is the diagnostic fallback."""
        desc = _tool_descriptions(mcp_tools)["searchMemoryBank"].lower()
        assert "prefer" in desc, (
            "searchMemoryBank must teach it is the preferred discovery tool"
        )
        assert "listmemorybanks" in desc, (
            "searchMemoryBank must reference listMemoryBanks as the fallback"
        )

    async def test_search_memory_bank_has_required_query_param(self, mcp_tools) -> None:
        """searchMemoryBank schema must declare ``query`` as a required string param."""
        tool = mcp_tools["searchMemoryBank"]
        props = tool.parameters.get("properties", {}) if hasattr(tool, "parameters") else {}
        query_param = props.get("query")
        assert query_param is not None, "searchMemoryBank must declare a query parameter"
        assert query_param.get("type") == "string", "searchMemoryBank query must be a string"
        required = tool.parameters.get("required", []) if hasattr(tool, "parameters") else []
        assert "query" in required, "searchMemoryBank must mark query as required"

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

    async def test_forget_file_marks_operator_only_destructive(self, mcp_tools) -> None:
        """forgetFile is an operator-only, destructive, file-granular tool — the schema
        must say so, since it is NOT part of the skills recall-only surface agents use."""
        desc = _tool_descriptions(mcp_tools)["forgetFile"].lower()
        assert "operator" in desc, (
            "forgetFile must state it is an operator-only tool"
        )
        assert any(
            cue in desc for cue in ("destructive", "permanently", "irreversible")
        ), "forgetFile must state it is destructive"
        assert (
            "not part of" in desc or "not for agents" in desc or "not recall" in desc
        ), "forgetFile must clarify it is outside the agent recall-only surface"


class TestMemoryBankParamSchema:
    """Direct assertions on the MEMORY_BANK_PARAM constant in schemas.py (used by the
    gateway-side tool schemas), independent of the FastMCP registry."""

    def test_memory_bank_param_names_user_suffixed_banks_and_legacy(self) -> None:
        """MEMORY_BANK_PARAM must name the user profile / prior-context banks and mark
        default/agent-sessions as legacy shells."""
        desc = MEMORY_BANK_PARAM["memory_bank"]["description"].lower()
        assert "user_<id>" in desc, "MEMORY_BANK_PARAM must name the user_<id> bank"
        assert "agent-sessions_{user_id}" in desc, (
            "MEMORY_BANK_PARAM must name the agent-sessions_{user_id} bank"
        )
        assert "recall-only" in desc, (
            "MEMORY_BANK_PARAM must mark vault/obsidian recall-only"
        )
        assert "legacy" in desc, (
            "MEMORY_BANK_PARAM must mark default/agent-sessions as legacy"
        )
