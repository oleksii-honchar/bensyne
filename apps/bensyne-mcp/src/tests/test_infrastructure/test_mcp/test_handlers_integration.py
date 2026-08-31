"""Integration tests for MCP tool handlers delegating to use cases.

Tests verify that each handler:
1. Instantiates the correct use case with expected dependencies
2. Calls use_case.execute() with the expected parameters
3. Returns Result.value as dict on success
4. Raises ValidationError on Result.ko
"""

from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from src.domain.exceptions import ValidationError
from src.infrastructure.bank.router import MemoryBankRouter
from src.utils.result import ErrorWithDetails, Result


class TestHandleRemember:
    """Test handle_remember delegates to RememberMemoryUseCase."""

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

    async def test_delegates_to_remember_memory_use_case(self, router, arguments) -> None:
        """handle_remember should call RememberMemoryUseCase.execute with arguments."""
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem-1",
                "memory_bank": "default",
            }
        )

        mock_container = MagicMock()
        mock_container.remember_memory_use_case.return_value = mock_use_case
        result = await handle_remember(router, arguments, container=mock_container)

        mock_container.remember_memory_use_case.assert_called_once()
        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["content"] == "Remember this"
        assert call_args["memory_bank"] == "default"

    async def test_returns_result_value_as_dict_on_success(self, router, arguments) -> None:
        """handle_remember should return the Result.value dict on success."""
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem-1",
                "memory_bank": "default",
            }
        )

        mock_container = MagicMock()
        mock_container.remember_memory_use_case.return_value = mock_use_case
        result = await handle_remember(router, arguments, container=mock_container)

        assert result["status"] == "stored"
        assert result["memory_id"] == "mem-1"
        assert result["memory_bank"] == "default"

    async def test_raises_validation_error_on_result_ko(self, router, arguments) -> None:
        """handle_remember should raise ValidationError when use case returns Result.ko."""
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([ErrorWithDetails("CONTENT_REQUIRED", {})])

        mock_container = MagicMock()
        mock_container.remember_memory_use_case.return_value = mock_use_case
        with pytest.raises(ValidationError):
            await handle_remember(router, arguments, container=mock_container)

    async def test_raises_validation_error_when_content_missing(self, router) -> None:
        """handle_remember should raise ValidationError when content is missing."""
        from src.infrastructure.mcp.handlers import handle_remember

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
        from src.infrastructure.mcp.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "results": [{"content": "result"}],
                "memory_bank": "default",
            }
        )

        mock_container = MagicMock()
        mock_container.recall_memory_use_case.return_value = mock_use_case
        result = await handle_recall(router, arguments, container=mock_container)

        mock_container.recall_memory_use_case.assert_called_once()
        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["query"] == "test query"
        assert call_args["memory_bank"] == "default"

    async def test_returns_result_value_as_dict_on_success(self, router, arguments) -> None:
        """handle_recall should return the Result.value dict on success."""
        from src.infrastructure.mcp.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "results": [{"content": "result"}],
                "memory_bank": "default",
            }
        )

        mock_container = MagicMock()
        mock_container.recall_memory_use_case.return_value = mock_use_case
        result = await handle_recall(router, arguments, container=mock_container)

        assert len(result["results"]) == 1
        assert result["memory_bank"] == "default"

    async def test_raises_validation_error_on_result_ko(self, router, arguments) -> None:
        """handle_recall should raise ValidationError when use case returns Result.ko."""
        from src.infrastructure.mcp.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([ErrorWithDetails("QUERY_REQUIRED", {})])

        mock_container = MagicMock()
        mock_container.recall_memory_use_case.return_value = mock_use_case
        with pytest.raises(ValidationError):
            await handle_recall(router, arguments, container=mock_container)


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
        from src.infrastructure.mcp.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "deleted",
                "memory_bank": "default",
            }
        )

        mock_container = MagicMock()
        mock_container.forget_memory_use_case.return_value = mock_use_case
        result = await handle_forget(router, arguments, container=mock_container)

        mock_container.forget_memory_use_case.assert_called_once()
        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["memory_id"] == "mem-1"
        assert call_args["memory_bank"] == "default"

    async def test_returns_result_value_as_dict_on_success(self, router, arguments) -> None:
        """handle_forget should return the Result.value dict on success."""
        from src.infrastructure.mcp.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "deleted",
                "memory_bank": "default",
            }
        )

        mock_container = MagicMock()
        mock_container.forget_memory_use_case.return_value = mock_use_case
        result = await handle_forget(router, arguments, container=mock_container)

        assert result["status"] == "deleted"
        assert result["memory_bank"] == "default"

    async def test_raises_validation_error_on_result_ko(self, router, arguments) -> None:
        """handle_forget should raise ValidationError when use case returns Result.ko."""
        from src.infrastructure.mcp.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([ErrorWithDetails("MEMORY_ID_REQUIRED", {})])

        mock_container = MagicMock()
        mock_container.forget_memory_use_case.return_value = mock_use_case
        with pytest.raises(ValidationError):
            await handle_forget(router, arguments, container=mock_container)


