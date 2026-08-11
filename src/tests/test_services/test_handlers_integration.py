"""Integration tests for MCP tool handlers delegating to use cases.

Tests verify that each handler:
1. Instantiates the correct use case with expected dependencies
2. Calls use_case.execute() with the expected parameters
3. Returns Result.value as dict on success
4. Raises ValidationError on Result.ko
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.exceptions import ValidationError
from src.domain.result import ErrorWithDetails, Result


class TestHandleRemember:
    """Test handle_remember delegates to ProcessMemoryUseCase."""

    @pytest.fixture
    def router(self) -> MagicMock:
        router = MagicMock()
        router.get_instance = AsyncMock()
        return router

    @pytest.fixture
    def arguments(self) -> dict:
        return {
            "memory_bank": "default",
            "content": "Remember this",
        }

    async def test_delegates_to_process_memory_use_case(self, router, arguments) -> None:
        """handle_remember should call ProcessMemoryUseCase.execute with arguments."""
        from src.services.tools.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "stored",
            "memory_id": "mem-1",
            "memory_bank": "default",
        })

        with patch(
            "src.services.tools.handlers.ProcessMemoryUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_remember(router, arguments)

        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["content"] == "Remember this"
        assert call_args["memory_bank"] == "default"

    async def test_returns_result_value_as_dict_on_success(self, router, arguments) -> None:
        """handle_remember should return the Result.value dict on success."""
        from src.services.tools.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "stored",
            "memory_id": "mem-1",
            "memory_bank": "default",
        })

        with patch(
            "src.services.tools.handlers.ProcessMemoryUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_remember(router, arguments)

        assert result["status"] == "stored"
        assert result["memory_id"] == "mem-1"
        assert result["memory_bank"] == "default"

    async def test_raises_validation_error_on_result_ko(self, router, arguments) -> None:
        """handle_remember should raise ValidationError when use case returns Result.ko."""
        from src.services.tools.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([
            ErrorWithDetails("CONTENT_REQUIRED", {})
        ])

        with patch(
            "src.services.tools.handlers.ProcessMemoryUseCase",
            return_value=mock_use_case,
        ):
            with pytest.raises(ValidationError):
                await handle_remember(router, arguments)

    async def test_raises_validation_error_when_content_missing(self, router) -> None:
        """handle_remember should raise ValidationError when content is missing."""
        from src.services.tools.handlers import handle_remember

        with pytest.raises(ValidationError):
            await handle_remember(router, {"memory_bank": "default"})


class TestHandleRecall:
    """Test handle_recall delegates to RecallMemoryUseCase."""

    @pytest.fixture
    def router(self) -> MagicMock:
        router = MagicMock()
        router.get_instance = AsyncMock()
        return router

    @pytest.fixture
    def arguments(self) -> dict:
        return {
            "memory_bank": "default",
            "query": "test query",
        }

    async def test_delegates_to_recall_memory_use_case(self, router, arguments) -> None:
        """handle_recall should call RecallMemoryUseCase.execute with arguments."""
        from src.services.tools.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "results": [{"content": "result"}],
            "memory_bank": "default",
        })

        with patch(
            "src.services.tools.handlers.RecallMemoryUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_recall(router, arguments)

        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["query"] == "test query"
        assert call_args["memory_bank"] == "default"

    async def test_returns_result_value_as_dict_on_success(self, router, arguments) -> None:
        """handle_recall should return the Result.value dict on success."""
        from src.services.tools.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "results": [{"content": "result"}],
            "memory_bank": "default",
        })

        with patch(
            "src.services.tools.handlers.RecallMemoryUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_recall(router, arguments)

        assert len(result["results"]) == 1
        assert result["memory_bank"] == "default"

    async def test_raises_validation_error_on_result_ko(self, router, arguments) -> None:
        """handle_recall should raise ValidationError when use case returns Result.ko."""
        from src.services.tools.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([
            ErrorWithDetails("QUERY_REQUIRED", {})
        ])

        with patch(
            "src.services.tools.handlers.RecallMemoryUseCase",
            return_value=mock_use_case,
        ):
            with pytest.raises(ValidationError):
                await handle_recall(router, arguments)


class TestHandleForget:
    """Test handle_forget delegates to ForgetMemoryUseCase."""

    @pytest.fixture
    def router(self) -> MagicMock:
        router = MagicMock()
        router.get_instance = AsyncMock()
        return router

    @pytest.fixture
    def arguments(self) -> dict:
        return {
            "memory_bank": "default",
            "memory_id": "mem-1",
        }

    async def test_delegates_to_forget_memory_use_case(self, router, arguments) -> None:
        """handle_forget should call ForgetMemoryUseCase.execute with arguments."""
        from src.services.tools.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "deleted",
            "memory_bank": "default",
        })

        with patch(
            "src.services.tools.handlers.ForgetMemoryUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_forget(router, arguments)

        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["memory_id"] == "mem-1"
        assert call_args["memory_bank"] == "default"

    async def test_returns_result_value_as_dict_on_success(self, router, arguments) -> None:
        """handle_forget should return the Result.value dict on success."""
        from src.services.tools.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "deleted",
            "memory_bank": "default",
        })

        with patch(
            "src.services.tools.handlers.ForgetMemoryUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_forget(router, arguments)

        assert result["status"] == "deleted"
        assert result["memory_bank"] == "default"

    async def test_raises_validation_error_on_result_ko(self, router, arguments) -> None:
        """handle_forget should raise ValidationError when use case returns Result.ko."""
        from src.services.tools.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([
            ErrorWithDetails("MEMORY_ID_REQUIRED", {})
        ])

        with patch(
            "src.services.tools.handlers.ForgetMemoryUseCase",
            return_value=mock_use_case,
        ):
            with pytest.raises(ValidationError):
                await handle_forget(router, arguments)


class TestHandleUpdate:
    """Test handle_update delegates to UpdateMemoryUseCase."""

    @pytest.fixture
    def router(self) -> MagicMock:
        router = MagicMock()
        router.get_instance = AsyncMock()
        return router

    @pytest.fixture
    def arguments(self) -> dict:
        return {
            "memory_bank": "default",
            "memory_id": "mem-1",
            "content": "updated content",
        }

    async def test_delegates_to_update_memory_use_case(self, router, arguments) -> None:
        """handle_update should call UpdateMemoryUseCase.execute with arguments."""
        from src.services.tools.handlers import handle_update

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "updated",
            "memory_bank": "default",
        })

        with patch(
            "src.services.tools.handlers.UpdateMemoryUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_update(router, arguments)

        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["memory_id"] == "mem-1"
        assert call_args["content"] == "updated content"

    async def test_returns_result_value_as_dict_on_success(self, router, arguments) -> None:
        """handle_update should return the Result.value dict on success."""
        from src.services.tools.handlers import handle_update

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "updated",
            "memory_bank": "default",
        })

        with patch(
            "src.services.tools.handlers.UpdateMemoryUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_update(router, arguments)

        assert result["status"] == "updated"
        assert result["memory_bank"] == "default"

    async def test_raises_validation_error_on_result_ko(self, router, arguments) -> None:
        """handle_update should raise ValidationError when use case returns Result.ko."""
        from src.services.tools.handlers import handle_update

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([
            ErrorWithDetails("MEMORY_ID_REQUIRED", {})
        ])

        with patch(
            "src.services.tools.handlers.UpdateMemoryUseCase",
            return_value=mock_use_case,
        ):
            with pytest.raises(ValidationError):
                await handle_update(router, arguments)


class TestHandleSleep:
    """Test handle_sleep delegates to SleepMemoryUseCase."""

    @pytest.fixture
    def router(self) -> MagicMock:
        router = MagicMock()
        router.get_instance = AsyncMock()
        return router

    @pytest.fixture
    def arguments(self) -> dict:
        return {
            "memory_bank": "default",
        }

    async def test_delegates_to_sleep_memory_use_case(self, router, arguments) -> None:
        """handle_sleep should call SleepMemoryUseCase.execute with arguments."""
        from src.services.tools.handlers import handle_sleep

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "result": {"status": "consolidated"},
            "memory_bank": "default",
        })

        with patch(
            "src.services.tools.handlers.SleepMemoryUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_sleep(router, arguments)

        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["memory_bank"] == "default"

    async def test_returns_result_value_as_dict_on_success(self, router, arguments) -> None:
        """handle_sleep should return the Result.value dict on success."""
        from src.services.tools.handlers import handle_sleep

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "result": {"status": "consolidated"},
            "memory_bank": "default",
        })

        with patch(
            "src.services.tools.handlers.SleepMemoryUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_sleep(router, arguments)

        assert result["memory_bank"] == "default"


class TestHandleListBanks:
    """Test handle_list_banks delegates to ListBanksUseCase."""

    @pytest.fixture
    def router(self) -> MagicMock:
        return MagicMock()

    async def test_delegates_to_list_banks_use_case(self, router) -> None:
        """handle_list_banks should call ListBanksUseCase.execute."""
        from src.services.tools.handlers import handle_list_banks

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "banks": [{"name": "default", "status": "active"}],
        })

        with patch(
            "src.services.tools.handlers.ListBanksUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_list_banks(router, {})

        mock_use_case.execute.assert_called_once()

    async def test_returns_result_value_as_dict_on_success(self, router) -> None:
        """handle_list_banks should return the Result.value dict on success."""
        from src.services.tools.handlers import handle_list_banks

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "banks": [
                {"name": "default", "status": "active"},
                {"name": "ns1", "status": "registered"},
            ],
        })

        with patch(
            "src.services.tools.handlers.ListBanksUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_list_banks(router, {})

        assert len(result["banks"]) == 2
        assert result["banks"][0]["name"] == "default"


class TestHandleRegisterBank:
    """Test handle_register_bank delegates to RegisterBankUseCase."""

    @pytest.fixture
    def router(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def arguments(self) -> dict:
        return {
            "name": "my-bank",
            "description": "A test bank",
        }

    async def test_delegates_to_register_bank_use_case(self, router, arguments) -> None:
        """handle_register_bank should call RegisterBankUseCase.execute with arguments."""
        from src.services.tools.handlers import handle_register_bank

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "registered",
            "name": "my-bank",
        })

        with patch(
            "src.services.tools.handlers.RegisterBankUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_register_bank(router, arguments)

        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["name"] == "my-bank"
        assert call_args["description"] == "A test bank"

    async def test_returns_result_value_as_dict_on_success(self, router, arguments) -> None:
        """handle_register_bank should return the Result.value dict on success."""
        from src.services.tools.handlers import handle_register_bank

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({
            "status": "registered",
            "name": "my-bank",
        })

        with patch(
            "src.services.tools.handlers.RegisterBankUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_register_bank(router, arguments)

        assert result["status"] == "registered"
        assert result["name"] == "my-bank"

    async def test_raises_validation_error_on_result_ko(self, router, arguments) -> None:
        """handle_register_bank should raise ValidationError when use case returns Result.ko."""
        from src.services.tools.handlers import handle_register_bank

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([
            ErrorWithDetails("NAME_REQUIRED", {})
        ])

        with patch(
            "src.services.tools.handlers.RegisterBankUseCase",
            return_value=mock_use_case,
        ):
            with pytest.raises(ValidationError):
                await handle_register_bank(router, arguments)
