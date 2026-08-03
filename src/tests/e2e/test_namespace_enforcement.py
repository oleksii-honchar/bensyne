"""E2E tests for namespace enforcement.

Verifies that all memory tools reject calls without namespace parameter,
and accept calls with namespace parameter.
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
                "clientInfo": {"name": "e2e-ns-enforcement-test", "version": "1.0.0"},
            },
        },
    )
    resp.raise_for_status()
    session_id = resp.headers.get("mcp-session-id", "")
    return _parse_sse_json(resp.text), session_id


def mcp_call_tool_raw(client: httpx.Client, tool_name: str, arguments: dict, request_id: int, session_id: str) -> dict:
    """Call an MCP tool and return the full JSON-RPC result (including errors).

    Does NOT raise on MCP errors — returns the raw result dict so we can assert
    on error codes and messages.
    """
    headers = {"Mcp-Session-Id": session_id} if session_id else {}
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
        headers=headers,
    )
    resp.raise_for_status()
    return _parse_sse_json(resp.text)


def mcp_call_tool(client: httpx.Client, tool_name: str, arguments: dict, request_id: int, session_id: str) -> dict:
    """Call an MCP tool and return the parsed result (raises on MCP error)."""
    result = mcp_call_tool_raw(client, tool_name, arguments, request_id, session_id)
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


def assert_mcp_error(result: dict, tool_name: str, expected_message_substring: str | None = None) -> None:
    """Assert that an MCP call returned an error (JSON-RPC error, tool-level error, or isError flag).

    FastMCP/Pydantic validation errors are returned as:
    {result: {content: [{text: "...validation error...", type: "text"}], isError: true}}
    """
    # Check for JSON-RPC level error
    if "error" in result:
        error = result["error"]
        message = error.get("message", "")
        if expected_message_substring:
            assert expected_message_substring.lower() in message.lower(), (
                f"Expected '{expected_message_substring}' in error message for {tool_name}, "
                f"got: {message}"
            )
        return

    tool_result = result.get("result", {})

    # Check for isError flag (FastMCP validation errors)
    if tool_result.get("isError"):
        content_list = tool_result.get("content", [])
        if content_list:
            text = content_list[0].get("text", "")
            if expected_message_substring:
                assert expected_message_substring.lower() in text.lower(), (
                    f"Expected '{expected_message_substring}' in error text for {tool_name}, "
                    f"got: {text}"
                )
            return

    # Check for tool-level error in result
    if "error" in tool_result:
        message = tool_result["error"]
        if expected_message_substring:
            assert expected_message_substring.lower() in str(message).lower(), (
                f"Expected '{expected_message_substring}' in error message for {tool_name}, "
                f"got: {message}"
            )
        return

    pytest.fail(f"Expected error for {tool_name}, but got success: {result}")


# ---------------------------------------------------------------------------
# Tests — namespace NOT provided
# ---------------------------------------------------------------------------


class TestRememberWithoutNamespace:
    """mnemosyne_remember requires namespace parameter."""

    def test_remember_without_namespace_raises_error(self, mcp_client: httpx.Client) -> None:
        """Calling remember without namespace returns error."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool_raw(
            mcp_client,
            "mnemosyne_remember",
            {"content": "test memory without namespace"},
            request_id=10,
            session_id=session_id,
        )
        assert_mcp_error(result, "mnemosyne_remember", "namespace")


class TestRecallWithoutNamespace:
    """mnemosyne_recall requires namespace parameter."""

    def test_recall_without_namespace_raises_error(self, mcp_client: httpx.Client) -> None:
        """Calling recall without namespace returns error."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool_raw(
            mcp_client,
            "mnemosyne_recall",
            {"query": "test query without namespace"},
            request_id=20,
            session_id=session_id,
        )
        assert_mcp_error(result, "mnemosyne_recall", "namespace")


class TestForgetWithoutNamespace:
    """mnemosyne_forget requires namespace parameter."""

    def test_forget_without_namespace_raises_error(self, mcp_client: httpx.Client) -> None:
        """Calling forget without namespace returns error."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool_raw(
            mcp_client,
            "mnemosyne_forget",
            {"memory_id": "fake-memory-id"},
            request_id=30,
            session_id=session_id,
        )
        assert_mcp_error(result, "mnemosyne_forget", "namespace")


class TestUpdateWithoutNamespace:
    """mnemosyne_update requires namespace parameter."""

    def test_update_without_namespace_raises_error(self, mcp_client: httpx.Client) -> None:
        """Calling update without namespace returns error."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool_raw(
            mcp_client,
            "mnemosyne_update",
            {"memory_id": "fake-memory-id", "content": "updated"},
            request_id=40,
            session_id=session_id,
        )
        assert_mcp_error(result, "mnemosyne_update", "namespace")


class TestSleepWithoutNamespace:
    """mnemosyne_sleep requires namespace parameter."""

    def test_sleep_without_namespace_raises_error(self, mcp_client: httpx.Client) -> None:
        """Calling sleep without namespace returns error."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool_raw(
            mcp_client,
            "mnemosyne_sleep",
            {},
            request_id=50,
            session_id=session_id,
        )
        assert_mcp_error(result, "mnemosyne_sleep", "namespace")


