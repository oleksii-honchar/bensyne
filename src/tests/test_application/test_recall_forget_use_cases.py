"""Unit tests for RecallMemoryUseCase and ForgetMemoryUseCase."""

from unittest.mock import MagicMock

import pytest

from src.application.use_cases.recall_memory_use_case import RecallMemoryUseCase
from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase
from src.domain.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock


class TestRecallMemoryUseCase:
    """Test RecallMemoryUseCase orchestration logic."""

    @pytest.fixture
    def mnemosyne_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(self, mnemosyne_client, logger) -> RecallMemoryUseCase:
        return RecallMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            logger=logger,
        )

    # -- Validation --

    def test_validate_params_returns_ko_when_query_is_empty(self, use_case) -> None:
        """Empty query should return Result.ko with QUERY_REQUIRED."""
        result = use_case.validate_params({"query": ""})

        assert result.is_ko is True
        assert result.errors[0].error_code == "QUERY_REQUIRED"

    def test_validate_params_returns_ko_when_query_is_missing(self, use_case) -> None:
        """Missing query should return Result.ko with QUERY_REQUIRED."""
        result = use_case.validate_params({})

        assert result.is_ko is True
        assert result.errors[0].error_code == "QUERY_REQUIRED"

    def test_validate_params_returns_ok_when_query_present(self, use_case) -> None:
        """Non-empty query should pass validation."""
        result = use_case.validate_params({"query": "search term", "limit": 5})

        assert result.is_ok is True
        assert result.value["query"] == "search term"

    # -- Successful recall --

    def test_execute_returns_results_when_recall_succeeds(self, use_case, mnemosyne_client) -> None:
        """When recall succeeds, return Result.ok with results and memory_bank."""
        mock_results = [{"id": "mem_1", "content": "Some memory"}]
        mnemosyne_client.recall.return_value = mock_results

        result = use_case.execute({
            "query": "search term",
            "limit": 5,
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        assert result.value["results"] == mock_results
        assert result.value["memory_bank"] == "my_bank"
        mnemosyne_client.recall.assert_called_once_with("search term", 5)

    def test_execute_uses_default_limit(self, use_case, mnemosyne_client) -> None:
        """When no limit is provided, use default limit of 10."""
        mnemosyne_client.recall.return_value = []

        use_case.execute({
            "query": "search term",
        })

        mnemosyne_client.recall.assert_called_once_with("search term", 10)


class TestForgetMemoryUseCase:
    """Test ForgetMemoryUseCase orchestration logic."""

    @pytest.fixture
    def mnemosyne_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def hash_index_service(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def file_service(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def chunk_repository(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def bank_type_checker(self) -> MagicMock:
        return MagicMock(return_value="pure_memories")

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(
        self,
        mnemosyne_client,
        hash_index_service,
        file_service,
        chunk_repository,
        bank_type_checker,
        logger,
    ) -> ForgetMemoryUseCase:
        return ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=file_service,
            chunk_repository=chunk_repository,
            bank_type_checker=bank_type_checker,
        )

    # -- Validation --

    def test_validate_params_returns_ko_when_memory_id_is_empty(self, use_case) -> None:
        """Empty memory_id should return Result.ko with MEMORY_ID_REQUIRED."""
        result = use_case.validate_params({"memory_id": ""})

        assert result.is_ko is True
        assert result.errors[0].error_code == "MEMORY_ID_REQUIRED"

    def test_validate_params_returns_ko_when_memory_id_is_missing(self, use_case) -> None:
        """Missing memory_id should return Result.ko with MEMORY_ID_REQUIRED."""
        result = use_case.validate_params({})

        assert result.is_ko is True
        assert result.errors[0].error_code == "MEMORY_ID_REQUIRED"

    def test_validate_params_returns_ok_when_memory_id_present(self, use_case) -> None:
        """Non-empty memory_id should pass validation."""
        result = use_case.validate_params({"memory_id": "mem_123"})

        assert result.is_ok is True
        assert result.value["memory_id"] == "mem_123"

    # -- Successful forget --

    def test_execute_returns_deleted_when_forget_succeeds(self, use_case, mnemosyne_client, hash_index_service) -> None:
        """When forget succeeds, return Result.ok with deleted status and clean hash index."""
        mnemosyne_client.forget.return_value = {"status": "deleted", "memory_id": "mem_123"}
        hash_index_service.remove.return_value = "a" * 64

        result = use_case.execute({
            "memory_id": "mem_123",
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        assert result.value["status"] == "deleted"
        assert result.value["memory_bank"] == "my_bank"
        mnemosyne_client.forget.assert_called_once_with("mem_123")
        hash_index_service.remove.assert_called_once_with("mem_123")

    def test_execute_cleans_hash_index_on_successful_deletion(self, use_case, mnemosyne_client, hash_index_service) -> None:
        """Hash index must be cleaned on successful deletion."""
        mnemosyne_client.forget.return_value = {"status": "deleted", "memory_id": "mem_123"}

        use_case.execute({
            "memory_id": "mem_123",
        })

        hash_index_service.remove.assert_called_once_with("mem_123")

    def test_execute_does_not_clean_hash_index_on_not_found(self, use_case, mnemosyne_client, hash_index_service) -> None:
        """Hash index should not be cleaned when memory was not found."""
        mnemosyne_client.forget.return_value = {"status": "not_found", "memory_id": "mem_123"}

        result = use_case.execute({
            "memory_id": "mem_123",
        })

        assert result.is_ok is True
        assert result.value["status"] == "not_found"
        hash_index_service.remove.assert_not_called()

    # -- Bank type guard --

    def test_execute_rejects_non_pure_memories_bank(self, mnemosyne_client, hash_index_service, logger) -> None:
        """ForgetMemoryUseCase must reject banks that are not pure_memories."""
        bank_type_checker = lambda bank: "file_metadata"

        use_case = ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=MagicMock(),
            chunk_repository=MagicMock(),
            bank_type_checker=bank_type_checker,
        )

        result = use_case.execute({
            "memory_id": "mem_123",
            "memory_bank": "my_bank",
        })

        assert result.is_ko is True
        assert result.errors[0].error_code == "MEMORY_BANK_NOT_SUPPORTED"
        mnemosyne_client.forget.assert_not_called()

    def test_execute_allows_pure_memories_bank(self, mnemosyne_client, hash_index_service, logger) -> None:
        """ForgetMemoryUseCase must allow banks that are pure_memories."""
        bank_type_checker = lambda bank: "pure_memories"

        use_case = ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=MagicMock(),
            chunk_repository=MagicMock(),
            bank_type_checker=bank_type_checker,
        )
        mnemosyne_client.forget.return_value = {"status": "deleted", "memory_id": "mem_123"}

        result = use_case.execute({
            "memory_id": "mem_123",
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        assert result.value["status"] == "deleted"
        mnemosyne_client.forget.assert_called_once_with("mem_123")

    # -- Chunk cleanup on successful deletion --

    def test_execute_removes_chunks_for_deleted_memory(self, mnemosyne_client, hash_index_service, logger) -> None:
        """When memory is deleted, all file chunks referencing it must be removed."""
        from src.domain.entities.file_chunk import FileChunk
        from src.domain.schemas.file_chunk_schema import ContentType as ChunkContentType
        from datetime import datetime

        bank_type_checker = lambda bank: "pure_memories"
        file_service = MagicMock()
        chunk_repository = MagicMock()

        now = datetime(2026, 1, 1, 0, 0, 0)
        chunk = FileChunk(
            id="fc_f1_mem_123",
            file_id="f1",
            memory_id="mem_123",
            chunk_index=0,
            start_line=0,
            end_line=10,
            content_hash="abc",
            content_type=ChunkContentType.TEXT,
            is_partial=False,
            created_at=now,
            updated_at=now,
        )
        chunk_repository.get_chunks_by_memory_id.return_value = Result.ok([chunk])

        use_case = ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=file_service,
            chunk_repository=chunk_repository,
            bank_type_checker=bank_type_checker,
        )
        mnemosyne_client.forget.return_value = {"status": "deleted", "memory_id": "mem_123"}

        use_case.execute({
            "memory_id": "mem_123",
            "memory_bank": "my_bank",
        })

        file_service.remove_chunk.assert_called_once_with("f1", "mem_123")

    def test_execute_no_chunk_cleanup_when_no_chunks(self, mnemosyne_client, hash_index_service, logger) -> None:
        """When no chunks reference the memory, file_service.remove_chunk must not be called."""
        bank_type_checker = lambda bank: "pure_memories"
        file_service = MagicMock()
        chunk_repository = MagicMock()
        chunk_repository.get_chunks_by_memory_id.return_value = Result.ok([])

        use_case = ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=file_service,
            chunk_repository=chunk_repository,
            bank_type_checker=bank_type_checker,
        )
        mnemosyne_client.forget.return_value = {"status": "deleted", "memory_id": "mem_123"}

        use_case.execute({
            "memory_id": "mem_123",
            "memory_bank": "my_bank",
        })

        file_service.remove_chunk.assert_not_called()

    def test_execute_no_chunk_cleanup_when_memory_not_found(self, mnemosyne_client, hash_index_service, logger) -> None:
        """When memory was not found, chunk cleanup must not run."""
        bank_type_checker = lambda bank: "pure_memories"
        file_service = MagicMock()
        chunk_repository = MagicMock()

        use_case = ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=file_service,
            chunk_repository=chunk_repository,
            bank_type_checker=bank_type_checker,
        )
        mnemosyne_client.forget.return_value = {"status": "not_found", "memory_id": "mem_123"}

        use_case.execute({
            "memory_id": "mem_123",
            "memory_bank": "my_bank",
        })

        chunk_repository.get_chunks_by_memory_id.assert_not_called()
        file_service.remove_chunk.assert_not_called()

    # -- File deletion when file becomes empty --

    def test_execute_deletes_file_when_no_remaining_chunks(self, mnemosyne_client, hash_index_service, logger) -> None:
        """After removing a chunk, if the file has no remaining chunks, delete the file."""
        from src.domain.entities.file_chunk import FileChunk
        from src.domain.schemas.file_chunk_schema import ContentType as ChunkContentType
        from datetime import datetime

        bank_type_checker = lambda bank: "pure_memories"
        file_service = MagicMock()
        chunk_repository = MagicMock()

        now = datetime(2026, 1, 1, 0, 0, 0)
        chunk = FileChunk(
            id="fc_f1_mem_123",
            file_id="f1",
            memory_id="mem_123",
            chunk_index=0,
            start_line=0,
            end_line=10,
            content_hash="abc",
            content_type=ChunkContentType.TEXT,
            is_partial=False,
            created_at=now,
            updated_at=now,
        )
        chunk_repository.get_chunks_by_memory_id.return_value = Result.ok([chunk])

        # After removing the chunk, file has no remaining chunks
        file_service.remove_chunk.return_value = Result.ok(None, events=[])
        file_service.get_chunks_count_by_file_id.return_value = Result.ok(0)

        use_case = ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=file_service,
            chunk_repository=chunk_repository,
            bank_type_checker=bank_type_checker,
        )
        mnemosyne_client.forget.return_value = {"status": "deleted", "memory_id": "mem_123"}

        use_case.execute({
            "memory_id": "mem_123",
            "memory_bank": "my_bank",
        })

        file_service.delete_file.assert_called_once_with("f1")

    def test_execute_does_not_delete_file_when_chunks_remain(self, mnemosyne_client, hash_index_service, logger) -> None:
        """After removing a chunk, if the file has remaining chunks, do not delete the file."""
        from src.domain.entities.file_chunk import FileChunk
        from src.domain.schemas.file_chunk_schema import ContentType as ChunkContentType
        from datetime import datetime

        bank_type_checker = lambda bank: "pure_memories"
        file_service = MagicMock()
        chunk_repository = MagicMock()

        now = datetime(2026, 1, 1, 0, 0, 0)
        chunk = FileChunk(
            id="fc_f1_mem_123",
            file_id="f1",
            memory_id="mem_123",
            chunk_index=0,
            start_line=0,
            end_line=10,
            content_hash="abc",
            content_type=ChunkContentType.TEXT,
            is_partial=False,
            created_at=now,
            updated_at=now,
        )
        chunk_repository.get_chunks_by_memory_id.return_value = Result.ok([chunk])

        # After removing the chunk, file still has remaining chunks
        file_service.remove_chunk.return_value = Result.ok(None, events=[])
        file_service.get_chunks_count_by_file_id.return_value = Result.ok(2)

        use_case = ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=file_service,
            chunk_repository=chunk_repository,
            bank_type_checker=bank_type_checker,
        )
        mnemosyne_client.forget.return_value = {"status": "deleted", "memory_id": "mem_123"}

        use_case.execute({
            "memory_id": "mem_123",
            "memory_bank": "my_bank",
        })

        file_service.delete_file.assert_not_called()

    # -- Hash index cleanup still happens --

    def test_execute_cleans_hash_index_after_chunk_cleanup(self, mnemosyne_client, hash_index_service, logger) -> None:
        """Hash index cleanup still happens after chunk cleanup on successful deletion."""
        from src.domain.entities.file_chunk import FileChunk
        from src.domain.schemas.file_chunk_schema import ContentType as ChunkContentType
        from datetime import datetime

        bank_type_checker = lambda bank: "pure_memories"
        file_service = MagicMock()
        chunk_repository = MagicMock()

        now = datetime(2026, 1, 1, 0, 0, 0)
        chunk = FileChunk(
            id="fc_f1_mem_123",
            file_id="f1",
            memory_id="mem_123",
            chunk_index=0,
            start_line=0,
            end_line=10,
            content_hash="abc",
            content_type=ChunkContentType.TEXT,
            is_partial=False,
            created_at=now,
            updated_at=now,
        )
        chunk_repository.get_chunks_by_memory_id.return_value = Result.ok([chunk])
        file_service.remove_chunk.return_value = Result.ok(None, events=[])
        file_service.get_chunks_count_by_file_id.return_value = Result.ok(0)

        use_case = ForgetMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            hash_index_service=hash_index_service,
            logger=logger,
            file_service=file_service,
            chunk_repository=chunk_repository,
            bank_type_checker=bank_type_checker,
        )
        mnemosyne_client.forget.return_value = {"status": "deleted", "memory_id": "mem_123"}

        use_case.execute({
            "memory_id": "mem_123",
            "memory_bank": "my_bank",
        })

        hash_index_service.remove.assert_called_once_with("mem_123")