class TestHandleForgetFile:
    """Test handle_forget_file delegates to ForgetFileUseCase via the DI container."""

    @pytest.fixture
    def router(self) -> MagicMock:
        router = MagicMock()
        router.get_instance = AsyncMock()
        return router

    @pytest.fixture
    def arguments(self) -> dict:
        return {
            "memory_bank": "default",
            "file_path": "/tmp/tool-responses/x.json",
        }

    async def test_delegates_to_forget_file_use_case(self, router, arguments) -> None:
        """handle_forget_file should call the container's forget_file_use_case."""
        from src.infrastructure.mcp.handlers import handle_forget_file

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {"status": "forgotten", "memory_bank": "default"}
        )

        mock_container = MagicMock()
        mock_container.forget_file_use_case.return_value = mock_use_case
        result = await handle_forget_file(router, arguments, container=mock_container)

        mock_container.forget_file_use_case.assert_called_once()
        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["file_path"] == "/tmp/tool-responses/x.json"
        assert call_args["memory_bank"] == "default"
        # The factory receives the per-bank mnemosyne client + memory bank.
        factory_kwargs = mock_container.forget_file_use_case.call_args.kwargs
        assert factory_kwargs["mnemosyne_client"] is router.get_instance.return_value
        assert factory_kwargs["memory_bank"] == "default"

    async def test_returns_result_value_as_dict_on_success(self, router, arguments) -> None:
        """handle_forget_file should return the Result.value dict on success."""
        from src.infrastructure.mcp.handlers import handle_forget_file

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "forgotten",
                "memory_bank": "default",
                "file_id": "f1",
            }
        )

        mock_container = MagicMock()
        mock_container.forget_file_use_case.return_value = mock_use_case
        result = await handle_forget_file(router, arguments, container=mock_container)

        assert result["status"] == "forgotten"
        assert result["file_id"] == "f1"

    async def test_raises_validation_error_on_result_ko(self, router, arguments) -> None:
        """handle_forget_file should raise ValidationError when use case returns Result.ko."""
        from src.infrastructure.mcp.handlers import handle_forget_file

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko(
            [ErrorWithDetails("FILE_NOT_FOUND", {})]
        )

        mock_container = MagicMock()
        mock_container.forget_file_use_case.return_value = mock_use_case
        with pytest.raises(ValidationError):
            await handle_forget_file(router, arguments, container=mock_container)

    async def test_raises_validation_error_without_file_path(self, router) -> None:
        """handle_forget_file should reject arguments without file_path."""
        from src.infrastructure.mcp.handlers import handle_forget_file

        with pytest.raises(ValidationError, match="file_path is required"):
            await handle_forget_file(
                router, {"memory_bank": "default"}, container=MagicMock()
            )

    async def test_raises_validation_error_without_memory_bank(self, router) -> None:
        """handle_forget_file should reject arguments without memory_bank."""
        from src.infrastructure.mcp.handlers import handle_forget_file

        with pytest.raises(ValidationError, match="memory_bank parameter is required"):
            await handle_forget_file(
                router, {"file_path": "/x"}, container=MagicMock()
            )


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
        from src.infrastructure.mcp.handlers import handle_update

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "updated",
                "memory_bank": "default",
            }
        )

        with patch(
            "src.infrastructure.mcp.handlers.UpdateMemoryUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_update(router, arguments)

        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["memory_id"] == "mem-1"
        assert call_args["content"] == "updated content"

    async def test_returns_result_value_as_dict_on_success(self, router, arguments) -> None:
        """handle_update should return the Result.value dict on success."""
        from src.infrastructure.mcp.handlers import handle_update

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "updated",
                "memory_bank": "default",
            }
        )

        with patch(
            "src.infrastructure.mcp.handlers.UpdateMemoryUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_update(router, arguments)

        assert result["status"] == "updated"
        assert result["memory_bank"] == "default"

    async def test_raises_validation_error_on_result_ko(self, router, arguments) -> None:
        """handle_update should raise ValidationError when use case returns Result.ko."""
        from src.infrastructure.mcp.handlers import handle_update

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([ErrorWithDetails("MEMORY_ID_REQUIRED", {})])

        with patch(
            "src.infrastructure.mcp.handlers.UpdateMemoryUseCase",
            return_value=mock_use_case,
        ):
            with pytest.raises(ValidationError):
                await handle_update(router, arguments)


class TestHandleSleep:
    """Test handle_sleep delegates to SleepUseCase."""

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

    async def test_delegates_to_sleep_use_case(self, router, arguments) -> None:
        """handle_sleep should call SleepUseCase.execute with arguments."""
        from src.infrastructure.mcp.handlers import handle_sleep

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "result": {"status": "consolidated"},
                "memory_bank": "default",
            }
        )

        with patch(
            "src.infrastructure.mcp.handlers.SleepUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_sleep(router, arguments)

        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["memory_bank"] == "default"

    async def test_returns_result_value_as_dict_on_success(self, router, arguments) -> None:
        """handle_sleep should return the Result.value dict on success."""
        from src.infrastructure.mcp.handlers import handle_sleep

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "result": {"status": "consolidated"},
                "memory_bank": "default",
            }
        )

        with patch(
            "src.infrastructure.mcp.handlers.SleepUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_sleep(router, arguments)

        assert result["memory_bank"] == "default"


class TestHandleListBanks:
    """Test handle_list_banks delegates to ListBanksUseCase (service-backed)."""

    @pytest.fixture
    def router(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def memory_bank_service(self) -> MagicMock:
        return MagicMock()

    async def test_delegates_to_list_banks_use_case(self, router, memory_bank_service) -> None:
        """handle_list_banks should call ListBanksUseCase.execute."""
        from src.infrastructure.mcp.handlers import handle_list_banks

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "banks": [{"name": "default", "status": "active"}],
            }
        )

        with patch(
            "src.infrastructure.mcp.handlers.ListBanksUseCase",
            return_value=mock_use_case,
        ) as mock_cls:
            result = await handle_list_banks(router, memory_bank_service, {})

        mock_cls.assert_called_once_with(
            memory_bank_service=memory_bank_service,
            router=router,
            logger=ANY,
        )
        mock_use_case.execute.assert_called_once()

    async def test_returns_result_value_as_dict_on_success(self, router, memory_bank_service) -> None:
        """handle_list_banks should return the Result.value dict on success."""
        from src.infrastructure.mcp.handlers import handle_list_banks

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "banks": [
                    {"name": "default", "status": "active"},
                    {"name": "ns1", "status": "registered"},
                ],
            }
        )

        with patch(
            "src.infrastructure.mcp.handlers.ListBanksUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_list_banks(router, memory_bank_service, {})

        assert len(result["banks"]) == 2
        assert result["banks"][0]["name"] == "default"


class TestHandleRegisterBank:
    """Test handle_register_bank delegates to RegisterBankUseCase (service-backed)."""

    @pytest.fixture
    def router(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def memory_bank_service(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def arguments(self) -> dict:
        return {
            "name": "my-bank",
            "description": "A test bank",
        }

    async def test_delegates_to_register_bank_use_case(self, router, memory_bank_service, arguments) -> None:
        """handle_register_bank should call RegisterBankUseCase.execute with arguments."""
        from src.infrastructure.mcp.handlers import handle_register_bank

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "registered",
                "name": "my-bank",
            }
        )

        with patch(
            "src.infrastructure.mcp.handlers.RegisterBankUseCase",
            return_value=mock_use_case,
        ) as mock_cls:
            result = await handle_register_bank(router, memory_bank_service, arguments)

        mock_cls.assert_called_once_with(
            memory_bank_service=memory_bank_service,
            logger=ANY,
        )
        mock_use_case.execute.assert_called_once()
        call_args = mock_use_case.execute.call_args[0][0]
        assert call_args["name"] == "my-bank"
        assert call_args["description"] == "A test bank"

    async def test_returns_result_value_as_dict_on_success(self, router, memory_bank_service, arguments) -> None:
        """handle_register_bank should return the Result.value dict on success."""
        from src.infrastructure.mcp.handlers import handle_register_bank

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "registered",
                "name": "my-bank",
            }
        )

        with patch(
            "src.infrastructure.mcp.handlers.RegisterBankUseCase",
            return_value=mock_use_case,
        ):
            result = await handle_register_bank(router, memory_bank_service, arguments)

        assert result["status"] == "registered"
        assert result["name"] == "my-bank"

    async def test_raises_validation_error_on_result_ko(self, router, memory_bank_service, arguments) -> None:
        """handle_register_bank should raise ValidationError when use case returns Result.ko."""
        from src.infrastructure.mcp.handlers import handle_register_bank

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([ErrorWithDetails("NAME_REQUIRED", {})])

        with patch(
            "src.infrastructure.mcp.handlers.RegisterBankUseCase",
            return_value=mock_use_case,
        ):
            with pytest.raises(ValidationError):
                await handle_register_bank(router, memory_bank_service, arguments)


