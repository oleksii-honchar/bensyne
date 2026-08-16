"""E2E tests that verify stateless MCP mode works correctly.

Bensyne runs with stateless_http=True, meaning no session initialization
is required. Each request works independently.
"""

from __future__ import annotations

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers — copied from test_mcp_tools.py (no session_id)
# ---------------------------------------------------------------------------


def _parse_sse_json(text: str) -> dict:
    """Parse a single SSE event's data field as JSON.

    SSE format: "event: message\\ndata: {...}\\n\\n"
    """
    for line in text.strip().split("\n"):
        if line.startswith("data: "):
            return __import__("json").loads(line[6:])
    raise ValueError(f"No SSE data found in response: {text!r}")


def mcp_call_tool(client: httpx.Client, tool_name: str, arguments: dict, request_id: int) -> dict:
    """Call an MCP tool and return the result.

    FastMCP 3.x returns structuredContent when available, otherwise parses text content.
    """
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments,
            },
        },
    )
    resp.raise_for_status()
    result = _parse_sse_json(resp.text)
    assert "error" not in result, f"MCP error calling {tool_name}: {result.get('error')}"
    tool_result = result.get("result", {})
    # FastMCP 3.x provides structuredContent for dict returns
    if "structuredContent" in tool_result:
        return tool_result["structuredContent"]
    # Fall back to parsing text content
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


class TestListBanksWithoutSession:
    """listMemoryBanks works without session initialization."""

    def test_list_banks_no_session(self, mcp_client: httpx.Client) -> None:
        """Call listMemoryBanks with no prior session init — should succeed."""
        result = mcp_call_tool(
            mcp_client,
            "listMemoryBanks",
            {},
            request_id=100,
        )
        assert "banks" in result
        assert isinstance(result["banks"], list)


class TestMemoryOpsWithoutSession:
    """rememberMemory + recallMemory sequence works without session initialization."""

    def test_remember_and_recall_no_session(self, mcp_client: httpx.Client) -> None:
        """Store a memory, recall it — all without session init."""
        bank = "e2e-stateless-ops"

        # Remember
        remember_result = mcp_call_tool(
            mcp_client,
            "rememberMemory",
            {"content": "stateless mode memory test", "memory_bank": bank},
            request_id=200,
        )
        assert remember_result["status"] == "stored"
        assert remember_result["memory_bank"] == bank
        assert "memory_id" in remember_result
        memory_id = remember_result["memory_id"]

        # Recall — same request, no session needed
        recall_result = mcp_call_tool(
            mcp_client,
            "recallMemory",
            {"query": "stateless mode memory test", "memory_bank": bank},
            request_id=201,
        )
        assert recall_result["memory_bank"] == bank
        assert "results" in recall_result
        results = recall_result["results"]
        assert len(results) >= 1
        matching = [r for r in results if r.get("id") == memory_id]
        assert len(matching) == 1, f"Expected memory_id {memory_id} in results: {results}"


class TestSequentialCallsWithoutSession:
    """Multiple sequential tool calls succeed without session initialization."""

    def test_sequential_calls_no_session(self, mcp_client: httpx.Client) -> None:
        """Chain 4 different tool calls without session init — all should succeed."""
        bank = "e2e-stateless-seq"

        # Call 1: list banks
        list_result = mcp_call_tool(
            mcp_client,
            "listMemoryBanks",
            {},
            request_id=300,
        )
        assert "banks" in list_result

        # Call 2: remember
        remember_result = mcp_call_tool(
            mcp_client,
            "rememberMemory",
            {"content": "sequential call one", "memory_bank": bank},
            request_id=301,
        )
        assert remember_result["status"] == "stored"

        # Call 3: recall
        recall_result = mcp_call_tool(
            mcp_client,
            "recallMemory",
            {"query": "sequential call one", "memory_bank": bank},
            request_id=302,
        )
        assert recall_result["memory_bank"] == bank
        assert len(recall_result["results"]) >= 1

        # Call 4: stats
        stats_result = mcp_call_tool(
            mcp_client,
            "getMemoryStats",
            {"memory_bank": bank},
            request_id=303,
        )
        assert stats_result["memory_bank"] == bank
        assert "stats" in stats_result
        assert isinstance(stats_result["stats"], dict)
