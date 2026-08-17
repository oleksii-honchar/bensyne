"""Unit tests for RememberMemoryUseCase."""

from unittest.mock import MagicMock

import pytest

from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
from src.domain.memory_entity import Memory
from src.utils.result import ErrorWithDetails, Result
from src.tests.test_domain.domain_test_utils import a_memory
from src.utils.structured_logging import LoggerMock


def _contract_v1_metadata(file_path: str = "notes/todo.md") -> dict:
    """A minimal unified chunk contract v1 metadata payload (has file_path)."""
    return {
        "contract_version": 1,
        "file_path": file_path,
        "chunk_index": 0,
        "total_chunks": 1,
    }


class TestRememberMemoryUseCase:
    """Test RememberMemoryUseCase orchestration logic."""

    @pytest.fixture
    def memory_repository(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def hash_index_service(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def file_service(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(
        self, memory_repository, hash_index_service, file_service, logger
    ) -> RememberMemoryUseCase:
        return RememberMemoryUseCase(
            memory_repository=memory_repository,
            hash_index_service=hash_index_service,
            file_service=file_service,
            logger=logger,
        )

    # -- Validation --

    def test_validate_params_returns_ko_when_content_is_empty(self, use_case) -> None:
        """Empty content should return Result.ko with CONTENT_REQUIRED."""
        result = use_case.validate_params({"content": ""})

        assert result.is_ko is True
        assert result.errors[0].error_code == "CONTENT_REQUIRED"

    def test_validate_params_returns_ko_when_content_missing(self, use_case) -> None:
        """Missing content should return Result.ko with CONTENT_REQUIRED."""
        result = use_case.validate_params({})

        assert result.is_ko is True
        assert result.errors[0].error_code == "CONTENT_REQUIRED"

    def test_validate_params_returns_ok_when_content_present(self, use_case) -> None:
        """Non-empty content should pass validation."""
        result = use_case.validate_params({"content": "some content"})

        assert result.is_ok is True
        assert result.value == {"content": "some content"}

    # -- Deduplication --

    def test_execute_returns_deduplicated_when_chunk_hash_exists(self, use_case, hash_index_service) -> None:
        """When the hash index already has the chunk_hash (read from metadata), return deduplicated."""
        existing_id = "existing_memory_id"
        hash_index_service.lookup.return_value = Result.ok(existing_id)

        result = use_case.execute(
            {
                "content": "file content",
                "memory_bank": "my_bank",
                "metadata": {"chunk_hash": "a" * 64},
            }
        )

        assert result.is_ok is True
        assert result.value["status"] == "deduplicated"
        assert result.value["memory_id"] == existing_id
        assert result.value["memory_bank"] == "my_bank"
        # Repository should NOT be called when deduplicated
        use_case.memory_repository.save.assert_not_called()
        # Hash index lookup was called with the chunk_hash read from metadata
        hash_index_service.lookup.assert_called_once_with("a" * 64)

    def test_extract_chunk_hash_reads_metadata(self) -> None:
        """_extract_chunk_hash reads metadata.chunk_hash (snake_case); ignores top-level hash."""
        assert RememberMemoryUseCase._extract_chunk_hash({"metadata": {"chunk_hash": "abc"}}) == "abc"
        # Absent chunk_hash ⇒ None.
        assert RememberMemoryUseCase._extract_chunk_hash({"metadata": {}}) is None
        # No metadata ⇒ None.
        assert RememberMemoryUseCase._extract_chunk_hash({}) is None
        # Metadata not a dict ⇒ None.
        assert RememberMemoryUseCase._extract_chunk_hash({"metadata": "not-a-dict"}) is None
        # Legacy top-level hash is NOT read (off the wire, D13).
        assert RememberMemoryUseCase._extract_chunk_hash({"hash": "legacy", "metadata": {}}) is None

    def test_execute_no_chunk_hash_bypasses_dedup(self, use_case, memory_repository, hash_index_service) -> None:
        """No chunk_hash in metadata ⇒ dedup bypassed entirely (pure memories unchanged)."""
        memory = a_memory(id="new_memory_id")
        memory_repository.save.return_value = Result.ok(memory)

        result = use_case.execute(
            {
                "id": "new_memory_id",
                "content": "plain content",
                "memory_bank": "my_bank",
                "metadata": {"tags": ["x"]},  # no chunk_hash anywhere
            }
        )

        assert result.is_ok is True
        assert result.value["status"] == "stored"
        # Dedup index never consulted when there is no chunk_hash.
        hash_index_service.lookup.assert_not_called()
        hash_index_service.store.assert_not_called()

    def test_execute_dedup_hit_still_materializes_with_existing_id(
        self, use_case, hash_index_service, file_service
    ) -> None:
        """Dedup HIT still materializes with the EXISTING memory id (D14/S3) — not a bare early-exit."""
        from src.application.services.file_service import derive_file_id

        existing_id = "existing_memory_id"
        hash_index_service.lookup.return_value = Result.ok(existing_id)
        expected_file_id = derive_file_id("my_bank", "notes/todo.md")
        file_service.materialize_file_context.return_value = Result.ok(
            {"file_id": expected_file_id, "relations_created": 0, "rebuilt": False, "errors": []}
        )

        result = use_case.execute(
            {
                "content": "file content",
                "memory_bank": "my_bank",
                "metadata": {**_contract_v1_metadata("notes/todo.md"), "chunk_hash": "a" * 64},
            }
        )

        assert result.is_ok is True
        # Response carries dedup status + existing id + memory_bank.
        assert result.value["status"] == "deduplicated"
        assert result.value["memory_id"] == existing_id
        assert result.value["memory_bank"] == "my_bank"
        # Materialization RAN with the EXISTING memory id (idempotent upsert links
        # the shared memory under this file — the S3 cross-file fix).
        materialize_args = file_service.materialize_file_context.call_args
        assert materialize_args[0][0] == "my_bank"
        assert materialize_args[0][1].file_path == "notes/todo.md"
        assert materialize_args[0][2] == existing_id
        # No new memory saved on a dedup hit.
        use_case.memory_repository.save.assert_not_called()
        # Materialization success surfaced in the response.
        assert result.value["file_materialization"] == {"status": "ok", "file_id": expected_file_id}

    def test_execute_dedup_hit_materialization_failure_is_non_fatal(
        self, use_case, hash_index_service, file_service
    ) -> None:
        """Materialize error on the dedup-HIT path is non-fatal (S2): remember still succeeds."""
        existing_id = "existing_memory_id"
        hash_index_service.lookup.return_value = Result.ok(existing_id)
        file_service.materialize_file_context.return_value = Result.ko(
            [ErrorWithDetails("MATERIALIZE_CHUNK_ERROR", {"file_id": "file_x"})]
        )

        result = use_case.execute(
            {
                "content": "file content",
                "memory_bank": "my_bank",
                "metadata": {**_contract_v1_metadata(), "chunk_hash": "a" * 64},
            }
        )

        assert result.is_ok is True
        # Remember still succeeds on the dedup hit.
        assert result.value["status"] == "deduplicated"
        assert result.value["memory_id"] == existing_id
        use_case.memory_repository.save.assert_not_called()
        # Materialization failure surfaced additively with non-empty errors.
        fm = result.value["file_materialization"]
        assert fm["status"] == "failed"
        assert len(fm["errors"]) > 0

    # -- Successful storage --

    def test_execute_returns_stored_when_memory_created(self, use_case, memory_repository) -> None:
        """When memory is saved successfully, return stored status with memory_id."""
        memory = a_memory(id="new_memory_id")
        memory_repository.save.return_value = Result.ok(memory)

        result = use_case.execute(
            {
                "id": "new_memory_id",
                "content": "new memory content",
            }
        )

        assert result.is_ok is True
        assert result.value["status"] == "stored"
        assert result.value["memory_id"] == "new_memory_id"

    # -- Materialization wiring (spec §4.1, S2 non-fatal contract) --

    def test_execute_materializes_after_save_with_saved_id(self, use_case, memory_repository, file_service) -> None:
        """Contract v1 metadata ⇒ mnemosyne save BEFORE materialize; saved id is authoritative."""
        from src.application.services.file_service import derive_file_id

        # Mnemosyne re-ids the memory on save — the SAVED id must win (D2).
        saved_memory = a_memory(id="reid_by_mnemosyne")
        memory_repository.save.return_value = Result.ok(saved_memory)
        expected_file_id = derive_file_id("my_bank", "notes/todo.md")
        file_service.materialize_file_context.return_value = Result.ok(
            {"file_id": expected_file_id, "relations_created": 0, "rebuilt": False, "errors": []}
        )

        result = use_case.execute(
            {
                "id": "client_side_id",
                "content": "chunk content",
                "memory_bank": "my_bank",
                "metadata": _contract_v1_metadata("notes/todo.md"),
            }
        )

        assert result.is_ok is True
        assert memory_repository.save.call_count == 1
        assert file_service.materialize_file_context.call_count == 1
        # Direct argument assertion: materialize received (bank, context, SAVED id).
        materialize_args = file_service.materialize_file_context.call_args
        assert materialize_args[0][0] == "my_bank"
        assert materialize_args[0][1].file_path == "notes/todo.md"
        assert materialize_args[0][2] == "reid_by_mnemosyne"
        # Response carries the derived file_id on success.
        assert result.value["status"] == "stored"
        assert result.value["memory_id"] == "reid_by_mnemosyne"
        assert result.value["file_materialization"] == {"status": "ok", "file_id": expected_file_id}

    def test_execute_call_order_save_before_materialize(self, use_case, memory_repository, file_service) -> None:
        """Spy both calls and assert mnemosyne save is invoked before materialization."""
        order: list[str] = []
        saved_memory = a_memory(id="saved_id")

        def _save_spy(memory):
            order.append("save")
            return Result.ok(saved_memory)

        def _materialize_spy(bank, context, memory_id):
            order.append("materialize")
            return Result.ok({"file_id": "file_abc", "relations_created": 0, "rebuilt": False, "errors": []})

        memory_repository.save.side_effect = _save_spy
        file_service.materialize_file_context.side_effect = _materialize_spy

        result = use_case.execute(
            {
                "id": "client_id",
                "content": "chunk content",
                "memory_bank": "bank_a",
                "metadata": _contract_v1_metadata(),
            }
        )

        assert result.is_ok is True
        assert order == ["save", "materialize"]

    def test_execute_materialization_failure_is_non_fatal(self, use_case, memory_repository, file_service) -> None:
        """Materialize error Result ⇒ memory still stored; response flags materialization failed."""
        saved_memory = a_memory(id="new_memory_id")
        memory_repository.save.return_value = Result.ok(saved_memory)
        file_service.materialize_file_context.return_value = Result.ko(
            [ErrorWithDetails("MATERIALIZE_CHUNK_ERROR", {"file_id": "file_x"})]
        )

        result = use_case.execute(
            {
                "id": "new_memory_id",
                "content": "chunk content",
                "memory_bank": "my_bank",
                "metadata": _contract_v1_metadata(),
            }
        )

        assert result.is_ok is True
        # The memory IS stored — success for the memory itself.
        assert result.value["status"] == "stored"
        assert result.value["memory_id"] == "new_memory_id"
        # Materialization failure surfaced additively with non-empty errors.
        fm = result.value["file_materialization"]
        assert fm["status"] == "failed"
        assert len(fm["errors"]) > 0

    def test_execute_no_file_path_means_no_materialization_key(
        self, use_case, memory_repository, file_service
    ) -> None:
        """Metadata without file_path ⇒ response byte-identical to today; FileService never called."""
        memory = a_memory(id="new_memory_id")
        memory_repository.save.return_value = Result.ok(memory)

        result = use_case.execute(
            {
                "id": "new_memory_id",
                "content": "plain content",
                "memory_bank": "my_bank",
                "metadata": {"tags": ["x"]},  # no file_path anywhere
            }
        )

        assert result.is_ok is True
        assert result.value == {
            "status": "stored",
            "memory_id": "new_memory_id",
            "memory_bank": "my_bank",
        }
        assert "file_materialization" not in result.value
        file_service.materialize_file_context.assert_not_called()

    def test_execute_no_metadata_means_no_materialization_key(
        self, use_case, memory_repository, file_service
    ) -> None:
        """Absent metadata ⇒ plain memory response, FileService never called."""
        memory = a_memory(id="new_memory_id")
        memory_repository.save.return_value = Result.ok(memory)

        result = use_case.execute(
            {
                "id": "new_memory_id",
                "content": "plain content",
            }
        )

        assert result.is_ok is True
        assert "file_materialization" not in result.value
        file_service.materialize_file_context.assert_not_called()

    def test_execute_returns_stored_with_memory_bank(self, use_case, memory_repository) -> None:
        """Stored result should include memory_bank from params."""
        memory = a_memory(id="new_memory_id")
        memory_repository.save.return_value = Result.ok(memory)

        result = use_case.execute(
            {
                "id": "new_memory_id",
                "content": "new memory content",
                "memory_bank": "my_bank",
            }
        )

        assert result.is_ok is True
        assert result.value["memory_bank"] == "my_bank"

    def test_execute_stores_chunk_hash_after_save(self, use_case, memory_repository, hash_index_service) -> None:
        """chunk_hash (from metadata) should be stored in the hash index after successful save."""
        memory = a_memory(id="new_memory_id")
        memory_repository.save.return_value = Result.ok(memory)
        hash_index_service.lookup.return_value = Result.ok(None)  # No dedup — new chunk_hash
        test_hash = "b" * 64

        use_case.execute(
            {
                "id": "new_memory_id",
                "content": "file content",
                "metadata": {"chunk_hash": test_hash},
            }
        )

        hash_index_service.store.assert_called_once_with(test_hash, "new_memory_id")

    # -- Repository failure --

    def test_execute_returns_ko_when_repository_save_fails(self, use_case, memory_repository) -> None:
        """When repository save fails, return Result.ko."""
        memory_repository.save.return_value = Result.ko([ErrorWithDetails("SAVE_ERROR", {})])

        result = use_case.execute(
            {
                "id": "new_memory_id",
                "content": "new memory content",
            }
        )

        assert result.is_ko is True
        assert result.errors[0].error_code == "SAVE_ERROR"

    # -- Memory.of failure --

    def test_execute_returns_ko_when_memory_of_fails(self, use_case) -> None:
        """When Memory.of fails validation, return Result.ko."""
        # Invalid scope triggers Memory.of validation failure
        result = use_case.execute(
            {
                "content": "some content",
                "scope": "invalid_scope",
            }
        )

        assert result.is_ko is True