class TestHandleExpandFileRelations:
    """Test handle_expand_file_relations delegates to ExpandFileRelationsUseCase."""

    async def test_passes_callable_get_not_client_object(self, tmp_path) -> None:
        """Handler must pass the bound `get` method (callable), not the client object.

        Regression guard: `FileMetadata.compose_content/compose_fetch` call
        `mnemosyne_client(chunk.memory_id)`, so the use case receives a
        callable (memory_id -> memory dict), not the raw MnemosyneClient.
        Passing the object caused a live `INTERNAL_ERROR`:
        `'MnemosyneClient' object is not callable`.
        """
        from src.infrastructure.mcp.handlers import handle_expand_file_relations

        router = MagicMock()
        router.get_instance = AsyncMock()
        router.config.data_dir = str(tmp_path)
        instance = MagicMock(name="client")
        router.get_instance.return_value = instance

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "file_id": "file_x",
                "memory_bank": "tmp-obsidian",
                "relations": [],
            }
        )
        mock_container = MagicMock()
        mock_container.expand_file_relations_use_case.return_value = mock_use_case

        arguments = {"memory_bank": "tmp-obsidian", "file_id": "file_x"}
        await handle_expand_file_relations(router, arguments, container=mock_container)

        mock_container.expand_file_relations_use_case.assert_called_once()
        # The wiring must pass the callable bound method, not the client object.
        assert (
            mock_container.expand_file_relations_use_case.call_args.kwargs["mnemosyne_client"]
            is instance.get
        )


