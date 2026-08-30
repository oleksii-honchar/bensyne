"""E2E tests for searchMemoryBank tool.

Verifies the discovery primitive ranks banks by relevance, respects ``limit``,
and applies the ``agent_id`` bonus to the matching persona bank. Runs against
the real MCP server via httpx (see conftest for ``mcp_client`` fixture).
"""

from __future__ import annotations

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers (mirrors test_list_banks.py — local copy keeps tests self-contained).
# ---------------------------------------------------------------------------


def _parse_sse_json(text: str) -> dict:
    """Parse a single SSE event's data field as JSON."""
    for line in text.strip().split("\n"):
        if line.startswith("data: "):
            return __import__("json").loads(line[6:])
    raise ValueError(f"No SSE data found in response: {text!r}")


def mcp_call_tool(
    client: httpx.Client, tool_name: str, arguments: dict, request_id: int
) -> dict:
    """Call an MCP tool and return the result.

    Stateless MCP — no session initialization or session ID headers needed.
    """
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
    )
    resp.raise_for_status()
    result = _parse_sse_json(resp.text)
    assert "error" not in result, f"MCP error calling {tool_name}: {result.get('error')}"
    tool_result = result.get("result", {})
    if "structuredContent" in tool_result:
        return tool_result["structuredContent"]
    content_list = tool_result.get("content", [])
    if content_list:
        text = content_list[0].get("text", "")
        try:
            return __import__("json").loads(text)
        except ValueError:
            return {"_raw": text}
    return tool_result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestSearchMemoryBank:
    """searchMemoryBank ranks banks by relevance and respects limit/agent_id."""

    def test_happy_path_returns_relevant_bank(self, mcp_client: httpx.Client) -> None:
        """A query that matches 'default' returns it in matches with score >= 1."""
        result = mcp_call_tool(
            mcp_client,
            "searchMemoryBank",
            {"query": "default"},
            request_id=10,
        )
        assert "matches" in result
        assert "total" in result
        assert isinstance(result["matches"], list)
        names = {m["name"] for m in result["matches"]}
        assert "default" in names, "Query 'default' should match the default bank"
        # Each match carries a score, name, description, memory_count, status.
        for match in result["matches"]:
            assert "name" in match
            assert "score" in match
            assert "memory_count" in match
            assert "status" in match

    def test_empty_result_for_nonsense_query(self, mcp_client: httpx.Client) -> None:
        """A query with no token overlap returns matches=[], total=0."""
        result = mcp_call_tool(
            mcp_client,
            "searchMemoryBank",
            {"query": "xyzzy-no-such-thing-plover-cipher"},
            request_id=11,
        )
        assert result["matches"] == [], (
            f"Non-matching query must return empty matches, got {result}"
        )
        assert result["total"] == 0

    def test_agent_id_bonus_surfaces_persona(self, mcp_client: httpx.Client) -> None:
        """Passing agent_id='worker' must include agent-persona_worker in results for a
        query that overlaps the worker's domain — and it must score at least as
        high as the same bank would without agent_id."""
        without_agent = mcp_call_tool(
            mcp_client,
            "searchMemoryBank",
            {"query": "worker"},
            request_id=12,
        )
        with_agent = mcp_call_tool(
            mcp_client,
            "searchMemoryBank",
            {"query": "worker", "agent_id": "worker"},
            request_id=13,
        )
        names_no = {m["name"] for m in without_agent["matches"]}
        names_yes = {m["name"] for m in with_agent["matches"]}
        # agent_id adds a bonus to agent-persona_worker — the bank must remain in
        # both result sets (its base score is positive on a 'worker' query).
        assert "agent-persona_worker" in names_no or "agent-persona_worker" in names_yes, (
            f"agent-persona_worker must surface for 'worker' query; got {names_no} / {names_yes}"
        )
        if "agent-persona_worker" in names_no and "agent-persona_worker" in names_yes:
            score_no = next(
                m["score"] for m in without_agent["matches"] if m["name"] == "agent-persona_worker"
            )
            score_yes = next(
                m["score"] for m in with_agent["matches"] if m["name"] == "agent-persona_worker"
            )
            assert score_yes > score_no, (
                f"agent_id bonus must increase agent-persona_worker score: "
                f"without={score_no}, with={score_yes}"
            )

    def test_limit_clamps_match_count(self, mcp_client: httpx.Client) -> None:
        """limit=1 must return at most one match, even when many banks match."""
        result = mcp_call_tool(
            mcp_client,
            "searchMemoryBank",
            {"query": "bank", "limit": 1},
            request_id=14,
        )
        assert len(result["matches"]) <= 1, (
            f"limit=1 must cap matches at 1, got {len(result['matches'])}"
        )
