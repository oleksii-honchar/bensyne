"""E2E tests for memory bank enforcement.

Verifies that all memory tools reject calls without memory_bank parameter,
and accept calls with memory_bank parameter.
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
                "clientInfo": {"name": "e2e-bank-enforcement-test", "version": "1.0.0"},
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
# Tests — memory_bank NOT provided
# ---------------------------------------------------------------------------


class TestRememberWithoutMemoryBank:
    """memory_remember requires memory_bank parameter."""

    def test_remember_without_memory_bank_raises_error(self, mcp_client: httpx.Client) -> None:
        """Calling remember without memory_bank returns error."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool_raw(
            mcp_client,
            "memory_remember",
            {"content": "test memory without memory bank"},
            request_id=10,
            session_id=session_id,
        )
        assert_mcp_error(result, "memory_remember", "memory_bank")


class TestRecallWithoutMemoryBank:
    """memory_recall requires memory_bank parameter."""

    def test_recall_without_memory_bank_raises_error(self, mcp_client: httpx.Client) -> None:
        """Calling recall without memory_bank returns error."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool_raw(
            mcp_client,
            "memory_recall",
            {"query": "test query without memory bank"},
            request_id=20,
            session_id=session_id,
        )
        assert_mcp_error(result, "memory_recall", "memory_bank")


class TestForgetWithoutMemoryBank:
    """memory_forget requires memory_bank parameter."""

    def test_forget_without_memory_bank_raises_error(self, mcp_client: httpx.Client) -> None:
        """Calling forget without memory_bank returns error."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool_raw(
            mcp_client,
            "memory_forget",
            {"memory_id": "fake-memory-id"},
            request_id=30,
            session_id=session_id,
        )
        assert_mcp_error(result, "memory_forget", "memory_bank")


class TestUpdateWithoutMemoryBank:
    """memory_update requires memory_bank parameter."""

    def test_update_without_memory_bank_raises_error(self, mcp_client: httpx.Client) -> None:
        """Calling update without memory_bank returns error."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool_raw(
            mcp_client,
            "memory_update",
            {"memory_id": "fake-memory-id", "content": "updated"},
            request_id=40,
            session_id=session_id,
        )
        assert_mcp_error(result, "memory_update", "memory_bank")


class TestSleepWithoutMemoryBank:
    """memory_sleep requires memory_bank parameter."""

    def test_sleep_without_memory_bank_raises_error(self, mcp_client: httpx.Client) -> None:
        """Calling sleep without memory_bank returns error."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool_raw(
            mcp_client,
            "memory_sleep",
            {},
            request_id=50,
            session_id=session_id,
        )
        assert_mcp_error(result, "memory_sleep", "memory_bank")


class TestStatsWithoutMemoryBank:
    """memory_stats requires memory_bank parameter."""

    def test_stats_without_memory_bank_raises_error(self, mcp_client: httpx.Client) -> None:
        """Calling stats without memory_bank returns error."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool_raw(
            mcp_client,
            "memory_stats",
            {},
            request_id=60,
            session_id=session_id,
        )
        assert_mcp_error(result, "memory_stats", "memory_bank")


# ---------------------------------------------------------------------------
# Tests — memory_bank IS provided (should succeed)
# ---------------------------------------------------------------------------


class TestRememberWithMemoryBank:
    """memory_remember succeeds with memory_bank parameter."""

    def test_remember_with_memory_bank_succeeds(self, mcp_client: httpx.Client) -> None:
        """Calling remember with memory_bank stores memory."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool(
            mcp_client,
            "memory_remember",
            {"content": "test memory with memory bank", "memory_bank": "e2e-bank-enforcement"},
            request_id=70,
            session_id=session_id,
        )
        assert result["status"] == "stored"
        assert result["memory_bank"] == "e2e-bank-enforcement"
        assert "memory_id" in result


class TestRecallWithMemoryBank:
    """memory_recall succeeds with memory_bank parameter."""

    def test_recall_with_memory_bank_succeeds(self, mcp_client: httpx.Client) -> None:
        """Calling recall with memory_bank returns results."""
        _, session_id = mcp_init(mcp_client)

        result = mcp_call_tool(
            mcp_client,
            "memory_recall",
            {"query": "test query", "memory_bank": "e2e-bank-enforcement"},
            request_id=80,
            session_id=session_id,
        )
        assert result["memory_bank"] == "e2e-bank-enforcement"
        assert "results" in result


class TestForgetWithMemoryBank:
    """memory_forget succeeds with memory_bank parameter."""

    def test_forget_with_memory_bank_succeeds(self, mcp_client: httpx.Client) -> None:
        """Calling forget with memory_bank deletes memory."""
        _, session_id = mcp_init(mcp_client)
        bank = "e2e-bank-enforcement-forget"

        # Store first
        remember_result = mcp_call_tool(
            mcp_client,
            "memory_remember",
            {"content": "to forget", "memory_bank": bank},
            request_id=90,
            session_id=session_id,
        )
        memory_id = remember_result["memory_id"]

        # Then forget
        result = mcp_call_tool(
            mcp_client,
            "memory_forget",
            {"memory_id": memory_id, "memory_bank": bank},
            request_id=91,
            session_id=session_id,
        )
        assert result["status"] == "deleted"
        assert result["memory_bank"] == bank


class TestUpdateWithMemoryBank:
    """memory_update succeeds with memory_bank parameter."""

    def test_update_with_memory_bank_succeeds(self, mcp_client: httpx.Client) -> None:
        """Calling update with memory_bank updates memory."""
        _, session_id = mcp_init(mcp_client)
        bank = "e2e-bank-enforcement-update"

        # Store first
        remember_result = mcp_call_tool(
            mcp_client,
            "memory_remember",
            {"content": "original", "memory_bank": bank},
            request_id=100,
            session_id=session_id,
        )
        memory_id = remember_result["memory_id"]

        # Then update
        result = mcp_call_tool(
            mcp_client,
            "memory_update",
            {"memory_id": memory_id, "content": "updated", "memory_bank": bank},
            request_id=101,
            session_id=session_id,
        )
        assert result["status"] == "updated"
        assert result["memory_bank"] == bank


class TestSleepWithMemoryBank:
    """memory_sleep succeeds with memory_bank parameter."""

    def test_sleep_with_memory_bank_succeeds(self, mcp_client: httpx.Client) -> None:
        """Calling sleep with memory_bank runs consolidation."""
        _, session_id = mcp_init(mcp_client)
        bank = "e2e-bank-enforcement-sleep"

        result = mcp_call_tool(
            mcp_client,
            "memory_sleep",
            {"memory_bank": bank},
            request_id=110,
            session_id=session_id,
        )
        assert result["memory_bank"] == bank
        assert isinstance(result, dict)


class TestStatsWithMemoryBank:
    """memory_stats succeeds with memory_bank parameter."""

    def test_stats_with_memory_bank_succeeds(self, mcp_client: httpx.Client) -> None:
        """Calling stats with memory_bank returns statistics."""
        _, session_id = mcp_init(mcp_client)
        bank = "e2e-bank-enforcement-stats"

        result = mcp_call_tool(
            mcp_client,
            "memory_stats",
            {"memory_bank": bank},
            request_id=120,
            session_id=session_id,
        )
        assert result["memory_bank"] == bank
        assert "stats" in result
        assert isinstance(result["stats"], dict)
