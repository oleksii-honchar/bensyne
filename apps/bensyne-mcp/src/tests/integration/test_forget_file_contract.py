"""Cross-layer contract verification for forgetFile (Task 3).

Exercises the REAL ForgetFileUseCase through the real MCP handler boundary
(register_tools -> handle_forget_file -> _raise_on_ko) and asserts the
MCP-level response shape:

- unknown file path -> {"status": "FILE_NOT_FOUND"} JSON tool result, NOT an
  error wrapper ("Error calling tool ..." absent, is_error False)
- already-deleted file -> {"status": "already_deleted"} (no contract regression)
- known file -> {"status": "forgotten"} (no contract regression)

Per-bank infrastructure (file_service, hash_index_service, mnemosyne client)
is stubbed; the use case, handler, and _raise_on_ko are real — this is the
app/integration boundary the plan targets.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from dependency_injector import providers

from src.domain.file_chunk_entity import ContentType, FileChunk
from src.domain.file_entity import File, FileStatus, SourceType
from src.utils.result import ErrorWithDetails, Result

NOW = datetime(2026, 1, 1, 0, 0, 0)
BANK = "vault"
UNKNOWN_PATH = "/tmp/notes/unknown.md"


def _a_file(
    id: str = "f1",
    path: str = UNKNOWN_PATH,
    status: FileStatus = FileStatus.INDEXED,
) -> File:
    return File(
        id=id,
        path=path,
        source_type=SourceType.VAULT,
        file_role=None,
        hash="a" * 64,
        file_type=None,
        size=None,
        language=None,
        aggregated_keywords=[],
        aggregated_tags=[],
        status=status,
        summary=None,
        total_chunks=0,
        average_importance=0.5,
        metadata={},
        created_at=NOW,
        updated_at=NOW,
    )


def _a_chunk(
    id: str = "c1",
    file_id: str = "f1",
    memory_id: str = "mem_1",
    chunk_index: int = 0,
) -> FileChunk:
    return FileChunk(
        id=id,
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=chunk_index,
        start_line=0,
        end_line=10,
        content_hash="abc",
        content_type=ContentType.TEXT,
        is_partial=False,
        section_header=None,
        parent_unit_ref=None,
        parent_unit_summary=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _build_server(container, router):
    """Build a real FastMCP server wired via register_tools (real handler path)."""
    from fastmcp import FastMCP

    from src.app import register_tools

    mcp = FastMCP(name="forget-file-contract-test")
    register_tools(mcp, router, MagicMock(), container)
    return mcp


@pytest.fixture
def router() -> MagicMock:
    router = MagicMock()
    router.get_instance = AsyncMock()
    return router


@pytest.fixture
def file_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def hash_index_service() -> MagicMock:
    return MagicMock()


@pytest.fixture
def container(file_service: MagicMock, hash_index_service: MagicMock):
    """TestContainer with the REAL forget_file_use_case factory.

    Only the per-bank file deps (file_metadata_bundle / file_service /
    hash_index_service) are stubbed; the use case, handler, and _raise_on_ko
    are real.
    """
    from src.infrastructure.di import TestContainer

    container = TestContainer()
    with container.override_providers(
        file_metadata_bundle=providers.Factory(lambda **kwargs: MagicMock()),
        file_service=providers.Factory(lambda **kwargs: file_service),
        hash_index_service=providers.Factory(lambda **kwargs: hash_index_service),
    ):
        yield container


async def _call_forget_file(container, router, file_path: str = UNKNOWN_PATH):
    mcp = _build_server(container, router)
    return await mcp.call_tool(
        "forgetFile",
        {"memory_bank": BANK, "file_path": file_path},
    )


class TestForgetFileUnknownPath:
    """Unknown file path -> JSON status FILE_NOT_FOUND, NOT an error wrapper."""

    async def test_unknown_path_returns_file_not_found_status(
        self, container, router, file_service: MagicMock
    ) -> None:
        """The MCP response is a JSON status, not a raised ValidationError."""
        file_service.get_file_by_path.return_value = Result.ko(
            [ErrorWithDetails("FILE_NOT_FOUND", {"path": UNKNOWN_PATH})]
        )

        result = await _call_forget_file(container, router)

        assert result.is_error is False
        assert result.structured_content == {"status": "FILE_NOT_FOUND"}
        # Not an error wrapper: FastMCP's "Error calling tool ..." text is absent.
        assert "Error calling tool" not in result.content[0].text

    async def test_unknown_path_does_not_touch_mnemosyne(
        self, container, router, file_service: MagicMock
    ) -> None:
        """A missing row is a no-op: no mnemosyne forget is attempted."""
        file_service.get_file_by_path.return_value = Result.ko(
            [ErrorWithDetails("FILE_NOT_FOUND", {"path": UNKNOWN_PATH})]
        )

        await _call_forget_file(container, router)

        mnemosyne = router.get_instance.return_value
        mnemosyne.forget.assert_not_called()


class TestForgetFileNoContractRegression:
    """forgotten/already_deleted still return JSON statuses at the boundary."""

    async def test_already_deleted_returns_status(
        self, container, router, file_service: MagicMock
    ) -> None:
        """A DELETED tombstone stays an idempotent already_deleted no-op."""
        file_service.get_file_by_path.return_value = Result.ok(
            _a_file(status=FileStatus.DELETED)
        )

        result = await _call_forget_file(container, router)

        assert result.is_error is False
        assert result.structured_content == {"status": "already_deleted"}

    async def test_forgotten_returns_status(
        self, container, router, file_service: MagicMock
    ) -> None:
        """A known file with unshared memories is forgotten with status forgotten."""
        file = _a_file(id="f1")
        chunk = _a_chunk(id="c1", file_id="f1", memory_id="mem_1")
        file_service.get_file_by_path.return_value = Result.ok(file)
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk])
        file_service.get_chunks_by_memory_id.return_value = Result.ok([chunk])
        file_service.delete_file.return_value = Result.ok(file)
        # Plain MagicMock: the use case calls forget() synchronously (not awaited).
        router.get_instance.return_value.forget = MagicMock(return_value=Result.ok(True))

        result = await _call_forget_file(container, router)

        assert result.is_error is False
        assert result.structured_content["status"] == "forgotten"