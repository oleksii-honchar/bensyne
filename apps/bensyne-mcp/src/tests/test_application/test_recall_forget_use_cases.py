"""Unit tests for RecallMemoryUseCase and ForgetMemoryUseCase."""

from unittest.mock import MagicMock

import pytest

from src.application.use_cases.recall_memory_use_case import RecallMemoryUseCase
from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock


class TestRecallMemoryUseCase:
    """Test RecallMemoryUseCase orchestration logic."""

    @pytest.fixture
    def mnemosyne_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def file_enrichment_service(self) -> MagicMock:
        """Mock enrichment service — mirrors contract: row copy + file_enrichment=None (pure)."""
        service = MagicMock()

        def _passthrough(memories, limit=5):
            rows = []
            for m in memories:
                row = dict(m)
                row["file_enrichment"] = None
                rows.append(row)
            return rows

        service.enrich.side_effect = _passthrough
        return service

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(self, mnemosyne_client, file_enrichment_service, logger) -> RecallMemoryUseCase:
        return RecallMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            file_enrichment_service=file_enrichment_service,
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
        mnemosyne_client.recall.return_value = Result.ok(mock_results)

        result = use_case.execute(
            {
                "query": "search term",
                "limit": 5,
                "memory_bank": "my_bank",
            }
        )

        assert result.is_ok is True
        # Enrichment post-pass adds file_enrichment=None to pure rows (service contract).
        assert result.value["results"] == [
            {"id": "mem_1", "content": "Some memory", "file_enrichment": None}
        ]
        assert result.value["memory_bank"] == "my_bank"
        mnemosyne_client.recall.assert_called_once_with("search term", 5)

    def test_execute_uses_default_limit(self, use_case, mnemosyne_client) -> None:
        """When no limit is provided, use default limit of 10."""
        mnemosyne_client.recall.return_value = Result.ok([])

        use_case.execute(
            {
                "query": "search term",
            }
        )

        mnemosyne_client.recall.assert_called_once_with("search term", 10)


