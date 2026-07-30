"""E2E tests for namespace routing and data isolation.

Verifies multiple namespaces, data isolation between them, and default fallback.
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
                "clientInfo": {"name": "e2e-ns-test", "version": "1.0.0"},
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


class TestIsolatedNamespaces:
    """Memories stored in one namespace are not visible in another."""

    def test_isolated_namespaces(self, mcp_client: httpx.Client) -> None:
        """Store in namespace A, verify not found in namespace B."""
        _, session_id = mcp_init(mcp_client)

        # Store unique content in namespace A
        mcp_call_tool(
            mcp_client,
            "mnemosyne_remember",
            {"content": "secret of namespace A", "namespace": "e2e-ns-a"},
            request_id=10,
            session_id=session_id,
        )

        # Store unique content in namespace B
        mcp_call_tool(
            mcp_client,
            "mnemosyne_remember",
            {"content": "secret of namespace B", "namespace": "e2e-ns-b"},
            request_id=11,
            session_id=session_id,
        )

        # Recall from namespace A should NOT find namespace B's content
        recall_a = mcp_call_tool(
            mcp_client,
            "mnemosyne_recall",
            {"query": "secret of namespace B", "namespace": "e2e-ns-a"},
            request_id=12,
            session_id=session_id,
        )
        # Filter results for exact phrase match
        found = any("secret of namespace B" in r.get("content", "") for r in recall_a["results"])
        assert not found, "Namespace A should not see namespace B's memories"

        # Recall from namespace B should NOT find namespace A's content
        recall_b = mcp_call_tool(
            mcp_client,
            "mnemosyne_recall",
            {"query": "secret of namespace A", "namespace": "e2e-ns-b"},
            request_id=13,
            session_id=session_id,
        )
        found = any("secret of namespace A" in r.get("content", "") for r in recall_b["results"])
        assert not found, "Namespace B should not see namespace A's memories"


class TestDefaultFallback:
    """Requests without namespace fall back to 'default'."""

    def test_default_fallback(self, mcp_client: httpx.Client) -> None:
        """Store without namespace, find in default."""
        _, session_id = mcp_init(mcp_client)

        # Store without namespace — should go to default
        remember_result = mcp_call_tool(
            mcp_client,
            "mnemosyne_remember",
            {"content": "default namespace memory"},
            request_id=20,
            session_id=session_id,
        )
        assert remember_result["namespace"] == "default"
        memory_id = remember_result["memory_id"]

        # Recall without namespace — should find in default
        recall_result = mcp_call_tool(
            mcp_client,
            "mnemosyne_recall",
            {"query": "default namespace memory"},
            request_id=21,
            session_id=session_id,
        )
        assert recall_result["namespace"] == "default"
        matching = [r for r in recall_result["results"] if r.get("id") == memory_id]
        assert len(matching) == 1


class TestConcurrentNamespaces:
    """Multiple namespaces active simultaneously."""

    def test_concurrent_namespaces(self, mcp_client: httpx.Client) -> None:
        """Use multiple namespaces simultaneously, all return correct data."""
        _, session_id = mcp_init(mcp_client)

        namespaces = ["e2e-conc-1", "e2e-conc-2", "e2e-conc-3"]
        memory_ids: dict[str, str] = {}

        # Store in each namespace
        for i, ns in enumerate(namespaces, start=30):
            result = mcp_call_tool(
                mcp_client,
                "mnemosyne_remember",
                {"content": f"concurrent memory for {ns}", "namespace": ns},
                request_id=i,
                session_id=session_id,
            )
            assert result["namespace"] == ns
            memory_ids[ns] = result["memory_id"]

        # Recall from each namespace
        for i, ns in enumerate(namespaces, start=40):
            recall = mcp_call_tool(
                mcp_client,
                "mnemosyne_recall",
                {"query": f"concurrent memory for {ns}", "namespace": ns},
                request_id=i,
                session_id=session_id,
            )
            assert recall["namespace"] == ns
            matching = [r for r in recall["results"] if r.get("id") == memory_ids[ns]]
            assert len(matching) == 1, f"Expected memory in namespace {ns}"