class TestBankDirResolution:
    """All 6 bank_dir sites resolve via router.get_bank_dir → <data_dir>/banks/<bank>/.

    Task 7 (S2/S13): handlers must NOT build `Path(data_dir) / memory_bank` inline
    (the old v1 layout). With a real router whose config.data_dir = tmp, every
    file-metadata handler must construct its bundle at `<tmp>/banks/<bank>/` and
    never at `<tmp>/<bank>/` or the data root.
    """

    @pytest.fixture
    def router(self, tmp_path) -> MemoryBankRouter:
        from src.domain.config_models import InstancePoolConfig
        from src.infrastructure.bank.router import MemoryBankRouter
        from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient

        config = InstancePoolConfig(
            max_instances=5,
            eviction_timeout=300,
            data_dir=str(tmp_path),
            default_bank="default",
        )

        def _mock_client(memory_bank: str) -> MagicMock:
            client = MagicMock(spec=MnemosyneClient)
            client.memory_bank = memory_bank
            return client

        with patch.object(
            MemoryBankRouter, "_create_instance", side_effect=_mock_client
        ):
            return MemoryBankRouter(config=config)

    def _assert_bundle_bank_dir(self, container: MagicMock, tmp_path, memory_bank: str = "default") -> None:
        """Assert the bundle was built at <tmp>/banks/<bank>/ — not <tmp>/<bank>/."""
        bundle_call = container.file_metadata_bundle.call_args
        assert bundle_call is not None, "file_metadata_bundle was not called"
        bank_dir = bundle_call.kwargs["bank_dir"]
        assert bank_dir == tmp_path / "banks" / memory_bank
        # Old-layout guards: no <tmp>/<bank>/ and no bundle at the data root.
        assert not (tmp_path / memory_bank).exists()

    async def test_handle_remember_bundle_at_banks_dir(self, router, tmp_path) -> None:
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({"status": "stored"})
        container = MagicMock()
        container.remember_memory_use_case.return_value = mock_use_case

        await handle_remember(
            router,
            {"memory_bank": "default", "content": "hello"},
            container=container,
        )

        self._assert_bundle_bank_dir(container, tmp_path)

    async def test_handle_recall_bundle_at_banks_dir(self, router, tmp_path) -> None:
        from src.infrastructure.mcp.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({"results": []})
        container = MagicMock()
        container.recall_memory_use_case.return_value = mock_use_case

        await handle_recall(
            router,
            {"memory_bank": "default", "query": "q"},
            container=container,
        )

        self._assert_bundle_bank_dir(container, tmp_path)

    async def test_handle_forget_bundle_at_banks_dir(self, router, tmp_path) -> None:
        from src.infrastructure.mcp.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({"status": "deleted"})
        container = MagicMock()
        container.forget_memory_use_case.return_value = mock_use_case

        await handle_forget(
            router,
            {"memory_bank": "default", "memory_id": "mem-1"},
            container=container,
        )

        self._assert_bundle_bank_dir(container, tmp_path)

    async def test_handle_search_files_bundle_at_banks_dir(self, router, tmp_path) -> None:
        from src.infrastructure.mcp.handlers import handle_search_files

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({"results": []})
        container = MagicMock()
        container.search_files_use_case.return_value = mock_use_case

        await handle_search_files(
            router,
            {"memory_bank": "default", "query": "q"},
            container=container,
        )

        self._assert_bundle_bank_dir(container, tmp_path)

    async def test_handle_expand_file_relations_bundle_at_banks_dir(self, router, tmp_path) -> None:
        from src.infrastructure.mcp.handlers import handle_expand_file_relations

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({"relations": []})
        container = MagicMock()
        container.expand_file_relations_use_case.return_value = mock_use_case

        await handle_expand_file_relations(
            router,
            {"memory_bank": "default", "file_id": "file-1"},
            container=container,
        )

        self._assert_bundle_bank_dir(container, tmp_path)

    async def test_handle_fetch_file_bundle_at_banks_dir(self, router, tmp_path) -> None:
        from src.infrastructure.mcp.handlers import handle_fetch_file

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({"file_id": "file-1"})
        container = MagicMock()
        container.fetch_file_use_case.return_value = mock_use_case

        await handle_fetch_file(
            router,
            {"memory_bank": "default", "file_id": "file-1"},
            container=container,
        )

        self._assert_bundle_bank_dir(container, tmp_path)

    async def test_handle_fetch_file_passes_path_handle_through(self, router, tmp_path) -> None:
        from src.infrastructure.mcp.handlers import handle_fetch_file

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok({"file_id": "file-1"})
        container = MagicMock()
        container.fetch_file_use_case.return_value = mock_use_case

        await handle_fetch_file(
            router,
            {"memory_bank": "default", "path_handle": "agent-a/00-entry.md"},
            container=container,
        )
        mock_use_case.execute.assert_called_once()
        executed_params = mock_use_case.execute.call_args[0][0]
        assert executed_params["path_handle"] == "agent-a/00-entry.md"
        assert "file_id" not in executed_params
        # Handler-level gate is gone: no file_id but a path_handle passes
        # straight to the use case (which owns FILE_REF_REQUIRED validation).
        self._assert_bundle_bank_dir(container, tmp_path)
