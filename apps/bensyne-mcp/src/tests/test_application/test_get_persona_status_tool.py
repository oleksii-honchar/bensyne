"""Tool-registration + handler tests for getPersonaStatus (Task 4 / spec §4.4).

Covers:
- register_tools wires ``getPersonaStatus(memory_bank)`` -> handle_get_persona_status
- the wire param name is ``memory_bank`` (snake_case) and is mandatory
- missing/empty memory_bank is a ValidationError
- the handler resolves the per-bank chunk repository from the DI container,
  reads the configurable threshold, and returns the use case's count dict
- threshold defaults to 10 and is overridable via the environment

Use-case logic itself is covered in test_get_persona_status_use_case.py; here
the use case is mocked so we test the wiring contract, not the counting.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.exceptions import ValidationError
from src.utils.result import Result

BANK = "agent-persona_architect"


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
            "total": 42,
            "node_memories": 31,
            "occasional_memories": 11,
            "expired_occasional_memories": 2,
            "materialization_due": True,
        }
    )
    return uc


@pytest.fixture
def container(use_case: MagicMock, chunk_repository: MagicMock) -> MagicMock:
    c = MagicMock()
    c.file_metadata_bundle.return_value = _a_bundle(chunk_repository)
    c.get_persona_status_use_case.return_value = use_case
    return c


@pytest.fixture
def router(mnemosyne_instance: MagicMock) -> MagicMock:
    r = MagicMock()
    r.get_instance = AsyncMock(return_value=mnemosyne_instance)
    r.get_bank_dir.return_value = "/tmp/data/banks/placeholder"
    return r


@pytest.fixture
def handler(router, container):
    from src.infrastructure.mcp.handlers import handle_get_persona_status

    async def call(arguments: dict) -> dict:
        return await handle_get_persona_status(router, arguments, container=container)

    return call


# ---------------------------------------------------------------------------
# Handler — happy path returns the use case's count dict
# ---------------------------------------------------------------------------


class TestGetPersonaStatusHandler:
    async def test_returns_five_field_contract(self, handler) -> None:
        result = await handler({"memory_bank": BANK})
        assert result == {
            "total": 42,
            "node_memories": 31,
            "occasional_memories": 11,
            "expired_occasional_memories": 2,
            "materialization_due": True,
        }

    async def test_missing_memory_bank_raises_validation_error(
        self, router, container
    ) -> None:
        from src.infrastructure.mcp.handlers import handle_get_persona_status

        with pytest.raises(ValidationError):
            await handle_get_persona_status(router, {}, container=container)

    async def test_empty_memory_bank_raises_validation_error(
        self, router, container
    ) -> None:
        from src.infrastructure.mcp.handlers import handle_get_persona_status

        with pytest.raises(ValidationError):
            await handle_get_persona_status(router, {"memory_bank": ""}, container=container)

    async def test_builds_use_case_with_chunk_repo_from_container(
        self, router, container, use_case, mnemosyne_instance
    ) -> None:
        """The handler threads router instance + container chunk repository into the use case."""
        from src.infrastructure.mcp.handlers import handle_get_persona_status

        await handle_get_persona_status(
            router, {"memory_bank": BANK}, container=container
        )

        router.get_instance.assert_awaited_once_with(BANK)
        container.get_persona_status_use_case.assert_called_once()
        kwargs = container.get_persona_status_use_case.call_args.kwargs
        assert kwargs["mnemosyne_client"] is mnemosyne_instance
        # chunk repository is the one from the resolved per-bank bundle
        bundle = container.file_metadata_bundle.return_value
        assert kwargs["file_chunk_repository"] is bundle.chunk_repository
        use_case.execute.assert_called_once_with({"memory_bank": BANK})


# ---------------------------------------------------------------------------
# Threshold — configurable, default 10, env-overridable
# ---------------------------------------------------------------------------


class TestGetPersonaStatusThreshold:
    async def test_default_threshold_is_10(
        self, router, container, use_case, monkeypatch
    ) -> None:
        from src.infrastructure.mcp.handlers import handle_get_persona_status

        monkeypatch.delenv("BENSYNE_PERSONA_MATERIALIZATION_THRESHOLD", raising=False)
        await handle_get_persona_status(router, {"memory_bank": BANK}, container=container)

        kwargs = container.get_persona_status_use_case.call_args.kwargs
        assert kwargs["materialization_threshold"] == 10

    async def test_threshold_overridable_via_env(
        self, router, container, use_case, monkeypatch
    ) -> None:
        from src.infrastructure.mcp.handlers import handle_get_persona_status

        monkeypatch.setenv("BENSYNE_PERSONA_MATERIALIZATION_THRESHOLD", "25")
        await handle_get_persona_status(router, {"memory_bank": BANK}, container=container)

        kwargs = container.get_persona_status_use_case.call_args.kwargs
        assert kwargs["materialization_threshold"] == 25

    async def test_invalid_env_threshold_falls_back_to_default(
        self, router, container, use_case, monkeypatch
    ) -> None:
        from src.infrastructure.mcp.handlers import handle_get_persona_status

        monkeypatch.setenv("BENSYNE_PERSONA_MATERIALIZATION_THRESHOLD", "not-a-number")
        await handle_get_persona_status(router, {"memory_bank": BANK}, container=container)

        kwargs = container.get_persona_status_use_case.call_args.kwargs
        assert kwargs["materialization_threshold"] == 10


# ---------------------------------------------------------------------------
# MCP registration — snake_case param, wired handler
# ---------------------------------------------------------------------------


class TestGetPersonaStatusRegistration:
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
        expected = {"total": 1, "node_memories": 1, "occasional_memories": 0,
                    "expired_occasional_memories": 0, "materialization_due": False}

        with patch(
            "src.infrastructure.mcp.handlers.handle_get_persona_status",
            new=AsyncMock(return_value=expected),
        ) as mock_handle:
            register_tools(mock_mcp, mock_router, mock_service, mock_container)
            tool_fn = self._capture_tool_fn(mock_mcp, "getPersonaStatus")

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
