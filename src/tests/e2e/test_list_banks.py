"""E2E tests for list_banks tool.

Verifies list_banks reflects active memory banks via actual MCP protocol.
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


def mcp_call_tool(client: httpx.Client, tool_name: str, arguments: dict, request_id: int) -> dict:
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


class TestListBanks:
    """list_banks reflects active memory banks."""

    def test_lists_default(self, mcp_client: httpx.Client) -> None:
        """Verify default memory bank is listed at start."""
        result = mcp_call_tool(
            mcp_client,
            "memory_list_banks",
            {},
            request_id=10,
        )
        assert "banks" in result
        names = {bank["name"] for bank in result["banks"]}
        assert "default" in names, "Default memory bank should always be listed"

    def test_lists_new_bank(self, mcp_client: httpx.Client) -> None:
        """After using a new memory bank, verify it appears in list_banks."""
        new_bank = "e2e-list-new-bank"

        # Use the new memory bank
        mcp_call_tool(
            mcp_client,
            "memory_remember",
            {"content": "activating memory bank", "memory_bank": new_bank},
            request_id=20,
        )

        # Verify it appears
        result = mcp_call_tool(
            mcp_client,
            "memory_list_banks",
            {},
            request_id=21,
        )
        names = {bank["name"] for bank in result["banks"]}
        assert new_bank in names, f"Memory bank {new_bank} should appear after first use"

        # Verify each entry has required fields
        for bank in result["banks"]:
            assert "name" in bank
            assert "bank" in bank
            assert "status" in bank
            assert "memory_count" in bank