class TestRecallMemoryEnrichment:
    """FileEnrichmentService post-pass on recall results (Task 15, D7)."""

    @pytest.fixture
    def mnemosyne_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def file_enrichment_service(self) -> MagicMock:
        service = MagicMock()

        def _passthrough(memories, limit=5):
            rows = []
            for m in memories:
                row = dict(m)
                row["file_enrichment"] = None
                rows.append(row)
            return rows

        service.enrich.side_effect = _passthrough
        return service

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(self, mnemosyne_client, file_enrichment_service, logger) -> RecallMemoryUseCase:
        return RecallMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            file_enrichment_service=file_enrichment_service,
            logger=logger,
        )

    def test_file_based_memory_gains_populated_file_enrichment(
        self, use_case, mnemosyne_client, file_enrichment_service
    ) -> None:
        """Recall of a file-based memory ⇒ result carries the service's enrichment block."""
        mock_results = [
            {
                "id": "mem_f1",
                "content": "chunk content",
                "file_enrichment": {
                    "file": {"id": "f1", "path": "/vault/a.md"},
                    "relations": [{"id": "r1", "relation_type": "sibling", "strength": 0.9}],
                },
            }
        ]
        mnemosyne_client.recall.return_value = Result.ok(
            [{"id": "mem_f1", "content": "chunk content"}]
        )
        file_enrichment_service.enrich.side_effect = lambda memories, limit=5: mock_results

        result = use_case.execute({"query": "q", "memory_bank": "bank"})

        assert result.is_ok is True
        enriched = result.value["results"][0]["file_enrichment"]
        assert enriched is not None
        assert enriched["file"]["id"] == "f1"
        assert enriched["relations"][0]["relation_type"] == "sibling"

    def test_pure_memory_result_byte_identical_except_file_enrichment_none(
        self, use_case, mnemosyne_client
    ) -> None:
        """Pure memory ⇒ file_enrichment is None and every other field unchanged."""
        original = {
            "id": "mem_pure",
            "content": "plain memory",
            "importance": 0.3,
            "relevance_score": 0.85,
        }
        mnemosyne_client.recall.return_value = Result.ok([dict(original)])

        result = use_case.execute({"query": "q", "memory_bank": "bank"})

        assert result.is_ok is True
        enriched_row = result.value["results"][0]
        assert enriched_row["file_enrichment"] is None
        without_key = {k: v for k, v in enriched_row.items() if k != "file_enrichment"}
        assert without_key == original

    def test_enrich_limit_propagates_to_service(self, use_case, mnemosyne_client, file_enrichment_service) -> None:
        """enrich_limit=2 ⇒ service.enrich called with limit 2."""
        mnemosyne_client.recall.return_value = Result.ok([{"id": "m1"}])

        use_case.execute({"query": "q", "memory_bank": "bank", "enrich_limit": 2})

        args, kwargs = file_enrichment_service.enrich.call_args
        limit = kwargs.get("limit", args[1] if len(args) > 1 else None)
        assert limit == 2

    def test_enrich_limit_absent_defaults_to_5(self, use_case, mnemosyne_client, file_enrichment_service) -> None:
        """No enrich_limit ⇒ service.enrich called with default 5."""
        mnemosyne_client.recall.return_value = Result.ok([{"id": "m1"}])

        use_case.execute({"query": "q", "memory_bank": "bank"})

        args, kwargs = file_enrichment_service.enrich.call_args
        limit = kwargs.get("limit", args[1] if len(args) > 1 else None)
        assert limit == 5

    def test_enrichment_scoped_to_returned_results_only(self, use_case, mnemosyne_client, file_enrichment_service) -> None:
        """Recall limit=1 ⇒ enrich receives exactly the returned results (1 row)."""
        mnemosyne_client.recall.return_value = Result.ok([{"id": "m1"}])

        use_case.execute({"query": "q", "memory_bank": "bank", "limit": 1})

        file_enrichment_service.enrich.assert_called_once()
        memories_arg = file_enrichment_service.enrich.call_args[0][0]
        assert len(memories_arg) == 1
        assert memories_arg[0]["id"] == "m1"

    def test_recall_ko_skips_enrichment(self, use_case, mnemosyne_client, file_enrichment_service) -> None:
        """When mnemosyne recall fails, enrichment must not run."""
        from src.utils.result import ErrorWithDetails

        mnemosyne_client.recall.return_value = Result.ko([ErrorWithDetails("RECALL_FAILED", {})])

        result = use_case.execute({"query": "q", "memory_bank": "bank"})

        assert result.is_ko is True
        file_enrichment_service.enrich.assert_not_called()

    def test_input_result_rows_not_mutated(self, use_case, mnemosyne_client) -> None:
        """Mnemosyne result dicts are never mutated in place by the post-pass."""
        original = {"id": "m1", "content": "x"}
        mnemosyne_client.recall.return_value = Result.ok([original])

        use_case.execute({"query": "q", "memory_bank": "bank"})

        assert "file_enrichment" not in original


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
        mnemosyne_client.forget.return_value = Result.ok(True)
        hash_index_service.remove.return_value = "a" * 64

        result = use_case.execute(
            {
                "memory_id": "mem_123",
                "memory_bank": "my_bank",
            }
        )

        assert result.is_ok is True
        assert result.value["status"] == "deleted"
        assert result.value["memory_bank"] == "my_bank"
        mnemosyne_client.forget.assert_called_once_with("mem_123")
        hash_index_service.remove.assert_called_once_with("mem_123")

    def test_execute_cleans_hash_index_on_successful_deletion(
        self, use_case, mnemosyne_client, hash_index_service
    ) -> None:
        """Hash index must be cleaned on successful deletion."""
        mnemosyne_client.forget.return_value = Result.ok(True)

        use_case.execute(
            {
                "memory_id": "mem_123",
            }
        )

        hash_index_service.remove.assert_called_once_with("mem_123")

    def test_execute_does_not_clean_hash_index_on_not_found(
        self, use_case, mnemosyne_client, hash_index_service
    ) -> None:
        """Hash index should not be cleaned when memory was not found."""
        mnemosyne_client.forget.return_value = Result.ok(False)

        result = use_case.execute(
            {
                "memory_id": "mem_123",
            }
        )

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

        result = use_case.execute(
            {
                "memory_id": "mem_123",
                "memory_bank": "my_bank",
            }
        )

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
        mnemosyne_client.forget.return_value = Result.ok(True)

        result = use_case.execute(
            {
                "memory_id": "mem_123",
                "memory_bank": "my_bank",
            }
        )

        assert result.is_ok is True
        assert result.value["status"] == "deleted"
        mnemosyne_client.forget.assert_called_once_with("mem_123")

    # -- Chunk cleanup on successful deletion --

    def test_execute_removes_chunks_for_deleted_memory(self, mnemosyne_client, hash_index_service, logger) -> None:
        """When memory is deleted, all file chunks referencing it must be removed."""
        from src.domain.file_chunk_entity import FileChunk
        from src.domain.models.file_chunk_model import ContentType as ChunkContentType
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
            section_header=None,
            parent_unit_ref=None,
            parent_unit_summary=None,
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
        mnemosyne_client.forget.return_value = Result.ok(True)

        use_case.execute(
            {
                "memory_id": "mem_123",
                "memory_bank": "my_bank",
            }
        )

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
        mnemosyne_client.forget.return_value = Result.ok(True)

        use_case.execute(
            {
                "memory_id": "mem_123",
                "memory_bank": "my_bank",
            }
        )

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
        mnemosyne_client.forget.return_value = Result.ok(False)

        use_case.execute(
            {
                "memory_id": "mem_123",
                "memory_bank": "my_bank",
            }
        )

        chunk_repository.get_chunks_by_memory_id.assert_not_called()
        file_service.remove_chunk.assert_not_called()

    # -- File deletion when file becomes empty --

    def test_execute_deletes_file_when_no_remaining_chunks(self, mnemosyne_client, hash_index_service, logger) -> None:
        """After removing a chunk, if the file has no remaining chunks, delete the file."""
        from src.domain.file_chunk_entity import FileChunk
        from src.domain.models.file_chunk_model import ContentType as ChunkContentType
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
            section_header=None,
            parent_unit_ref=None,
            parent_unit_summary=None,
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
        mnemosyne_client.forget.return_value = Result.ok(True)

        use_case.execute(
            {
                "memory_id": "mem_123",
                "memory_bank": "my_bank",
            }
        )

        file_service.delete_file.assert_called_once_with("f1")

    def test_execute_does_not_delete_file_when_chunks_remain(
        self, mnemosyne_client, hash_index_service, logger
    ) -> None:
        """After removing a chunk, if the file has remaining chunks, do not delete the file."""
        from src.domain.file_chunk_entity import FileChunk
        from src.domain.models.file_chunk_model import ContentType as ChunkContentType
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
            section_header=None,
            parent_unit_ref=None,
            parent_unit_summary=None,
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
        mnemosyne_client.forget.return_value = Result.ok(True)

        use_case.execute(
            {
                "memory_id": "mem_123",
                "memory_bank": "my_bank",
            }
        )

        file_service.delete_file.assert_not_called()

    # -- Hash index cleanup still happens --

    def test_execute_cleans_hash_index_after_chunk_cleanup(self, mnemosyne_client, hash_index_service, logger) -> None:
        """Hash index cleanup still happens after chunk cleanup on successful deletion."""
        from src.domain.file_chunk_entity import FileChunk
        from src.domain.models.file_chunk_model import ContentType as ChunkContentType
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
            section_header=None,
            parent_unit_ref=None,
            parent_unit_summary=None,
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
        mnemosyne_client.forget.return_value = Result.ok(True)

        use_case.execute(
            {
                "memory_id": "mem_123",
                "memory_bank": "my_bank",
            }
        )

        hash_index_service.remove.assert_called_once_with("mem_123")
