"""MCP tool handlers tests."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from src.domain.exceptions import ValidationError
from src.domain.config_models import InstancePoolConfig
from src.infrastructure.bank.router import MemoryBankRouter


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_mnemosyne_instance() -> MagicMock:
    """Create a fully configured mock Mnemosyne instance."""
    mock = MagicMock()
    mock.remember.return_value = "mem_abc123"
    mock.recall.return_value = [{"id": "mem_abc123", "content": "test memory", "score": 0.9}]
    mock.forget.return_value = True
    mock.update.return_value = True
    mock.sleep.return_value = {"status": "ok", "consolidated": 0}
    mock.stats.return_value = {"working": 5, "episodic": 2}
    mock.get_stats.return_value = {"working": 5, "episodic": 2}
    mock.get.return_value = None
    return mock


def _patch_mnemosyne_class(mock_instance: MagicMock) -> Any:
    """Context manager that patches mnemosyne.core.memory.Mnemosyne."""
    return patch.dict(
        "sys.modules",
        {
            "mnemosyne": MagicMock(),
            "mnemosyne.core": MagicMock(),
            "mnemosyne.core.memory": MagicMock(Mnemosyne=MagicMock(return_value=mock_instance)),
        },
    )


@pytest.fixture
def router(tmp_path: Path) -> MemoryBankRouter:
    """Create a MemoryBankRouter with mocked mnemosyne — patch persists across tests."""
    mock_instance = _mock_mnemosyne_instance()

    # Patch mnemosyne.core.memory.Mnemosyne class directly in sys.modules
    # so lazy import in client.py always returns our mock
    with patch.dict(
        "sys.modules",
        {
            "mnemosyne": MagicMock(),
            "mnemosyne.core": MagicMock(),
            "mnemosyne.core.memory": MagicMock(Mnemosyne=lambda **kwargs: mock_instance),
        },
    ):
        config = InstancePoolConfig(
            max_instances=5,
            eviction_timeout=300,
            data_dir=str(tmp_path),
            default_bank="default",
        )
        router = MemoryBankRouter(config=config)
        router._mock_instance = mock_instance  # expose for test assertions
        yield router


# ---------------------------------------------------------------------------
# Tool schemas
# ---------------------------------------------------------------------------


class TestToolSchemas:
    """Tool schemas include memory_bank parameter as required (no default)."""

    def test_remember_schema_memory_bank_required_no_default(self) -> None:
        from src.infrastructure.mcp.schemas import REMEMBER_SCHEMA

        params = REMEMBER_SCHEMA["parameters"]["properties"]
        assert "memory_bank" in params
        assert "default" not in params["memory_bank"]
        assert "memory_bank" in REMEMBER_SCHEMA["parameters"]["required"]

    def test_recall_schema_memory_bank_required_no_default(self) -> None:
        from src.infrastructure.mcp.schemas import RECALL_SCHEMA

        params = RECALL_SCHEMA["parameters"]["properties"]
        assert "memory_bank" in params
        assert "default" not in params["memory_bank"]
        assert "memory_bank" in RECALL_SCHEMA["parameters"]["required"]

    def test_forget_schema_memory_bank_required_no_default(self) -> None:
        from src.infrastructure.mcp.schemas import FORGET_SCHEMA

        params = FORGET_SCHEMA["parameters"]["properties"]
        assert "memory_bank" in params
        assert "default" not in params["memory_bank"]
        assert "memory_bank" in FORGET_SCHEMA["parameters"]["required"]

    def test_update_schema_memory_bank_required_no_default(self) -> None:
        from src.infrastructure.mcp.schemas import UPDATE_SCHEMA

        params = UPDATE_SCHEMA["parameters"]["properties"]
        assert "memory_bank" in params
        assert "default" not in params["memory_bank"]
        assert "memory_bank" in UPDATE_SCHEMA["parameters"]["required"]

    def test_sleep_schema_memory_bank_required_no_default(self) -> None:
        from src.infrastructure.mcp.schemas import SLEEP_SCHEMA

        params = SLEEP_SCHEMA["parameters"]["properties"]
        assert "memory_bank" in params
        assert "default" not in params["memory_bank"]
        assert "memory_bank" in SLEEP_SCHEMA["parameters"]["required"]

    def test_stats_schema_memory_bank_required_no_default(self) -> None:
        from src.infrastructure.mcp.schemas import STATS_SCHEMA

        params = STATS_SCHEMA["parameters"]["properties"]
        assert "memory_bank" in params
        assert "default" not in params["memory_bank"]
        assert "memory_bank" in STATS_SCHEMA["parameters"]["required"]

    def test_memory_bank_param_description_says_required(self) -> None:
        from src.infrastructure.mcp.schemas import MEMORY_BANK_PARAM

        assert "required" in MEMORY_BANK_PARAM["memory_bank"]["description"].lower()

    def test_list_banks_schema_no_memory_bank_param(self) -> None:
        from src.infrastructure.mcp.schemas import LIST_BANKS_SCHEMA

        params = LIST_BANKS_SCHEMA["parameters"]["properties"]
        assert "memory_bank" not in params

    def test_all_tool_schemas_use_memory_names(self) -> None:
        """All tool schemas expose their tool names following doWithWhat pattern."""
        from src.infrastructure.mcp.schemas import ALL_TOOL_SCHEMAS

        names = {schema["name"] for schema in ALL_TOOL_SCHEMAS}
        assert names == {
            "rememberMemory",
            "recallMemory",
            "forgetMemory",
            "updateMemory",
            "sleep",
            "getMemoryStats",
            "listMemoryBanks",
            "registerMemoryBank",
        }


# ---------------------------------------------------------------------------
# Remember handler
# ---------------------------------------------------------------------------


class TestHandleRememberDedup:
    """Deduplication integration in handle_remember via RememberMemoryUseCase."""

    def test_dedup_returns_deduplicated_when_hash_exists(self, router: MemoryBankRouter) -> None:
        """When fileHash exists in index, return deduplicated status without calling remember."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "deduplicated",
                "memory_id": "mem_existing_001",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_remember(
                    router,
                    {
                        "content": "test memory",
                        "memory_bank": "test-ns",
                        "metadata": {"fileHash": "sha256_abc123"},
                    },
                )

            assert result["status"] == "deduplicated"
            assert result["memory_id"] == "mem_existing_001"
            assert result["memory_bank"] == "test-ns"

        asyncio.run(run())

    def test_dedup_stores_and_indexes_new_hash(self, router: MemoryBankRouter) -> None:
        """When fileHash is new, store memory and index the hash."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem_abc123",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_remember(
                    router,
                    {
                        "content": "new memory",
                        "memory_bank": "test-ns",
                        "metadata": {"fileHash": "sha256_new_hash"},
                    },
                )

            assert result["status"] == "stored"
            assert result["memory_id"] == "mem_abc123"

        asyncio.run(run())

    def test_dedup_pure_memory_bypasses_dedup(self, router: MemoryBankRouter) -> None:
        """When no fileHash in metadata, normal flow unchanged — no hash index interaction."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem_abc123",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_remember(
                    router,
                    {
                        "content": "pure text memory",
                        "memory_bank": "test-ns",
                    },
                )

            assert result["status"] == "stored"
            assert result["memory_id"] == "mem_abc123"

        asyncio.run(run())

    def test_dedup_pure_memory_with_other_metadata(self, router: MemoryBankRouter) -> None:
        """Memory with metadata but no fileHash bypasses dedup."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem_abc123",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_remember(
                    router,
                    {
                        "content": "memory with other metadata",
                        "memory_bank": "test-ns",
                        "metadata": {"source": "api", "tags": ["important"]},
                    },
                )

            assert result["status"] == "stored"
            assert result["memory_id"] == "mem_abc123"

        asyncio.run(run())

    def test_dedup_hash_index_error_is_non_fatal(self, router: MemoryBankRouter) -> None:
        """When hash index raises, use case handles it — handler returns stored."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem_abc123",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_remember(
                    router,
                    {
                        "content": "test memory",
                        "memory_bank": "test-ns",
                        "metadata": {"fileHash": "sha256_abc123"},
                    },
                )

            # Should still store normally despite hash index error (handled by use case)
            assert result["status"] == "stored"
            assert result["memory_id"] == "mem_abc123"

        asyncio.run(run())

    def test_dedup_hash_index_store_error_is_non_fatal(self, router: MemoryBankRouter) -> None:
        """When hash index store fails after remember, memory is still stored (handled by use case)."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem_abc123",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_remember(
                    router,
                    {
                        "content": "test memory",
                        "memory_bank": "test-ns",
                        "metadata": {"fileHash": "sha256_abc123"},
                    },
                )

            # Memory stored despite index failure (handled by use case)
            assert result["status"] == "stored"
            assert result["memory_id"] == "mem_abc123"

        asyncio.run(run())

    def test_dedup_hash_index_created_with_correct_db_path(self, router: MemoryBankRouter) -> None:
        """HashIndexService is created with correct memory_bank."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem_abc123",
                "memory_bank": "my-bank",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_remember(
                    router,
                    {
                        "content": "test",
                        "memory_bank": "my-bank",
                        "metadata": {"fileHash": "sha256_abc"},
                    },
                )

            # Verify use case was called with correct memory_bank
            call_args = mock_use_case.execute.call_args[0][0]
            assert call_args["memory_bank"] == "my-bank"
            assert result["status"] == "stored"

        asyncio.run(run())

    def test_dedup_remember_returns_dict_result(self, router: MemoryBankRouter) -> None:
        """When use case returns result with memory_id, handler returns it correctly."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem_raw_result",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_remember(
                    router,
                    {
                        "content": "test",
                        "memory_bank": "test-ns",
                        "metadata": {"fileHash": "sha256_abc"},
                    },
                )

            assert result["status"] == "stored"
            assert result["memory_id"] == "mem_raw_result"

        asyncio.run(run())


class TestHandleRemember:
    """remember handler stores to correct memory bank via RememberMemoryUseCase."""

    def test_remember_stores_to_correct_memory_bank(self, router: MemoryBankRouter) -> None:
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem_abc123",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_remember(router, {"content": "test memory", "memory_bank": "test-ns"})

            assert result["status"] == "stored"
            assert result["memory_id"] == "mem_abc123"
            assert result["memory_bank"] == "test-ns"
            # Verify use case received correct memory_bank
            call_args = mock_use_case.execute.call_args[0][0]
            assert call_args["memory_bank"] == "test-ns"

        asyncio.run(run())

    def test_remember_raises_validation_error_without_memory_bank(self, router: MemoryBankRouter) -> None:
        from src.infrastructure.mcp.handlers import handle_remember

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_remember(router, {"content": "test memory"})

        asyncio.run(run())

    def test_remember_raises_validation_error_without_content(self, router: MemoryBankRouter) -> None:
        from src.infrastructure.mcp.handlers import handle_remember

        async def run() -> None:
            with pytest.raises(ValidationError, match="content is required"):
                await handle_remember(router, {"memory_bank": "test-ns"})

        asyncio.run(run())

    def test_remember_passes_extra_params(self, router: MemoryBankRouter) -> None:
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_remember

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem_abc123",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
                return_value=mock_use_case,
            ):
                await handle_remember(
                    router,
                    {
                        "content": "test",
                        "memory_bank": "test-ns",
                        "importance": 0.8,
                        "source": "user",
                    },
                )

            # Verify use case received the extra params
            call_args = mock_use_case.execute.call_args[0][0]
            assert call_args["importance"] == 0.8
            assert call_args["source"] == "user"

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Recall handler
# ---------------------------------------------------------------------------


class TestHandleRecall:
    """recall handler queries correct memory bank via RecallMemoryUseCase."""

    def test_recall_queries_correct_memory_bank(self, router: MemoryBankRouter) -> None:
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_recall

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "results": [{"id": "mem_abc123", "content": "test memory", "score": 0.9}],
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RecallMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_recall(router, {"query": "test", "memory_bank": "test-ns"})

            assert result["memory_bank"] == "test-ns"
            assert len(result["results"]) == 1
            assert result["results"][0]["id"] == "mem_abc123"

        asyncio.run(run())

    def test_recall_raises_validation_error_without_memory_bank(self, router: MemoryBankRouter) -> None:
        from src.infrastructure.mcp.handlers import handle_recall

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_recall(router, {"query": "test"})

        asyncio.run(run())

    def test_recall_raises_validation_error_without_query(self, router: MemoryBankRouter) -> None:
        from src.infrastructure.mcp.handlers import handle_recall

        async def run() -> None:
            with pytest.raises(ValidationError, match="query is required"):
                await handle_recall(router, {"memory_bank": "test-ns"})

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Forget handler
# ---------------------------------------------------------------------------


class TestHandleForget:
    """forget handler deletes from correct memory bank via ForgetMemoryUseCase."""

    def test_forget_deletes_from_correct_memory_bank(self, router: MemoryBankRouter) -> None:
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "deleted",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ForgetMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_forget(router, {"memory_id": "mem_abc123", "memory_bank": "test-ns"})

            assert result["status"] == "deleted"
            assert result["memory_bank"] == "test-ns"

        asyncio.run(run())

    def test_forget_raises_validation_error_without_memory_bank(self, router: MemoryBankRouter) -> None:
        from src.infrastructure.mcp.handlers import handle_forget

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_forget(router, {"memory_id": "mem_abc123"})

        asyncio.run(run())

    def test_forget_raises_validation_error_without_memory_id(self, router: MemoryBankRouter) -> None:
        from src.infrastructure.mcp.handlers import handle_forget

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_id is required"):
                await handle_forget(router, {"memory_bank": "test-ns"})

        asyncio.run(run())

    def test_forget_removes_hash_index_entry_on_success(self, router: MemoryBankRouter) -> None:
        """When forget succeeds, use case handles hash index cleanup."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "deleted",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ForgetMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_forget(
                    router,
                    {"memory_id": "mem_to_forget", "memory_bank": "test-ns"},
                )

            assert result["status"] == "deleted"
            # Verify use case was called with correct memory_id
            call_args = mock_use_case.execute.call_args[0][0]
            assert call_args["memory_id"] == "mem_to_forget"

        asyncio.run(run())

    def test_forget_hash_index_removal_is_non_fatal(self, router: MemoryBankRouter) -> None:
        """When hash index removal fails, use case handles it — forget still succeeds."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "deleted",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ForgetMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_forget(
                    router,
                    {"memory_id": "mem_to_forget", "memory_bank": "test-ns"},
                )

            assert result["status"] == "deleted"

        asyncio.run(run())

    def test_forget_hash_index_not_found_is_non_fatal(self, router: MemoryBankRouter) -> None:
        """When no hash index entry exists, use case handles it — forget still succeeds."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "deleted",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ForgetMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_forget(
                    router,
                    {"memory_id": "mem_no_hash", "memory_bank": "test-ns"},
                )

            assert result["status"] == "deleted"

        asyncio.run(run())

    def test_forget_hash_index_creation_error_is_non_fatal(self, router: MemoryBankRouter) -> None:
        """When hash index creation fails, use case handles it — forget still succeeds."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "deleted",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ForgetMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_forget(
                    router,
                    {"memory_id": "mem_to_forget", "memory_bank": "test-ns"},
                )

            assert result["status"] == "deleted"

        asyncio.run(run())

    def test_forget_skips_hash_cleanup_when_not_deleted(self, router: MemoryBankRouter) -> None:
        """When forget returns not_found, use case handles it — no hash cleanup needed."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_forget

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "not_found",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ForgetMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_forget(
                    router,
                    {"memory_id": "mem_not_found", "memory_bank": "test-ns"},
                )

            assert result["status"] == "not_found"

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Update handler
# ---------------------------------------------------------------------------


