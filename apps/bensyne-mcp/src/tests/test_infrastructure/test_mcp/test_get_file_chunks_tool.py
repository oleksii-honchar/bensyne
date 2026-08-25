"""MCP tool tests for getFileChunks — read-only stored-chunk-set existence check.

Covers (Task 1 / spec §4.5):
- unknown file -> FILE_NOT_FOUND with empty chunks and derived file_id
- known file -> status "present" plus file_hash/total_chunks/source_type and
  one entry per stored chunk (chunk_index/content_hash/memory_id/memory_status)
- memory_status present when mnemosyne.get returns a dict, missing when None
- pure read-only: no mnemosyne save/embed, no file-layer writes
- snake_case wire contract
- MCP registration with snake_case params file_path + memory_bank
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.application.services.file_service import derive_file_id
from src.domain.exceptions import ValidationError
from src.domain.file_chunk_entity import ContentType, FileChunk
from src.domain.file_entity import File, FileStatus, SourceType
from src.utils.result import Result

NOW = datetime(2026, 1, 1, 0, 0, 0)

BANK = "vault"
PATH = "/tmp/notes/idea.md"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _a_file(
    id: str,
    path: str = PATH,
    source_type: SourceType = SourceType.VAULT,
    hash: str | None = "f" * 64,
    total_chunks: int = 2,
) -> File:
    return File(
        id=id,
        path=path,
        source_type=source_type,
        file_role=None,
        hash=hash,
        file_type=None,
        size=None,
        language=None,
        aggregated_keywords=[],
        aggregated_tags=[],
        status=FileStatus.INDEXED,
        summary=None,
        total_chunks=total_chunks,
        average_importance=0.5,
        metadata={},
        created_at=NOW,
        updated_at=NOW,
    )


def _a_chunk(
    id: str,
    file_id: str,
    memory_id: str,
    chunk_index: int,
    content_hash: str | None = "c" * 64,
) -> FileChunk:
    return FileChunk(
        id=id,
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=chunk_index,
        start_line=1,
        end_line=10,
        content_hash=content_hash,
        content_type=ContentType.TEXT,
        is_partial=False,
        section_header=None,
        parent_unit_ref=None,
        parent_unit_summary=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _a_bundle(file_repository: MagicMock, chunk_repository: MagicMock) -> MagicMock:
    bundle = MagicMock()
    bundle.file_repository = file_repository
    bundle.chunk_repository = chunk_repository
    return bundle


@pytest.fixture
def mnemosyne_instance() -> MagicMock:
    return MagicMock()


@pytest.fixture
def file_repository() -> MagicMock:
    return MagicMock()


@pytest.fixture
def chunk_repository() -> MagicMock:
    return MagicMock()


@pytest.fixture
def container(file_repository: MagicMock, chunk_repository: MagicMock) -> MagicMock:
    container = MagicMock()
    container.file_metadata_bundle.return_value = _a_bundle(file_repository, chunk_repository)
    return container


@pytest.fixture
def router(mnemosyne_instance: MagicMock) -> MagicMock:
    router = MagicMock()
    router.get_instance = AsyncMock(return_value=mnemosyne_instance)
    return router


@pytest.fixture
def handler_ctx(router, container):
    """Bundled handler dependencies for the default arguments."""

    from src.infrastructure.mcp.handlers import handle_get_file_chunks

    async def call(arguments: dict) -> dict:
        return await handle_get_file_chunks(router, arguments, container=container)

    return call


# ---------------------------------------------------------------------------
# Handler — FILE_NOT_FOUND
# ---------------------------------------------------------------------------


class TestGetFileChunksFileNotFound:
    async def test_unknown_file_returns_file_not_found_with_empty_chunks(
        self,
        handler_ctx,
        router,
        container,
        file_repository: MagicMock,
        chunk_repository: MagicMock,
        mnemosyne_instance: MagicMock,
    ) -> None:
        """No files row -> status FILE_NOT_FOUND, derived file_id, empty chunks."""
        file_repository.get_file_by_id.return_value = Result.ok(None)

        result = await handler_ctx({"file_path": PATH, "memory_bank": BANK})

        expected_file_id = derive_file_id(BANK, PATH)
        assert result["status"] == "FILE_NOT_FOUND"
        assert result["file_id"] == expected_file_id
        assert result["chunks"] == []

        # Chunk reads and mnemosyne point reads must not run for an unknown file.
        chunk_repository.get_chunks_by_file_id.assert_not_called()
        mnemosyne_instance.get.assert_not_called()

    async def test_looks_up_derived_file_id(
        self,
        handler_ctx,
        router,
        container,
        file_repository: MagicMock,
        mnemosyne_instance: MagicMock,
    ) -> None:
        """The handler derives file_{sha256("bank:path")[:32]} and queries it."""
        file_repository.get_file_by_id.return_value = Result.ok(None)

        await handler_ctx({"file_path": PATH, "memory_bank": BANK})

        file_repository.get_file_by_id.assert_called_once_with(derive_file_id(BANK, PATH))

    async def test_requires_file_path(self, router, container) -> None:
        """Missing file_path is a ValidationError, not a silent success."""
        from src.infrastructure.mcp.handlers import handle_get_file_chunks

        with pytest.raises(ValidationError):
            await handle_get_file_chunks(router, {"memory_bank": BANK}, container=container)


# ---------------------------------------------------------------------------
# Handler — present file / contract shape
# ---------------------------------------------------------------------------


class TestGetFileChunksPresent:
    async def test_returns_snake_case_contract_for_known_file(
        self,
        handler_ctx,
        router,
        container,
        file_repository: MagicMock,
        chunk_repository: MagicMock,
        mnemosyne_instance: MagicMock,
    ) -> None:
        """Known file -> status present + file_id/file_hash/total_chunks/source_type
        and one snake_case entry per stored chunk."""
        file_id = derive_file_id(BANK, PATH)
        file_hash = "f" * 64
        file = _a_file(id=file_id, hash=file_hash, total_chunks=2)
        chunks = [
            _a_chunk(id="c1", file_id=file_id, memory_id="mem_1", chunk_index=0, content_hash="h1"),
            _a_chunk(id="c2", file_id=file_id, memory_id="mem_2", chunk_index=1, content_hash="h2"),
        ]
        file_repository.get_file_by_id.return_value = Result.ok(file)
        chunk_repository.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_instance.get.return_value = {"id": "mem_1"}

        result = await handler_ctx({"file_path": PATH, "memory_bank": BANK})

        assert set(result.keys()) == {
            "status",
            "file_id",
            "file_hash",
            "total_chunks",
            "source_type",
            "chunks",
        }
        assert result["status"] == "present"
        assert result["file_id"] == file_id
        assert result["file_hash"] == file_hash
        assert result["total_chunks"] == 2
        assert result["source_type"] == "vault"

        assert len(result["chunks"]) == 2
        assert set(result["chunks"][0].keys()) == {
            "chunk_index",
            "content_hash",
            "memory_id",
            "memory_status",
        }
        assert result["chunks"][0] == {
            "chunk_index": 0,
            "content_hash": "h1",
            "memory_id": "mem_1",
            "memory_status": "present",
        }
        assert result["chunks"][1] == {
            "chunk_index": 1,
            "content_hash": "h2",
            "memory_id": "mem_2",
            "memory_status": "present",
        }

    async def test_known_file_with_no_chunks_returns_empty_chunks_list(
        self,
        handler_ctx,
        router,
        container,
        file_repository: MagicMock,
        chunk_repository: MagicMock,
        mnemosyne_instance: MagicMock,
    ) -> None:
        """A file row with zero chunk rows -> status present, chunks [].

        total_chunks reflects the stored File entity value; no mnemosyne reads run."""
        file_id = derive_file_id(BANK, PATH)
        file = _a_file(id=file_id, total_chunks=0)
        file_repository.get_file_by_id.return_value = Result.ok(file)
        chunk_repository.get_chunks_by_file_id.return_value = Result.ok([])

        result = await handler_ctx({"file_path": PATH, "memory_bank": BANK})

        assert result["status"] == "present"
        assert result["chunks"] == []
        assert result["total_chunks"] == 0
        mnemosyne_instance.get.assert_not_called()


# ---------------------------------------------------------------------------
# Handler — memory_status present/missing mix
# ---------------------------------------------------------------------------


class TestGetFileChunksMemoryStatus:
    async def test_memory_status_mix_present_and_missing(
        self,
        handler_ctx,
        router,
        container,
        file_repository: MagicMock,
        chunk_repository: MagicMock,
        mnemosyne_instance: MagicMock,
    ) -> None:
        """memory_status is present when mnemosyne.get returns a dict, missing when None."""
        file_id = derive_file_id(BANK, PATH)
        file = _a_file(id=file_id, total_chunks=3)
        chunks = [
            _a_chunk(id="c1", file_id=file_id, memory_id="mem_1", chunk_index=0),
            _a_chunk(id="c2", file_id=file_id, memory_id="mem_2", chunk_index=1),
            _a_chunk(id="c3", file_id=file_id, memory_id="mem_3", chunk_index=2),
        ]
        file_repository.get_file_by_id.return_value = Result.ok(file)
        chunk_repository.get_chunks_by_file_id.return_value = Result.ok(chunks)
        # mem_2 is missing (get -> None); the others are live.
        mnemosyne_instance.get.side_effect = [{"id": "mem_1"}, None, {"id": "mem_3"}]

        result = await handler_ctx({"file_path": PATH, "memory_bank": BANK})

        statuses = [c["memory_status"] for c in result["chunks"]]
        assert statuses == ["present", "missing", "present"]
        assert result["chunks"][1]["memory_id"] == "mem_2"

        # Exactly one cheap point read per chunk — no save/embed.
        assert mnemosyne_instance.get.call_count == 3


# ---------------------------------------------------------------------------
# Read-only guarantees — no saves, no embeddings, no file-layer writes
# ---------------------------------------------------------------------------


class TestGetFileChunksReadOnly:
    async def test_never_calls_mnemosyne_save_or_embedding(
        self,
        handler_ctx,
        router,
        container,
        file_repository: MagicMock,
        chunk_repository: MagicMock,
        mnemosyne_instance: MagicMock,
    ) -> None:
        """The tool must never save/embed: mnemosyne.save/remember are never invoked."""
        file_id = derive_file_id(BANK, PATH)
        file = _a_file(id=file_id)
        chunks = [_a_chunk(id="c1", file_id=file_id, memory_id="mem_1", chunk_index=0)]
        file_repository.get_file_by_id.return_value = Result.ok(file)
        chunk_repository.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_instance.get.return_value = {"id": "mem_1"}

        await handler_ctx({"file_path": PATH, "memory_bank": BANK})

        mnemosyne_instance.save.assert_not_called()
        mnemosyne_instance.remember.assert_not_called()
        mnemosyne_instance.forget.assert_not_called()

    async def test_never_writes_file_layer(
        self,
        handler_ctx,
        router,
        container,
        file_repository: MagicMock,
        chunk_repository: MagicMock,
        mnemosyne_instance: MagicMock,
    ) -> None:
        """The tool must never write file rows, chunk rows, or relations."""
        file_id = derive_file_id(BANK, PATH)
        file = _a_file(id=file_id)
        chunks = [_a_chunk(id="c1", file_id=file_id, memory_id="mem_1", chunk_index=0)]
        file_repository.get_file_by_id.return_value = Result.ok(file)
        chunk_repository.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne_instance.get.return_value = {"id": "mem_1"}

        await handler_ctx({"file_path": PATH, "memory_bank": BANK})

        file_repository.save_file.assert_not_called()
        chunk_repository.save_chunk.assert_not_called()


# ---------------------------------------------------------------------------
# MCP registration — snake_case params, wired handler
# ---------------------------------------------------------------------------


class TestGetFileChunksRegistration:
    def _capture_tool_fn(self, mock_mcp: MagicMock, tool_name: str):
        for i, call in enumerate(mock_mcp.tool.call_args_list):
            if call.kwargs.get("name") == tool_name:
                return mock_mcp.tool.return_value.call_args_list[i].args[0]
        raise AssertionError(f"tool {tool_name} not registered")

    def test_registers_tool_with_snake_case_params_and_calls_handler(self) -> None:
        """register_tools wires getFileChunks(file_path, memory_bank) -> handle_get_file_chunks."""
        from src.app import register_tools

        mock_mcp = MagicMock()
        mock_router = MagicMock()
        mock_service = MagicMock()
        mock_container = MagicMock()

        with patch(
            "src.infrastructure.mcp.handlers.handle_get_file_chunks",
            new=AsyncMock(return_value={"status": "present", "chunks": []}),
        ) as mock_handle:
            register_tools(mock_mcp, mock_router, mock_service, mock_container)
            tool_fn = self._capture_tool_fn(mock_mcp, "getFileChunks")

            # Snake_case parameter names are the wire contract.
            import inspect

            params = inspect.signature(tool_fn).parameters
            assert list(params.keys()) == ["file_path", "memory_bank"]

            result = asyncio.run(tool_fn(PATH, BANK))

        assert result == {"status": "present", "chunks": []}
        mock_handle.assert_awaited_once_with(mock_router, {"file_path": PATH, "memory_bank": BANK}, mock_container)


# ---------------------------------------------------------------------------
# Schema registry — snake_case GET_FILE_CHUNKS_SCHEMA
# ---------------------------------------------------------------------------


class TestGetFileChunksSchema:
    def test_schema_in_all_tool_schemas(self) -> None:
        from src.infrastructure.mcp.schemas import ALL_TOOL_SCHEMAS, GET_FILE_CHUNKS_SCHEMA

        assert GET_FILE_CHUNKS_SCHEMA in ALL_TOOL_SCHEMAS

    def test_schema_has_snake_case_params(self) -> None:
        from src.infrastructure.mcp.schemas import GET_FILE_CHUNKS_SCHEMA

        params = GET_FILE_CHUNKS_SCHEMA["parameters"]
        assert params["type"] == "object"
        assert set(params["properties"].keys()) == {"file_path", "memory_bank"}
        assert params["required"] == ["file_path", "memory_bank"]
