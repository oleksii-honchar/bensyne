"""E2E tests for list_namespaces tool.

Verifies list_namespaces reflects active namespaces via actual MCP protocol.
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
                "clientInfo": {"name": "e2e-list-ns-test", "version": "1.0.0"},
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


class TestListNamespaces:
    """list_namespaces reflects active namespaces."""

    def test_lists_default(self, mcp_client: httpx.Client) -> None:
        """Verify default namespace is listed at start."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool(
            mcp_client,
            "mnemosyne_list_namespaces",
            {},
            request_id=10,
            session_id=session_id,
        )
        assert "namespaces" in result
        names = {ns["name"] for ns in result["namespaces"]}
        assert "default" in names, "Default namespace should always be listed"

    def test_lists_new_namespace(self, mcp_client: httpx.Client) -> None:
        """After using a new namespace, verify it appears in list_namespaces."""
        _, session_id = mcp_init(mcp_client)

        new_ns = "e2e-list-new-ns"

        # Use the new namespace
        mcp_call_tool(
            mcp_client,
            "mnemosyne_remember",
            {"content": "activating namespace", "namespace": new_ns},
            request_id=20,
            session_id=session_id,
        )

        # Verify it appears
        result = mcp_call_tool(
            mcp_client,
            "mnemosyne_list_namespaces",
            {},
            request_id=21,
            session_id=session_id,
        )
        names = {ns["name"] for ns in result["namespaces"]}
        assert new_ns in names, f"Namespace {new_ns} should appear after first use"

        # Verify each entry has required fields
        for ns in result["namespaces"]:
            assert "name" in ns
            assert "bank" in ns
            assert "status" in ns
            assert "memory_count" in ns