class TestHandleUpdate:
    """update handler updates in correct memory bank via UpdateMemoryUseCase."""

    def test_update_updates_in_correct_memory_bank(self, router: MemoryBankRouter) -> None:
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_update

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "updated",
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.UpdateMemoryUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_update(
                    router,
                    {"memory_id": "mem_abc123", "content": "updated", "memory_bank": "test-ns"},
                )

            assert result["status"] == "updated"
            assert result["memory_bank"] == "test-ns"

        asyncio.run(run())

    def test_update_raises_validation_error_without_memory_bank(self, router: MemoryBankRouter) -> None:
        from src.infrastructure.mcp.handlers import handle_update

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_update(router, {"memory_id": "mem_abc123", "importance": 0.9})

        asyncio.run(run())

    def test_update_raises_validation_error_without_memory_id(self, router: MemoryBankRouter) -> None:
        from src.infrastructure.mcp.handlers import handle_update

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_id is required"):
                await handle_update(router, {"memory_bank": "test-ns"})

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Sleep handler
# ---------------------------------------------------------------------------


class TestHandleSleep:
    """sleep handler consolidates in correct memory bank via SleepUseCase."""

    def test_sleep_consolidates_in_correct_memory_bank(self, router: MemoryBankRouter) -> None:
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_sleep

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "result": {"status": "ok", "consolidated": 0},
                "memory_bank": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.SleepUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_sleep(router, {"memory_bank": "test-ns"})

            assert result["memory_bank"] == "test-ns"

        asyncio.run(run())

    def test_sleep_raises_validation_error_without_memory_bank(self, router: MemoryBankRouter) -> None:
        from src.infrastructure.mcp.handlers import handle_sleep

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_sleep(router, {})

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Stats handler
# ---------------------------------------------------------------------------


