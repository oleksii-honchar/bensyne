"""Unit tests for RememberMemoryUseCase."""

from unittest.mock import MagicMock

import pytest

from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
from src.domain.memory_entity import Memory
from src.utils.result import ErrorWithDetails, Result
from src.tests.test_domain.domain_test_utils import a_memory
from src.utils.structured_logging import LoggerMock


class TestRememberMemoryUseCase:
    """Test RememberMemoryUseCase orchestration logic."""

    @pytest.fixture
    def memory_repository(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def hash_index_service(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(self, memory_repository, hash_index_service, logger) -> RememberMemoryUseCase:
        return RememberMemoryUseCase(
            memory_repository=memory_repository,
            hash_index_service=hash_index_service,
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

    def test_execute_returns_deduplicated_when_hash_exists(self, use_case, hash_index_service) -> None:
        """When hash index already has the hash, return deduplicated status."""
        existing_id = "existing_memory_id"
        hash_index_service.lookup.return_value = existing_id

        result = use_case.execute({
            "content": "file content",
            "hash": "a" * 64,
        })

        assert result.is_ok is True
        assert result.value["status"] == "deduplicated"
        assert result.value["memory_id"] == existing_id
        # Repository should NOT be called when deduplicated
        use_case.memory_repository.save.assert_not_called()
        # Hash index lookup was called with the provided hash
        hash_index_service.lookup.assert_called_once_with("a" * 64)

    # -- Successful storage --

    def test_execute_returns_stored_when_memory_created(self, use_case, memory_repository) -> None:
        """When memory is saved successfully, return stored status with memory_id."""
        memory = a_memory(id="new_memory_id")
        memory_repository.save.return_value = Result.ok(memory)

        result = use_case.execute({
            "id": "new_memory_id",
            "content": "new memory content",
        })

        assert result.is_ok is True
        assert result.value["status"] == "stored"
        assert result.value["memory_id"] == "new_memory_id"

    def test_execute_returns_stored_with_memory_bank(self, use_case, memory_repository) -> None:
        """Stored result should include memory_bank from params."""
        memory = a_memory(id="new_memory_id")
        memory_repository.save.return_value = Result.ok(memory)

        result = use_case.execute({
            "id": "new_memory_id",
            "content": "new memory content",
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        assert result.value["memory_bank"] == "my_bank"

    def test_execute_stores_hash_after_save(self, use_case, memory_repository, hash_index_service) -> None:
        """Hash should be stored in hash index after successful save."""
        memory = a_memory(id="new_memory_id")
        memory_repository.save.return_value = Result.ok(memory)
        hash_index_service.lookup.return_value = None  # No dedup — new hash
        test_hash = "b" * 64

        use_case.execute({
            "id": "new_memory_id",
            "content": "file content",
            "hash": test_hash,
        })

        hash_index_service.store.assert_called_once_with(test_hash, "new_memory_id")

    # -- Repository failure --

    def test_execute_returns_ko_when_repository_save_fails(self, use_case, memory_repository) -> None:
        """When repository save fails, return Result.ko."""
        memory_repository.save.return_value = Result.ko([ErrorWithDetails("SAVE_ERROR", {})])

        result = use_case.execute({
            "id": "new_memory_id",
            "content": "new memory content",
        })

        assert result.is_ko is True
        assert result.errors[0].error_code == "SAVE_ERROR"

    # -- Memory.of failure --

    def test_execute_returns_ko_when_memory_of_fails(self, use_case) -> None:
        """When Memory.of fails validation, return Result.ko."""
        # Memory.of requires id; omitting it should fail
        result = use_case.execute({
            "content": "some content",
        })

        assert result.is_ko is True
