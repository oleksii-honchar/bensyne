"""E2E tests for memory bank routing and data isolation.

Verifies multiple memory banks, data isolation between them, and the default bank.
"""

from __future__ import annotations

import httpx
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_sse_json(text: str) -> dict:
    """Parse a single SSE event's data field as JSON."""
    for line in text.strip().split("\n"):
        if line.startswith("data: "):
            return __import__("json").loads(line[6:])
    raise ValueError(f"No SSE data found in response: {text!r}")


def mcp_init(client: httpx.Client) -> tuple[dict, str]:
    """Initialize MCP session and return (response, session_id)."""
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "e2e-bank-test", "version": "1.0.0"},
            },
        },
    )
    resp.raise_for_status()
    session_id = resp.headers.get("mcp-session-id", "")
    return _parse_sse_json(resp.text), session_id


def mcp_call_tool(client: httpx.Client, tool_name: str, arguments: dict, request_id: int, session_id: str) -> dict:
    """Call an MCP tool and return the result."""
    headers = {"Mcp-Session-Id": session_id} if session_id else {}
    resp = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": request_id,
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
        headers=headers,
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


class TestIsolatedMemoryBanks:
    """Memories stored in one memory bank are not visible in another."""

    def test_isolated_memory_banks(self, mcp_client: httpx.Client) -> None:
        """Store in memory bank A, verify not found in memory bank B."""
        _, session_id = mcp_init(mcp_client)

        # Store unique content in memory bank A
        mcp_call_tool(
            mcp_client,
            "memory_remember",
            {"content": "secret of memory bank A", "memory_bank": "e2e-bank-a"},
            request_id=10,
            session_id=session_id,
        )

        # Store unique content in memory bank B
        mcp_call_tool(
            mcp_client,
            "memory_remember",
            {"content": "secret of memory bank B", "memory_bank": "e2e-bank-b"},
            request_id=11,
            session_id=session_id,
        )

        # Recall from memory bank A should NOT find memory bank B's content
        recall_a = mcp_call_tool(
            mcp_client,
            "memory_recall",
            {"query": "secret of memory bank B", "memory_bank": "e2e-bank-a"},
            request_id=12,
            session_id=session_id,
        )
        # Filter results for exact phrase match
        found = any("secret of memory bank B" in r.get("content", "") for r in recall_a["results"])
        assert not found, "Memory bank A should not see memory bank B's memories"

        # Recall from memory bank B should NOT find memory bank A's content
        recall_b = mcp_call_tool(
            mcp_client,
            "memory_recall",
            {"query": "secret of memory bank A", "memory_bank": "e2e-bank-b"},
            request_id=13,
            session_id=session_id,
        )
        found = any("secret of memory bank A" in r.get("content", "") for r in recall_b["results"])
        assert not found, "Memory bank B should not see memory bank A's memories"


class TestDefaultBankFallback:
    """The 'default' memory bank is always available."""

    def test_default_memory_bank_is_valid(self, mcp_client: httpx.Client) -> None:
        """Store and recall using explicit 'default' memory bank — still works."""
        _, session_id = mcp_init(mcp_client)

        # Store with explicit "default" memory bank
        remember_result = mcp_call_tool(
            mcp_client,
            "memory_remember",
            {"content": "default memory bank memory", "memory_bank": "default"},
            request_id=20,
            session_id=session_id,
        )
        assert remember_result["memory_bank"] == "default"
        memory_id = remember_result["memory_id"]

        # Recall with explicit "default" memory bank — should find it
        recall_result = mcp_call_tool(
            mcp_client,
            "memory_recall",
            {"query": "default memory bank memory", "memory_bank": "default"},
            request_id=21,
            session_id=session_id,
        )
        assert recall_result["memory_bank"] == "default"
        matching = [r for r in recall_result["results"] if r.get("id") == memory_id]
        assert len(matching) == 1


class TestConcurrentMemoryBanks:
    """Multiple memory banks active simultaneously."""

    def test_concurrent_memory_banks(self, mcp_client: httpx.Client) -> None:
        """Use multiple memory banks simultaneously, all return correct data."""
        _, session_id = mcp_init(mcp_client)

        banks = ["e2e-conc-1", "e2e-conc-2", "e2e-conc-3"]
        memory_ids: dict[str, str] = {}

        # Store in each memory bank
        for i, bank in enumerate(banks, start=30):
            result = mcp_call_tool(
                mcp_client,
                "memory_remember",
                {"content": f"concurrent memory for {bank}", "memory_bank": bank},
                request_id=i,
                session_id=session_id,
            )
            assert result["memory_bank"] == bank
            memory_ids[bank] = result["memory_id"]

        # Recall from each memory bank
        for i, bank in enumerate(banks, start=40):
            recall = mcp_call_tool(
                mcp_client,
                "memory_recall",
                {"query": f"concurrent memory for {bank}", "memory_bank": bank},
                request_id=i,
                session_id=session_id,
            )
            assert recall["memory_bank"] == bank
            matching = [r for r in recall["results"] if r.get("id") == memory_ids[bank]]
            assert len(matching) == 1, f"Expected memory in memory bank {bank}"