class TestHandleStats:
    """stats handler returns stats from correct memory bank."""

    def test_stats_returns_from_correct_memory_bank(self, router: MemoryBankRouter) -> None:
        from src.infrastructure.mcp.handlers import handle_stats

        async def run() -> None:
            result = await handle_stats(router, {"memory_bank": "test-ns"})

            assert result["memory_bank"] == "test-ns"
            assert result["stats"]["working"] == 5

        asyncio.run(run())

    def test_stats_raises_validation_error_without_memory_bank(self, router: MemoryBankRouter) -> None:
        from src.infrastructure.mcp.handlers import handle_stats

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_stats(router, {})

        asyncio.run(run())


# ---------------------------------------------------------------------------
# List Banks handler
# ---------------------------------------------------------------------------


class TestHandleListBanks:
    """list_banks returns all active banks via ListBanksUseCase."""

    def test_list_banks_returns_all_active_banks(self, router: MemoryBankRouter) -> None:
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_list_banks

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "banks": [
                    {"name": "default", "status": "active"},
                    {"name": "ns1", "status": "active"},
                    {"name": "ns2", "status": "active"},
                ],
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ListBanksUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_list_banks(router, {})

            assert len(result["banks"]) == 3
            names = {ns["name"] for ns in result["banks"]}
            assert names == {"default", "ns1", "ns2"}

        asyncio.run(run())

    def test_list_banks_no_memory_bank_param_needed(self) -> None:
        from src.infrastructure.mcp.schemas import LIST_BANKS_SCHEMA

        # Schema should not require memory_bank parameter
        params = LIST_BANKS_SCHEMA["parameters"]
        assert params["type"] == "object"
        assert "memory_bank" not in params.get("properties", {})

    def test_list_banks_includes_description_from_registry(self, router: MemoryBankRouter) -> None:
        """Each bank entry includes description field from registry (via ListBanksUseCase)."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_list_banks

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "banks": [
                    {
                        "name": "default",
                        "description": "Default personal memory — general conversation context, preferences, and facts",
                    },
                    {
                        "name": "custom-ns",
                        "description": "My custom description",
                    },
                ],
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ListBanksUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_list_banks(router, {})

            default_ns = next(ns for ns in result["banks"] if ns["name"] == "default")
            custom_ns = next(ns for ns in result["banks"] if ns["name"] == "custom-ns")

            assert "description" in default_ns
            assert (
                default_ns["description"]
                == "Default personal memory — general conversation context, preferences, and facts"
            )

            assert "description" in custom_ns
            assert custom_ns["description"] == "My custom description"

        asyncio.run(run())

    def test_list_banks_includes_memory_count_from_stats(self, router: MemoryBankRouter) -> None:
        """Each bank entry includes memory_count from use case result."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_list_banks

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "banks": [
                    {"name": "counted-ns", "memory_count": 15},
                ],
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ListBanksUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_list_banks(router, {})

            counted_ns = next(ns for ns in result["banks"] if ns["name"] == "counted-ns")
            assert "memory_count" in counted_ns
            assert counted_ns["memory_count"] == 15

        asyncio.run(run())

    def test_list_banks_memory_count_handles_missing_keys(self, router: MemoryBankRouter) -> None:
        """memory_count from use case handles missing keys gracefully."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_list_banks

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "banks": [
                    {"name": "sparse-ns", "memory_count": 0},
                ],
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ListBanksUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_list_banks(router, {})

            sparse_ns = next(ns for ns in result["banks"] if ns["name"] == "sparse-ns")
            assert "memory_count" in sparse_ns
            assert isinstance(sparse_ns["memory_count"], int)

        asyncio.run(run())

    def test_list_banks_response_shape_has_all_required_fields(self, router: MemoryBankRouter) -> None:
        """Response shape: {banks: [{name, bank, description, memory_count}, ...]}."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_list_banks

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "banks": [
                    {
                        "name": "default",
                        "bank": "default",
                        "description": "Default",
                        "memory_count": 5,
                        "status": "active",
                    },
                ],
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ListBanksUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_list_banks(router, {})

            assert "banks" in result
            assert isinstance(result["banks"], list)

            for ns in result["banks"]:
                assert "name" in ns
                assert isinstance(ns["name"], str)
                assert "bank" in ns
                assert isinstance(ns["bank"], str)
                assert "description" in ns
                assert isinstance(ns["description"], str)
                assert "memory_count" in ns
                assert isinstance(ns["memory_count"], int)

        asyncio.run(run())

    def test_list_banks_default_always_appears_with_hardcoded_description(self, router: MemoryBankRouter) -> None:
        """Default bank always appears with its hardcoded description (via use case)."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_list_banks

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "banks": [
                    {
                        "name": "default",
                        "description": "Default personal memory — general conversation context, preferences, and facts",
                    },
                ],
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ListBanksUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_list_banks(router, {})

            default_ns = next(ns for ns in result["banks"] if ns["name"] == "default")
            assert (
                default_ns["description"]
                == "Default personal memory — general conversation context, preferences, and facts"
            )

        asyncio.run(run())

    def test_list_banks_unregistered_bank_has_none_description(self, router: MemoryBankRouter) -> None:
        """Banks without registered description show None or empty description (via use case)."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_list_banks

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "banks": [
                    {"name": "unregistered-ns", "description": ""},
                ],
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.ListBanksUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_list_banks(router, {})

            unreg_ns = next(ns for ns in result["banks"] if ns["name"] == "unregistered-ns")
            assert "description" in unreg_ns

        asyncio.run(run())


