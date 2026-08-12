"""E2E tests for MCP tools via streamable HTTP transport.

Tests remember, recall, forget, update, sleep, stats against a real running server.
"""

from __future__ import annotations

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
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


class TestRememberAndRecall:
    """remember and recall end-to-end."""

    def test_remember_and_recall(self, mcp_client: httpx.Client) -> None:
        """Store a memory, recall it, verify content is returned."""
        bank = "e2e-tools-test"

        # Remember
        remember_result = mcp_call_tool(
            mcp_client,
            "rememberMemory",
            {"content": "e2e test memory alpha", "memory_bank": bank},
            request_id=10,
        )
        assert remember_result["status"] == "stored"
        assert remember_result["memory_bank"] == bank
        assert "memory_id" in remember_result
        memory_id = remember_result["memory_id"]

        # Recall
        recall_result = mcp_call_tool(
            mcp_client,
            "recallMemory",
            {"query": "e2e test memory alpha", "memory_bank": bank},
            request_id=11,
        )
        assert recall_result["memory_bank"] == bank
        assert "results" in recall_result
        # At least one result should match our stored memory
        results = recall_result["results"]
        assert len(results) >= 1
        # Find the result matching our memory_id
        matching = [r for r in results if r.get("id") == memory_id]
        assert len(matching) == 1, f"Expected memory_id {memory_id} in results: {results}"


class TestForget:
    """forget end-to-end."""

    def test_forget(self, mcp_client: httpx.Client) -> None:
        """Store a memory, delete it, verify it is gone."""
        bank = "e2e-forget-test"

        # Remember
        remember_result = mcp_call_tool(
            mcp_client,
            "rememberMemory",
            {"content": "to be forgotten", "memory_bank": bank},
            request_id=20,
        )
        memory_id = remember_result["memory_id"]

        # Forget
        forget_result = mcp_call_tool(
            mcp_client,
            "forgetMemory",
            {"memory_id": memory_id, "memory_bank": bank},
            request_id=21,
        )
        assert forget_result["status"] == "deleted"
        assert forget_result["memory_id"] == memory_id
        assert forget_result["memory_bank"] == bank

        # Verify gone via recall
        recall_result = mcp_call_tool(
            mcp_client,
            "recallMemory",
            {"query": "to be forgotten", "memory_bank": bank},
            request_id=22,
        )
        matching = [r for r in recall_result["results"] if r.get("id") == memory_id]
        assert len(matching) == 0, "Forgotten memory should not appear in recall"


class TestUpdate:
    """update end-to-end."""

    def test_update(self, mcp_client: httpx.Client) -> None:
        """Store a memory, update its content, verify new content."""
        bank = "e2e-update-test"

        # Remember
        remember_result = mcp_call_tool(
            mcp_client,
            "rememberMemory",
            {"content": "original content", "memory_bank": bank},
            request_id=30,
        )
        memory_id = remember_result["memory_id"]

        # Update
        update_result = mcp_call_tool(
            mcp_client,
            "updateMemory",
            {"memory_id": memory_id, "content": "updated content", "memory_bank": bank},
            request_id=31,
        )
        assert update_result["status"] == "updated"
        assert update_result["memory_id"] == memory_id
        assert update_result["memory_bank"] == bank

        # Verify via recall
        recall_result = mcp_call_tool(
            mcp_client,
            "recallMemory",
            {"query": "updated content", "memory_bank": bank},
            request_id=32,
        )
        matching = [r for r in recall_result["results"] if r.get("id") == memory_id]
        assert len(matching) == 1, "Updated memory should be found by new content"


class TestStats:
    """stats end-to-end."""

    def test_stats(self, mcp_client: httpx.Client) -> None:
        """Verify stats endpoint returns valid data for a memory bank."""
        bank = "e2e-stats-test"

        # Store a memory first
        mcp_call_tool(
            mcp_client,
            "rememberMemory",
            {"content": "stats test memory", "memory_bank": bank},
            request_id=40,
        )

        # Get stats
        stats_result = mcp_call_tool(
            mcp_client,
            "getMemoryStats",
            {"memory_bank": bank},
            request_id=41,
        )
        assert stats_result["memory_bank"] == bank
        assert "stats" in stats_result
        # Stats should contain some numeric counters
        stats = stats_result["stats"]
        assert isinstance(stats, dict)


class TestSleep:
    """sleep end-to-end."""

    def test_sleep(self, mcp_client: httpx.Client) -> None:
        """Verify sleep runs without error on a memory bank."""
        bank = "e2e-sleep-test"

        sleep_result = mcp_call_tool(
            mcp_client,
            "sleep",
            {"memory_bank": bank},
            request_id=50,
        )
        assert sleep_result["memory_bank"] == bank
        # sleep should return a result dict (exact shape depends on mnemosyne-oss)
        assert isinstance(sleep_result, dict)
