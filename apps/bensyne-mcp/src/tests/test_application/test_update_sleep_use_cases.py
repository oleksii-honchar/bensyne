"""Unit tests for UpdateMemoryUseCase and SleepUseCase."""

from unittest.mock import MagicMock

import pytest

from src.application.use_cases.update_memory_use_case import UpdateMemoryUseCase
from src.application.use_cases.sleep_use_case import SleepUseCase
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock


class TestUpdateMemoryUseCase:
    """Test UpdateMemoryUseCase orchestration logic."""

    @pytest.fixture
    def mnemosyne_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(self, mnemosyne_client, logger) -> UpdateMemoryUseCase:
        return UpdateMemoryUseCase(
            mnemosyne_client=mnemosyne_client,
            logger=logger,
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

    # -- Successful update --

    def test_execute_returns_updated_when_update_succeeds(self, use_case, mnemosyne_client) -> None:
        """When update succeeds, return Result.ok with status and memory_bank."""
        mnemosyne_client.update.return_value = Result.ok(True)

        result = use_case.execute({
            "memory_id": "mem_123",
            "content": "new content",
            "importance": 0.9,
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        assert result.value["status"] == "updated"
        assert result.value["memory_bank"] == "my_bank"
        mnemosyne_client.update.assert_called_once_with(
            "mem_123", content="new content", importance=0.9
        )

    def test_execute_passes_only_content_when_importance_not_provided(self, use_case, mnemosyne_client) -> None:
        """When only content is provided, importance should be None."""
        mnemosyne_client.update.return_value = Result.ok(True)

        result = use_case.execute({
            "memory_id": "mem_123",
            "content": "new content",
        })

        assert result.is_ok is True
        mnemosyne_client.update.assert_called_once_with(
            "mem_123", content="new content", importance=None
        )

    def test_execute_passes_only_importance_when_content_not_provided(self, use_case, mnemosyne_client) -> None:
        """When only importance is provided, content should be None."""
        mnemosyne_client.update.return_value = Result.ok(True)

        result = use_case.execute({
            "memory_id": "mem_123",
            "importance": 0.5,
        })

        assert result.is_ok is True
        mnemosyne_client.update.assert_called_once_with(
            "mem_123", content=None, importance=0.5
        )

    def test_execute_returns_not_found_when_memory_not_found(self, use_case, mnemosyne_client) -> None:
        """When memory is not found, return status not_found."""
        mnemosyne_client.update.return_value = Result.ok(False)

        result = use_case.execute({
            "memory_id": "mem_999",
            "content": "new content",
        })

        assert result.is_ok is True
        assert result.value["status"] == "not_found"

    def test_execute_uses_default_memory_bank(self, use_case, mnemosyne_client) -> None:
        """When no memory_bank is provided, use default."""
        mnemosyne_client.update.return_value = Result.ok(True)

        result = use_case.execute({
            "memory_id": "mem_123",
            "content": "new content",
        })

        assert result.is_ok is True
        assert result.value["memory_bank"] == "default"


class TestSleepUseCase:
    """Test SleepUseCase orchestration logic."""

    @pytest.fixture
    def mnemosyne_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(self, mnemosyne_client, logger) -> SleepUseCase:
        return SleepUseCase(
            mnemosyne_client=mnemosyne_client,
            logger=logger,
        )

    # -- Delegation --

    def test_execute_delegates_to_mnemosyne_client_sleep(self, use_case, mnemosyne_client) -> None:
        """SleepUseCase should delegate to MnemosyneClient.sleep()."""
        sleep_result = {"status": "consolidated", "merged": 5}
        mnemosyne_client.sleep.return_value = Result.ok(sleep_result)

        result = use_case.execute({
            "memory_bank": "my_bank",
        })

        assert result.is_ok is True
        mnemosyne_client.sleep.assert_called_once()
        assert result.value["result"] == sleep_result
        assert result.value["memory_bank"] == "my_bank"

    def test_execute_returns_merged_result(self, use_case, mnemosyne_client) -> None:
        """Result should contain the merged result dict from sleep()."""
        sleep_result = {"status": "consolidated", "merged": 3, "discarded": 1}
        mnemosyne_client.sleep.return_value = Result.ok(sleep_result)

        result = use_case.execute({
            "memory_bank": "default",
        })

        assert result.is_ok is True
        assert result.value["result"] == sleep_result
        assert result.value["memory_bank"] == "default"
