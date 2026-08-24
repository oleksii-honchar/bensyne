"""Unit tests for ForgetFileUseCase."""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.forget_file_use_case import ForgetFileUseCase
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock
from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.file_chunk_entity import FileChunk
from src.domain.models.file_chunk_model import ContentType as ChunkContentType

NOW = datetime(2026, 1, 1, 0, 0, 0)
VALID_HASH = "a" * 64


def _a_file(
    id: str = "f1",
    path: str = "/vault/notes/test.md",
    status: FileStatus = FileStatus.INDEXED,
) -> File:
    return File(
        id=id,
        path=path,
        source_type=SourceType.VAULT,
        file_role=None,
        hash=VALID_HASH,
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
        content_type=ChunkContentType.TEXT,
        is_partial=False,
        section_header=None,
        parent_unit_ref=None,
        parent_unit_summary=None,
        created_at=NOW,
        updated_at=NOW,
    )


class TestForgetFileUseCase:
    """Test ForgetFileUseCase orchestration logic."""

    @pytest.fixture
    def file_service(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def hash_index_service(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def mnemosyne_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(
        self,
        file_service: MagicMock,
        hash_index_service: MagicMock,
        mnemosyne_client: MagicMock,
        logger: LoggerMock,
    ) -> ForgetFileUseCase:
        return ForgetFileUseCase(
            file_service=file_service,
            hash_index_service=hash_index_service,
            mnemosyne_client=mnemosyne_client,
            logger=logger,
            memory_bank="my_bank",
        )

    # -- Validation --

    def test_validate_params_returns_ko_when_file_path_is_empty(self, use_case: ForgetFileUseCase) -> None:
        """Empty file_path should return Result.ko with FILE_PATH_REQUIRED."""
        result = use_case.validate_params({"file_path": ""})

        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_PATH_REQUIRED"

    def test_validate_params_returns_ko_when_file_path_is_missing(self, use_case: ForgetFileUseCase) -> None:
        """Missing file_path should return Result.ko with FILE_PATH_REQUIRED."""
        result = use_case.validate_params({})

        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_PATH_REQUIRED"

    def test_validate_params_returns_ok_when_file_path_present(self, use_case: ForgetFileUseCase) -> None:
        """Non-empty file_path should pass validation."""
        result = use_case.validate_params({"file_path": "/vault/notes/test.md"})

        assert result.is_ok is True
        assert result.value["file_path"] == "/vault/notes/test.md"

    # -- File not found --

    def test_execute_returns_file_not_found_when_file_not_found(
        self, use_case: ForgetFileUseCase, file_service: MagicMock
    ) -> None:
        """When get_file_by_path returns FILE_NOT_FOUND, propagate it."""
        file_service.get_file_by_path.return_value = Result.ko(
            [ErrorWithDetails("FILE_NOT_FOUND", {"path": "/vault/notes/test.md"})]
        )

        result = use_case.execute({"file_path": "/vault/notes/test.md"})

        assert result.is_ko is True
        assert result.errors[0].error_code == "FILE_NOT_FOUND"

    # -- Already deleted --

    def test_execute_returns_already_deleted_when_file_is_deleted(
        self, use_case: ForgetFileUseCase, file_service: MagicMock, mnemosyne_client: MagicMock
    ) -> None:
        """When file is already DELETED, return already_deleted without calling mnemosyne."""
        deleted_file = _a_file(id="f1", status=FileStatus.DELETED)
        file_service.get_file_by_path.return_value = Result.ok(deleted_file)

        result = use_case.execute({"file_path": "/vault/notes/test.md"})

        assert result.is_ok is True
        assert result.value["status"] == "already_deleted"
        # mnemosyne.forget should NOT be called for already-deleted files
        mnemosyne_client.forget.assert_not_called()

    # -- Successful forget (not shared) --

    def test_execute_forgets_file_when_memories_not_shared(
        self,
        use_case: ForgetFileUseCase,
        file_service: MagicMock,
        hash_index_service: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When file's memories are not shared, forget them and mark file DELETED."""
        file = _a_file(id="f1")
        file_service.get_file_by_path.return_value = Result.ok(file)

        # File has two chunks (memories)
        chunk1 = _a_chunk(id="c1", file_id="f1", memory_id="mem_1")
        chunk2 = _a_chunk(id="c2", file_id="f1", memory_id="mem_2")
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk1, chunk2])

        # Neither memory is shared (only referenced by f1)
        file_service.get_chunks_by_memory_id.side_effect = [
            Result.ok([chunk1]),  # mem_1 only in f1
            Result.ok([chunk2]),  # mem_2 only in f1
        ]

        # mnemosyne.forget succeeds
        mnemosyne_client.forget.return_value = Result.ok(True)

        # delete_file succeeds
        file_service.delete_file.return_value = Result.ok(file)

        result = use_case.execute({"file_path": "/vault/notes/test.md"})

        assert result.is_ok is True
        assert result.value["status"] == "forgotten"
        assert result.value["file_id"] == "f1"
        assert result.value["files_affected"] == 1

        # mnemosyne.forget called for both memories
        mnemosyne_client.forget.assert_any_call("mem_1")
        mnemosyne_client.forget.assert_any_call("mem_2")
        assert mnemosyne_client.forget.call_count == 2

        # hash_index.remove called for both memories
        hash_index_service.remove.assert_any_call("mem_1")
        hash_index_service.remove.assert_any_call("mem_2")
        assert hash_index_service.remove.call_count == 2

        # delete_file called to mark file as DELETED
        file_service.delete_file.assert_called_once_with("f1")

    # -- Shared memory guard --

    def test_execute_preserves_shared_memory(
        self,
        use_case: ForgetFileUseCase,
        file_service: MagicMock,
        hash_index_service: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When a memory is shared with another file, don't forget it but still delete the file."""
        file = _a_file(id="f1")
        file_service.get_file_by_path.return_value = Result.ok(file)

        # File has one chunk with a shared memory
        chunk1 = _a_chunk(id="c1", file_id="f1", memory_id="mem_shared")
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk1])

        # Memory is shared with f2
        shared_chunk_f1 = _a_chunk(id="c1", file_id="f1", memory_id="mem_shared")
        shared_chunk_f2 = _a_chunk(id="c2", file_id="f2", memory_id="mem_shared")
        file_service.get_chunks_by_memory_id.return_value = Result.ok([shared_chunk_f1, shared_chunk_f2])

        # delete_file succeeds
        file_service.delete_file.return_value = Result.ok(file)

        result = use_case.execute({"file_path": "/vault/notes/test.md"})

        assert result.is_ok is True
        assert result.value["status"] == "forgotten"

        # mnemosyne.forget NOT called for shared memory
        mnemosyne_client.forget.assert_not_called()

        # hash_index.remove NOT called for shared memory
        hash_index_service.remove.assert_not_called()

        # delete_file still called to mark file as DELETED (D20 cascade removes chunk rows)
        file_service.delete_file.assert_called_once_with("f1")

    def test_execute_mixed_shared_and_unshared_memories(
        self,
        use_case: ForgetFileUseCase,
        file_service: MagicMock,
        hash_index_service: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When file has both shared and unshared memories, only forget unshared ones."""
        file = _a_file(id="f1")
        file_service.get_file_by_path.return_value = Result.ok(file)

        # File has two chunks: one shared, one unshared
        chunk_shared = _a_chunk(id="c1", file_id="f1", memory_id="mem_shared")
        chunk_unshared = _a_chunk(id="c2", file_id="f1", memory_id="mem_unique")
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk_shared, chunk_unshared])

        # mem_shared is shared with f2, mem_unique is only in f1
        def get_chunks_by_memory_id(memory_id: str) -> Result[list[FileChunk]]:
            if memory_id == "mem_shared":
                return Result.ok([
                    _a_chunk(id="c1", file_id="f1", memory_id="mem_shared"),
                    _a_chunk(id="c2", file_id="f2", memory_id="mem_shared"),
                ])
            else:  # mem_unique
                return Result.ok([
                    _a_chunk(id="c3", file_id="f1", memory_id="mem_unique"),
                ])

        file_service.get_chunks_by_memory_id.side_effect = get_chunks_by_memory_id

        # mnemosyne.forget succeeds
        mnemosyne_client.forget.return_value = Result.ok(True)

        # delete_file succeeds
        file_service.delete_file.return_value = Result.ok(file)

        result = use_case.execute({"file_path": "/vault/notes/test.md"})

        assert result.is_ok is True
        assert result.value["status"] == "forgotten"

        # mnemosyne.forget called ONLY for unshared memory
        mnemosyne_client.forget.assert_called_once_with("mem_unique")

        # hash_index.remove called ONLY for unshared memory
        hash_index_service.remove.assert_called_once_with("mem_unique")

        # delete_file called
        file_service.delete_file.assert_called_once_with("f1")

    # -- Idempotency --

    def test_execute_idempotent_second_call_returns_already_deleted(
        self,
        use_case: ForgetFileUseCase,
        file_service: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Second call for same file returns already_deleted without re-calling mnemosyne."""
        # First call: file is INDEXED
        indexed_file = _a_file(id="f1", status=FileStatus.INDEXED)
        # Second call: file is DELETED (after first call marks it as such)
        deleted_file = _a_file(id="f1", status=FileStatus.DELETED)

        # Setup get_file_by_path to return different files for each call
        file_service.get_file_by_path.side_effect = [
            Result.ok(indexed_file),
            Result.ok(deleted_file),
        ]

        # First call: file has one unshared memory
        chunk1 = _a_chunk(id="c1", file_id="f1", memory_id="mem_1")
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk1])
        file_service.get_chunks_by_memory_id.return_value = Result.ok([chunk1])
        mnemosyne_client.forget.return_value = Result.ok(True)
        file_service.delete_file.return_value = Result.ok(deleted_file)

        # First call
        result1 = use_case.execute({"file_path": "/vault/notes/test.md"})
        assert result1.is_ok is True
        assert result1.value["status"] == "forgotten"

        # Second call
        result2 = use_case.execute({"file_path": "/vault/notes/test.md"})
        assert result2.is_ok is True
        assert result2.value["status"] == "already_deleted"

        # mnemosyne.forget called only once total (from first call)
        mnemosyne_client.forget.assert_called_once_with("mem_1")

    # -- Error handling --

    def test_execute_returns_ko_when_mnemosyne_forget_fails(
        self,
        use_case: ForgetFileUseCase,
        file_service: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """When mnemosyne.forget fails, return the error."""
        file = _a_file(id="f1")
        file_service.get_file_by_path.return_value = Result.ok(file)

        chunk1 = _a_chunk(id="c1", file_id="f1", memory_id="mem_1")
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk1])
        file_service.get_chunks_by_memory_id.return_value = Result.ok([chunk1])

        # mnemosyne.forget fails
        mnemosyne_client.forget.return_value = Result.ko(
            [ErrorWithDetails("DATABASE_ERROR", {"detail": "Connection failed"})]
        )

        result = use_case.execute({"file_path": "/vault/notes/test.md"})

        assert result.is_ko is True
        assert result.errors[0].error_code == "DATABASE_ERROR"

    # -- Chunk loading error handling --

    def test_execute_returns_ko_when_get_chunks_by_file_id_fails(
        self, use_case: ForgetFileUseCase, file_service: MagicMock
    ) -> None:
        """When loading chunks fails, return the error."""
        file = _a_file(id="f1")
        file_service.get_file_by_path.return_value = Result.ok(file)

        file_service.get_chunks_by_file_id.return_value = Result.ko(
            [ErrorWithDetails("CHUNKS_ERROR", {"detail": "DB error"})]
        )

        result = use_case.execute({"file_path": "/vault/notes/test.md"})

        assert result.is_ko is True
        assert result.errors[0].error_code == "CHUNKS_ERROR"

    # -- Empty memory_id handling --

    def test_execute_skips_chunks_with_empty_memory_id(
        self,
        use_case: ForgetFileUseCase,
        file_service: MagicMock,
        mnemosyne_client: MagicMock,
    ) -> None:
        """Chunks with empty memory_id should be skipped."""
        file = _a_file(id="f1")
        file_service.get_file_by_path.return_value = Result.ok(file)

        # Chunk with empty memory_id
        chunk_empty = _a_chunk(id="c1", file_id="f1", memory_id="")
        # Chunk with valid memory_id
        chunk_valid = _a_chunk(id="c2", file_id="f1", memory_id="mem_valid")
        file_service.get_chunks_by_file_id.return_value = Result.ok([chunk_empty, chunk_valid])

        # Only the valid memory is checked
        file_service.get_chunks_by_memory_id.return_value = Result.ok([chunk_valid])
        mnemosyne_client.forget.return_value = Result.ok(True)
        file_service.delete_file.return_value = Result.ok(file)

        result = use_case.execute({"file_path": "/vault/notes/test.md"})

        assert result.is_ok is True
        # mnemosyne.forget called only for valid memory
        mnemosyne_client.forget.assert_called_once_with("mem_valid")