class TestStatsWithoutNamespace:
    """mnemosyne_stats requires namespace parameter."""

    def test_stats_without_namespace_raises_error(self, mcp_client: httpx.Client) -> None:
        """Calling stats without namespace returns error."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool_raw(
            mcp_client,
            "mnemosyne_stats",
            {},
            request_id=60,
            session_id=session_id,
        )
        assert_mcp_error(result, "mnemosyne_stats", "namespace")


# ---------------------------------------------------------------------------
# Tests — namespace IS provided (should succeed)
# ---------------------------------------------------------------------------


class TestRememberWithNamespace:
    """mnemosyne_remember succeeds with namespace parameter."""

    def test_remember_with_namespace_succeeds(self, mcp_client: httpx.Client) -> None:
        """Calling remember with namespace stores memory."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool(
            mcp_client,
            "mnemosyne_remember",
            {"content": "test memory with namespace", "namespace": "e2e-ns-enforcement"},
            request_id=70,
            session_id=session_id,
        )
        assert result["status"] == "stored"
        assert result["namespace"] == "e2e-ns-enforcement"
        assert "memory_id" in result


class TestRecallWithNamespace:
    """mnemosyne_recall succeeds with namespace parameter."""

    def test_recall_with_namespace_succeeds(self, mcp_client: httpx.Client) -> None:
        """Calling recall with namespace returns results."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool(
            mcp_client,
            "mnemosyne_recall",
            {"query": "test query", "namespace": "e2e-ns-enforcement"},
            request_id=80,
            session_id=session_id,
        )
        assert result["namespace"] == "e2e-ns-enforcement"
        assert "results" in result


class TestForgetWithNamespace:
    """mnemosyne_forget succeeds with namespace parameter."""

    def test_forget_with_namespace_succeeds(self, mcp_client: httpx.Client) -> None:
        """Calling forget with namespace deletes memory."""
        _, session_id = mcp_init(mcp_client)
        ns = "e2e-ns-enforcement-forget"

        # Store first
        remember_result = mcp_call_tool(
            mcp_client,
            "mnemosyne_remember",
            {"content": "to forget", "namespace": ns},
            request_id=90,
            session_id=session_id,
        )
        memory_id = remember_result["memory_id"]

        # Then forget
        result = mcp_call_tool(
            mcp_client,
            "mnemosyne_forget",
            {"memory_id": memory_id, "namespace": ns},
            request_id=91,
            session_id=session_id,
        )
        assert result["status"] == "deleted"
        assert result["namespace"] == ns


class TestUpdateWithNamespace:
    """mnemosyne_update succeeds with namespace parameter."""

    def test_update_with_namespace_succeeds(self, mcp_client: httpx.Client) -> None:
        """Calling update with namespace updates memory."""
        _, session_id = mcp_init(mcp_client)
        ns = "e2e-ns-enforcement-update"

        # Store first
        remember_result = mcp_call_tool(
            mcp_client,
            "mnemosyne_remember",
            {"content": "original", "namespace": ns},
            request_id=100,
            session_id=session_id,
        )
        memory_id = remember_result["memory_id"]

        # Then update
        result = mcp_call_tool(
            mcp_client,
            "mnemosyne_update",
            {"memory_id": memory_id, "content": "updated", "namespace": ns},
            request_id=101,
            session_id=session_id,
        )
        assert result["status"] == "updated"
        assert result["namespace"] == ns


class TestSleepWithNamespace:
    """mnemosyne_sleep succeeds with namespace parameter."""

    def test_sleep_with_namespace_succeeds(self, mcp_client: httpx.Client) -> None:
        """Calling sleep with namespace runs consolidation."""
        _, session_id = mcp_init(mcp_client)
        ns = "e2e-ns-enforcement-sleep"

        result = mcp_call_tool(
            mcp_client,
            "mnemosyne_sleep",
            {"namespace": ns},
            request_id=110,
            session_id=session_id,
        )
        assert result["namespace"] == ns
        assert isinstance(result, dict)


class TestStatsWithNamespace:
    """mnemosyne_stats succeeds with namespace parameter."""

    def test_stats_with_namespace_succeeds(self, mcp_client: httpx.Client) -> None:
        """Calling stats with namespace returns statistics."""
        _, session_id = mcp_init(mcp_client)
        ns = "e2e-ns-enforcement-stats"

        result = mcp_call_tool(
            mcp_client,
            "mnemosyne_stats",
            {"namespace": ns},
            request_id=120,
            session_id=session_id,
        )
        assert result["namespace"] == ns
        assert "stats" in result
        assert isinstance(result["stats"], dict)