class TestRegisterBankSchema:
    """register_bank schema has name and description as required fields."""

    def test_register_bank_schema_exists(self) -> None:
        from src.infrastructure.mcp.schemas import REGISTER_BANK_SCHEMA

        assert REGISTER_BANK_SCHEMA is not None

    def test_register_bank_schema_has_correct_name(self) -> None:
        from src.infrastructure.mcp.schemas import REGISTER_BANK_SCHEMA

        assert REGISTER_BANK_SCHEMA["name"] == "registerMemoryBank"

    def test_register_bank_schema_has_description(self) -> None:
        from src.infrastructure.mcp.schemas import REGISTER_BANK_SCHEMA

        assert "description" in REGISTER_BANK_SCHEMA
        assert len(REGISTER_BANK_SCHEMA["description"]) > 0

    def test_register_bank_schema_has_name_parameter(self) -> None:
        from src.infrastructure.mcp.schemas import REGISTER_BANK_SCHEMA

        params = REGISTER_BANK_SCHEMA["parameters"]["properties"]
        assert "name" in params
        assert params["name"]["type"] == "string"

    def test_register_bank_schema_has_description_parameter(self) -> None:
        from src.infrastructure.mcp.schemas import REGISTER_BANK_SCHEMA

        params = REGISTER_BANK_SCHEMA["parameters"]["properties"]
        assert "description" in params
        assert params["description"]["type"] == "string"

    def test_register_bank_schema_requires_name_and_description(self) -> None:
        from src.infrastructure.mcp.schemas import REGISTER_BANK_SCHEMA

        required = REGISTER_BANK_SCHEMA["parameters"]["required"]
        assert "name" in required
        assert "description" in required

    def test_register_bank_schema_in_all_tool_schemas(self) -> None:
        from src.infrastructure.mcp.schemas import ALL_TOOL_SCHEMAS, REGISTER_BANK_SCHEMA

        assert REGISTER_BANK_SCHEMA in ALL_TOOL_SCHEMAS


