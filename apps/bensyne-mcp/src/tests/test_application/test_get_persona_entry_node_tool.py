"""Tool-registration + handler tests for getPersonaEntryNode (D2, RC2).

Covers:
- register_tools wires ``getPersonaEntryNode(memory_bank)`` -> handle_get_persona_entry_node
- the wire param name is ``memory_bank`` (snake_case) and is mandatory
- missing/empty memory_bank is a ValidationError
- the handler resolves the per-bank chunk repository from the DI container and
  returns the use case's node dict (memory_id, file_id, title, text, metadata, tags)

Use-case logic itself is covered in test_get_persona_entry_node_use_case.py;
here the use case is mocked so we test the wiring contract, not discovery.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.exceptions import ValidationError
from src.utils.result import Result

BANK = "persona_architect"


def _a_bundle(chunk_repository: MagicMock) -> MagicMock:
    bundle = MagicMock()
    bundle.file_repository = MagicMock()
    bundle.chunk_repository = chunk_repository
    return bundle


@pytest.fixture
def mnemosyne_instance() -> MagicMock:
    return MagicMock()


@pytest.fixture
def chunk_repository() -> MagicMock:
    return MagicMock()


@pytest.fixture
def use_case() -> MagicMock:
    uc = MagicMock()
    uc.execute.return_value = Result.ok(
        {
            "memory_id": "mem_entry",
            "file_id": "file_entry",
            "title": "Entry Node",
            "text": "Start read frame",
            "metadata": {"persona.node_id": "00-entry", "persona.entry": "true"},
            "tags": ["persona-node", "00-entry"],
        }
    )
    return uc


@pytest.fixture
def container(use_case: MagicMock, chunk_repository: MagicMock) -> MagicMock:
    c = MagicMock()
    c.file_metadata_bundle.return_value = _a_bundle(chunk_repository)
    c.get_persona_entry_node_use_case.return_value = use_case
    return c


@pytest.fixture
def router(mnemosyne_instance: MagicMock) -> MagicMock:
    r = MagicMock()
    r.get_instance = AsyncMock(return_value=mnemosyne_instance)
    r.get_bank_dir.return_value = "/tmp/data/banks/placeholder"
    return r


@pytest.fixture
def handler(router, container):
    from src.infrastructure.mcp.handlers import handle_get_persona_entry_node

    async def call(arguments: dict) -> dict:
        return await handle_get_persona_entry_node(router, arguments, container=container)

    return call


# ---------------------------------------------------------------------------
# Handler — happy path returns the use case's node dict
# ---------------------------------------------------------------------------


class TestGetPersonaEntryNodeHandler:
    async def test_returns_six_field_contract(self, handler) -> None:
        result = await handler({"memory_bank": BANK})
        assert result == {
            "memory_id": "mem_entry",
            "file_id": "file_entry",
            "title": "Entry Node",
            "text": "Start read frame",
            "metadata": {"persona.node_id": "00-entry", "persona.entry": "true"},
            "tags": ["persona-node", "00-entry"],
        }

    async def test_missing_memory_bank_raises_validation_error(
        self, router, container
    ) -> None:
        from src.infrastructure.mcp.handlers import handle_get_persona_entry_node

        with pytest.raises(ValidationError):
            await handle_get_persona_entry_node(router, {}, container=container)

    async def test_empty_memory_bank_raises_validation_error(
        self, router, container
    ) -> None:
        from src.infrastructure.mcp.handlers import handle_get_persona_entry_node

        with pytest.raises(ValidationError):
            await handle_get_persona_entry_node(
                router, {"memory_bank": ""}, container=container
            )

    async def test_builds_use_case_with_chunk_repo_from_container(
        self, router, container, use_case, mnemosyne_instance
    ) -> None:
        """The handler threads router instance + container chunk repository into the use case."""
        from src.infrastructure.mcp.handlers import handle_get_persona_entry_node

        await handle_get_persona_entry_node(
            router, {"memory_bank": BANK}, container=container
        )

        router.get_instance.assert_awaited_once_with(BANK)
        container.get_persona_entry_node_use_case.assert_called_once()
        kwargs = container.get_persona_entry_node_use_case.call_args.kwargs
        # Content fetcher is the mnemosyne client's .get (file layer is a
        # projection of memory); the entry flag + content-link repos come from
        # the resolved per-bank bundle.
        assert kwargs["mnemosyne_client"] is mnemosyne_instance.get
        bundle = container.file_metadata_bundle.return_value
        assert kwargs["file_repository"] is bundle.file_repository
        assert kwargs["file_chunk_repository"] is bundle.chunk_repository
        use_case.execute.assert_called_once_with({"memory_bank": BANK})


# ---------------------------------------------------------------------------
# MCP registration — snake_case param, wired handler
# ---------------------------------------------------------------------------


class TestGetPersonaEntryNodeRegistration:
    def _capture_tool_fn(self, mock_mcp: MagicMock, tool_name: str):
        for i, call in enumerate(mock_mcp.tool.call_args_list):
            if call.kwargs.get("name") == tool_name:
                return mock_mcp.tool.return_value.call_args_list[i].args[0]
        raise AssertionError(f"tool {tool_name} not registered")

    def test_registers_tool_with_memory_bank_param_and_calls_handler(self) -> None:
        from src.app import register_tools

        mock_mcp = MagicMock()
        mock_router = MagicMock()
        mock_service = MagicMock()
        mock_container = MagicMock()
        expected = {
            "memory_id": "mem_entry",
            "file_id": "file_entry",
            "title": "Entry Node",
            "text": "Start read frame",
            "metadata": {"persona.node_id": "00-entry"},
            "tags": ["persona-node", "00-entry"],
        }

        with patch(
            "src.infrastructure.mcp.handlers.handle_get_persona_entry_node",
            new=AsyncMock(return_value=expected),
        ) as mock_handle:
            register_tools(mock_mcp, mock_router, mock_service, mock_container)
            tool_fn = self._capture_tool_fn(mock_mcp, "getPersonaEntryNode")

            import inspect

            params = inspect.signature(tool_fn).parameters
            # memory_bank is the only (mandatory) wire parameter.
            assert list(params.keys()) == ["memory_bank"]

            result = asyncio.run(tool_fn(BANK))

        assert result == expected
        mock_handle.assert_awaited_once_with(
            mock_router, {"memory_bank": BANK}, mock_container
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