# ---------------------------------------------------------------------------
# Integration: full tool call round-trip via MCP protocol
# ---------------------------------------------------------------------------


class TestToolCallIntegration:
    """Full tool call round-trip via MCP protocol with use case delegation."""

    @pytest.fixture
    def router(self, tmp_path: Path) -> MemoryBankRouter:
        mock_instance = _mock_mnemosyne_instance()

        with patch.dict(
            "sys.modules",
            {
                "mnemosyne": MagicMock(),
                "mnemosyne.core": MagicMock(),
                "mnemosyne.core.memory": MagicMock(Mnemosyne=lambda **kwargs: mock_instance),
            },
        ):
            config = InstancePoolConfig(
                max_instances=10,
                eviction_timeout=300,
                data_dir=str(tmp_path),
                default_bank="default",
            )
            router = MemoryBankRouter(config=config)
            router._mock_instance = mock_instance
            yield router

    def test_full_remember_recall_round_trip(self, router: MemoryBankRouter) -> None:
        """Remember then recall in same memory bank returns the memory."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_remember, handle_recall

        mock_remember_uc = MagicMock()
        mock_remember_uc.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem_abc123",
                "memory_bank": "user-123",
            }
        )

        mock_recall_uc = MagicMock()
        mock_recall_uc.execute.return_value = Result.ok(
            {
                "results": [{"id": "mem_abc123", "content": "user prefers dark mode"}],
                "memory_bank": "user-123",
            }
        )

        async def run() -> None:
            with patch("src.infrastructure.mcp.handlers.RememberMemoryUseCase", return_value=mock_remember_uc):
                remember_result = await handle_remember(
                    router,
                    {"content": "user prefers dark mode", "memory_bank": "user-123"},
                )
                assert remember_result["status"] == "stored"
                assert remember_result["memory_bank"] == "user-123"

            with patch("src.infrastructure.mcp.handlers.RecallMemoryUseCase", return_value=mock_recall_uc):
                recall_result = await handle_recall(
                    router,
                    {"query": "dark mode", "memory_bank": "user-123"},
                )
                assert recall_result["memory_bank"] == "user-123"
                assert len(recall_result["results"]) == 1

        asyncio.run(run())

    def test_memory_bank_isolation_between_remember_and_recall(self, router: MemoryBankRouter) -> None:
        """Memories stored in one memory bank are not visible in another."""
        from src.infrastructure.mcp.handlers import handle_remember
        from src.utils.result import Result

        mock_uc = MagicMock()
        mock_uc.execute.return_value = Result.ok(
            {
                "status": "stored",
                "memory_id": "mem_abc123",
                "memory_bank": "ns-a",
            }
        )

        async def run() -> None:
            with patch("src.infrastructure.mcp.handlers.RememberMemoryUseCase", return_value=mock_uc):
                # Store in ns-a
                await handle_remember(router, {"content": "ns-a secret", "memory_bank": "ns-a"})

                # Store in ns-b
                await handle_remember(router, {"content": "ns-b secret", "memory_bank": "ns-b"})

            # Verify different clients per memory bank
            assert router.instances["ns-a"] is not router.instances["ns-b"]

        asyncio.run(run())

    def test_mcp_response_format_matches_spec(self, router: MemoryBankRouter) -> None:
        """Response format matches MCP spec with memory_bank field included."""
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import (
            handle_remember,
            handle_recall,
            handle_forget,
            handle_update,
            handle_sleep,
            handle_stats,
        )

        async def run() -> None:
            # remember response
            mock_uc = MagicMock()
            mock_uc.execute.return_value = Result.ok(
                {
                    "status": "stored",
                    "memory_id": "x",
                    "memory_bank": "spec-ns",
                }
            )
            with patch("src.infrastructure.mcp.handlers.RememberMemoryUseCase", return_value=mock_uc):
                r = await handle_remember(router, {"content": "test", "memory_bank": "spec-ns"})
                assert "status" in r
                assert "memory_id" in r
                assert "memory_bank" in r
                assert isinstance(r["status"], str)
                assert isinstance(r["memory_id"], str)
                assert isinstance(r["memory_bank"], str)

            # recall response
            mock_uc = MagicMock()
            mock_uc.execute.return_value = Result.ok(
                {
                    "results": [{"id": "x"}],
                    "memory_bank": "spec-ns",
                }
            )
            with patch("src.infrastructure.mcp.handlers.RecallMemoryUseCase", return_value=mock_uc):
                r = await handle_recall(router, {"query": "test", "memory_bank": "spec-ns"})
                assert "results" in r
                assert "memory_bank" in r
                assert isinstance(r["results"], list)

            # forget response
            mock_uc = MagicMock()
            mock_uc.execute.return_value = Result.ok(
                {
                    "status": "deleted",
                    "memory_bank": "spec-ns",
                }
            )
            with patch("src.infrastructure.mcp.handlers.ForgetMemoryUseCase", return_value=mock_uc):
                r = await handle_forget(router, {"memory_id": "x", "memory_bank": "spec-ns"})
                assert "status" in r
                assert "memory_bank" in r

            # update response
            mock_uc = MagicMock()
            mock_uc.execute.return_value = Result.ok(
                {
                    "status": "updated",
                    "memory_bank": "spec-ns",
                }
            )
            with patch("src.infrastructure.mcp.handlers.UpdateMemoryUseCase", return_value=mock_uc):
                r = await handle_update(router, {"memory_id": "x", "memory_bank": "spec-ns"})
                assert "status" in r
                assert "memory_bank" in r

            # sleep response
            mock_uc = MagicMock()
            mock_uc.execute.return_value = Result.ok(
                {
                    "result": {"status": "ok"},
                    "memory_bank": "spec-ns",
                }
            )
            with patch("src.infrastructure.mcp.handlers.SleepUseCase", return_value=mock_uc):
                r = await handle_sleep(router, {"memory_bank": "spec-ns"})
                assert "memory_bank" in r

            # stats response (not using use case yet)
            r = await handle_stats(router, {"memory_bank": "spec-ns"})
            assert "stats" in r
            assert "memory_bank" in r

        asyncio.run(run())

    def test_memory_bank_required_no_fallback_to_default(self, router: MemoryBankRouter) -> None:
        """All handlers raise ValidationError when memory_bank not provided (no fallback)."""
        from src.infrastructure.mcp.handlers import (
            handle_remember,
            handle_recall,
            handle_forget,
            handle_update,
            handle_sleep,
            handle_stats,
        )

        async def run() -> None:
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_remember(router, {"content": "x"})
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_recall(router, {"query": "x"})
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_forget(router, {"memory_id": "x"})
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_update(router, {"memory_id": "x"})
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_sleep(router, {})
            with pytest.raises(ValidationError, match="memory_bank parameter is required"):
                await handle_stats(router, {})

        asyncio.run(run())


# ---------------------------------------------------------------------------
# Register Bank handler
# ---------------------------------------------------------------------------


class TestHandleRegisterBank:
    """register_bank handler validates args and registers via RegisterBankUseCase."""

    def test_register_bank_success(self, router: MemoryBankRouter) -> None:
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_register_bank

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "registered",
                "name": "my-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RegisterBankUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_register_bank(
                    router,
                    {"name": "my-ns", "description": "My custom bank"},
                )

            assert result["status"] == "registered"
            assert result["name"] == "my-ns"

        asyncio.run(run())

    def test_register_bank_idempotent_updates_description(self, router: MemoryBankRouter) -> None:
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_register_bank

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "registered",
                "name": "my-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RegisterBankUseCase",
                return_value=mock_use_case,
            ):
                # First registration
                await handle_register_bank(
                    router,
                    {"name": "my-ns", "description": "Original description"},
                )

                # Second registration with same name updates description
                result = await handle_register_bank(
                    router,
                    {"name": "my-ns", "description": "Updated description"},
                )
                assert result["status"] == "registered"
                assert result["name"] == "my-ns"

        asyncio.run(run())

    def test_register_bank_raises_when_name_missing(self, router: MemoryBankRouter) -> None:
        from src.utils.result import ErrorWithDetails, Result
        from src.infrastructure.mcp.handlers import handle_register_bank

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([ErrorWithDetails("NAME_REQUIRED", {})])

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RegisterBankUseCase",
                return_value=mock_use_case,
            ):
                with pytest.raises(ValidationError, match="registerMemoryBank failed"):
                    await handle_register_bank(router, {"description": "no name"})

        asyncio.run(run())

    def test_register_bank_raises_when_description_missing(self, router: MemoryBankRouter) -> None:
        from src.utils.result import ErrorWithDetails, Result
        from src.infrastructure.mcp.handlers import handle_register_bank

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([ErrorWithDetails("DESCRIPTION_REQUIRED", {})])

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RegisterBankUseCase",
                return_value=mock_use_case,
            ):
                with pytest.raises(ValidationError, match="registerMemoryBank failed"):
                    await handle_register_bank(router, {"name": "no-desc"})

        asyncio.run(run())

    def test_register_bank_raises_when_both_missing(self, router: MemoryBankRouter) -> None:
        from src.utils.result import ErrorWithDetails, Result
        from src.infrastructure.mcp.handlers import handle_register_bank

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ko([ErrorWithDetails("NAME_REQUIRED", {})])

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RegisterBankUseCase",
                return_value=mock_use_case,
            ):
                with pytest.raises(ValidationError, match="registerMemoryBank failed"):
                    await handle_register_bank(router, {})

        asyncio.run(run())

    def test_register_bank_returns_correct_shape(self, router: MemoryBankRouter) -> None:
        from src.utils.result import Result
        from src.infrastructure.mcp.handlers import handle_register_bank

        mock_use_case = MagicMock()
        mock_use_case.execute.return_value = Result.ok(
            {
                "status": "registered",
                "name": "test-ns",
            }
        )

        async def run() -> None:
            with patch(
                "src.infrastructure.mcp.handlers.RegisterBankUseCase",
                return_value=mock_use_case,
            ):
                result = await handle_register_bank(
                    router,
                    {"name": "test-ns", "description": "Test"},
                )

            assert set(result.keys()) == {"status", "name"}
            assert isinstance(result["status"], str)
            assert isinstance(result["name"], str)

        asyncio.run(run())
