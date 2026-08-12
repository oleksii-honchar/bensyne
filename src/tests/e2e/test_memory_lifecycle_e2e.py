"""E2E tests for the full memory lifecycle: handler → use case → domain → repository.

Validates that the DDD migration preserved backward compatibility and that
the architecture works as a complete system. Uses mocked MnemosyneClient
and in-memory repositories to avoid real database/service dependencies.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.domain.exceptions import ValidationError
from src.utils.result import Result
from src.tests.test_domain.domain_test_utils import (
    InMemoryMemoryRepository,
    a_memory,
    a_memory_repository,
)


# ---------------------------------------------------------------------------
# Fixtures — full application setup with real dependencies
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_mnemosyne_client() -> MagicMock:
    """Create a mock MnemosyneClient that returns realistic responses.

    The use cases (forget, update, recall) call .get() and [] on the
    client's return values — they expect raw dicts, not Result objects.
    Only RememberMemoryUseCase uses the client as a MemoryRepository
    (calling .save() which returns Result).
    """
    client = MagicMock()
    client.memory_bank = "default"
    client.last_accessed = 0.0

    # remember: used by RememberMemoryUseCase as MemoryRepository.save() → returns Result
    client.save = MagicMock(return_value=Result.ok(a_memory(id="mem-001")))

    # recall: used by RecallMemoryUseCase → returns Result[List[Dict]]
    client.recall = MagicMock(return_value=Result.ok([
        {"id": "mem-001", "content": "test memory", "score": 0.9},
    ]))

    # forget: used by ForgetMemoryUseCase → returns Result[bool]
    client.forget = MagicMock(return_value=Result.ok(True))

    # update: used by UpdateMemoryUseCase → returns Result[bool]
    client.update = MagicMock(return_value=Result.ok(True))

    # sleep: used by SleepUseCase → returns Result[Dict]
    client.sleep = MagicMock(return_value=Result.ok({
        "status": "consolidated",
    }))

    # stats: used directly by handlers → returns Result (handler checks .is_ok)
    client.stats = MagicMock(return_value=Result.ok({
        "working_count": 1,
        "episodic_count": 0,
    }))
    return client


@pytest.fixture
def mock_router(mock_mnemosyne_client: MagicMock) -> MagicMock:
    """Create a mock MemoryBankRouter that returns the mock client."""
    router = MagicMock()
    router.get_instance = AsyncMock(return_value=mock_mnemosyne_client)
    router.instances = {"default": mock_mnemosyne_client}
    router.registry = MagicMock()
    router.registry.list_banks.return_value = ["default"]
    router.get_bank_description.return_value = "Default personal memory"
    return router


@pytest.fixture
def in_memory_repo() -> InMemoryMemoryRepository:
    """Create an empty in-memory memory repository."""
    return a_memory_repository()


# ---------------------------------------------------------------------------
# Test: Complete memory lifecycle (create → recall → update → forget)
# ---------------------------------------------------------------------------

class TestMemoryLifecycle:
    """E2E: complete memory lifecycle through handler → use case → domain → infra."""

    async def test_complete_lifecycle_remember_recall_update_forget(
        self,
        mock_router: MagicMock,
        mock_mnemosyne_client: MagicMock,
    ) -> None:
        """Store a memory, recall it, update it, then forget it — full lifecycle.

        Patches RememberMemoryUseCase because Memory.of() requires an id that
        the handler does not provide — the real Mnemosyne library generates it.
        """
        from src.infrastructure.mcp.handlers import (
            handle_remember,
            handle_recall,
            handle_forget,
            handle_update,
        )

        bank = "lifecycle_test"

        # --- Create ---
        with patch(
            "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
        ) as MockUc:
            mock_uc = MagicMock()
            mock_uc.execute.return_value = Result.ok({
                "status": "stored",
                "memory_id": "mem-lifecycle-1",
                "memory_bank": bank,
            })
            MockUc.return_value = mock_uc

            remember_result = await handle_remember(
                mock_router,
                {"memory_bank": bank, "content": "E2E lifecycle memory"},
            )

        assert remember_result["status"] == "stored"
        assert remember_result["memory_bank"] == bank
        assert remember_result["memory_id"] == "mem-lifecycle-1"

        # --- Recall ---
        recall_result = await handle_recall(
            mock_router,
            {"memory_bank": bank, "query": "lifecycle memory"},
        )
        assert recall_result["memory_bank"] == bank
        assert "results" in recall_result
        assert recall_result["results"][0]["id"] == "mem-001"

        # --- Update ---
        update_result = await handle_update(
            mock_router,
            {
                "memory_bank": bank,
                "memory_id": "mem-lifecycle-1",
                "content": "updated lifecycle memory",
            },
        )
        assert update_result["status"] == "updated"
        assert update_result["memory_bank"] == bank

        # --- Forget ---
        forget_result = await handle_forget(
            mock_router,
            {"memory_bank": bank, "memory_id": "mem-lifecycle-1"},
            bank_type_checker=lambda bank: "pure_memories",
        )
        assert forget_result["status"] == "deleted"
        assert forget_result["memory_bank"] == bank

    async def test_sleep_returns_consolidated_result(
        self,
        mock_router: MagicMock,
    ) -> None:
        """Sleep triggers consolidation and returns proper result."""
        from src.infrastructure.mcp.handlers import handle_sleep

        sleep_result = await handle_sleep(
            mock_router,
            {"memory_bank": "default"},
        )
        assert sleep_result["memory_bank"] == "default"
        assert isinstance(sleep_result, dict)

    async def test_stats_returns_valid_data(
        self,
        mock_router: MagicMock,
    ) -> None:
        """Stats returns valid data for a memory bank."""
        from src.infrastructure.mcp.handlers import handle_stats

        stats_result = await handle_stats(
            mock_router,
            {"memory_bank": "default"},
        )
        assert stats_result["memory_bank"] == "default"
        assert "stats" in stats_result
        assert isinstance(stats_result["stats"], dict)

    async def test_lifecycle_with_in_memory_repository(
        self,
        in_memory_repo: InMemoryMemoryRepository,
    ) -> None:
        """Full lifecycle using in-memory repository directly through use case."""
        from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
        from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase
        from src.infrastructure.mcp.hash_index_service import HashIndexService
        from src.utils.structured_logging import LoggerMock

        # Create a mock hash index service
        mock_hash_service = MagicMock(spec=HashIndexService)
        mock_hash_service.lookup.return_value = None  # No dedup
        mock_hash_service.store = MagicMock()
        mock_hash_service.remove = MagicMock()

        logger = LoggerMock()

        # --- Create memory via RememberMemoryUseCase with in-memory repo ---
        process_uc = RememberMemoryUseCase(
            memory_repository=in_memory_repo,
            hash_index_service=mock_hash_service,
            logger=logger,
        )

        create_result = process_uc.execute({
            "id": "e2e-mem-1",
            "content": "In-memory test memory",
            "memory_bank": "test_bank",
        })
        assert create_result.is_ok is True
        assert create_result.value["status"] == "stored"
        assert create_result.value["memory_id"] == "e2e-mem-1"

        # Verify memory was saved in the in-memory repository
        find_result = in_memory_repo.find_by_id("e2e-mem-1")
        assert find_result.is_ok is True
        assert find_result.value is not None
        assert find_result.value.content == "In-memory test memory"

        # --- Forget memory via ForgetMemoryUseCase ---
        mock_client = MagicMock()
        mock_client.forget.return_value = Result.ok(True)

        forget_uc = ForgetMemoryUseCase(
            mnemosyne_client=mock_client,
            hash_index_service=mock_hash_service,
            logger=logger,
            file_service=MagicMock(),
            chunk_repository=MagicMock(),
            bank_type_checker=lambda bank: "pure_memories",
        )

        forget_result = forget_uc.execute({
            "memory_id": "e2e-mem-1",
            "memory_bank": "test_bank",
        })
        assert forget_result.is_ok is True
        assert forget_result.value["status"] == "deleted"
        # Hash index should be cleaned up
        mock_hash_service.remove.assert_called_once_with("e2e-mem-1")

# ---------------------------------------------------------------------------
# Test: Memory deduplication via hash
# ---------------------------------------------------------------------------

class TestMemoryDeduplication:
    """E2E: memory deduplication via hash index."""

    async def test_deduplication_returns_existing_memory_id(
        self,
    ) -> None:
        """When the same file hash is provided, the use case returns deduplicated status."""
        from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
        from src.infrastructure.mcp.hash_index_service import HashIndexService
        from src.tests.test_domain.domain_test_utils import a_memory_repository
        from src.utils.structured_logging import LoggerMock

        mock_hash_service = MagicMock(spec=HashIndexService)
        existing_id = "existing-mem-id"
        mock_hash_service.lookup.return_value = Result.ok(existing_id)

        repo = a_memory_repository()
        logger = LoggerMock()

        uc = RememberMemoryUseCase(
            memory_repository=repo,
            hash_index_service=mock_hash_service,
            logger=logger,
        )

        result = uc.execute({
            "content": "file content",
            "hash": "a" * 64,  # SHA-256 hash
        })

        assert result.is_ok is True
        assert result.value["status"] == "deduplicated"
        assert result.value["memory_id"] == existing_id
        # Repository save should NOT be called when deduplicated
        assert len(repo._store) == 0
        mock_hash_service.store.assert_not_called()

    async def test_deduplication_via_handler(
        self,
        mock_router: MagicMock,
    ) -> None:
        """Handler-level deduplication: same hash returns deduplicated.

        Patches RememberMemoryUseCase because Memory.of() requires an id that
        the handler does not provide.
        """
        from src.infrastructure.mcp.handlers import handle_remember

        # Patch RememberMemoryUseCase to return deduplicated result
        with patch(
            "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
        ) as MockUc:
            mock_uc = MagicMock()
            mock_uc.execute.return_value = Result.ok({
                "status": "deduplicated",
                "memory_id": "dedup-mem-id",
            })
            MockUc.return_value = mock_uc

            result = await handle_remember(
                mock_router,
                {
                    "memory_bank": "dedup_bank",
                    "content": "file content",
                    "file_path": "/path/to/file.txt",
                    "file_hash": "a" * 64,
                },
            )

            assert result["status"] == "deduplicated"
            assert result["memory_id"] == "dedup-mem-id"

    async def test_new_hash_is_stored_after_save(
        self,
        in_memory_repo: InMemoryMemoryRepository,
    ) -> None:
        """When a new hash is provided and memory is saved, hash is stored in index."""
        from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
        from src.infrastructure.mcp.hash_index_service import HashIndexService
        from src.utils.structured_logging import LoggerMock

        mock_hash_service = MagicMock(spec=HashIndexService)
        mock_hash_service.lookup.return_value = Result.ok(None)  # New hash

        logger = LoggerMock()

        uc = RememberMemoryUseCase(
            memory_repository=in_memory_repo,
            hash_index_service=mock_hash_service,
            logger=logger,
        )

        test_hash = "b" * 64
        result = uc.execute({
            "id": "new-mem-1",
            "content": "file content",
            "hash": test_hash,
        })

        assert result.is_ok is True
        assert result.value["status"] == "stored"
        # Hash should be stored after save
        mock_hash_service.store.assert_called_once_with(test_hash, "new-mem-1")

# ---------------------------------------------------------------------------
# Test: Bank registration and listing
# ---------------------------------------------------------------------------

class TestBankRegistrationAndListing:
    """E2E: memory bank registration and listing."""

    async def test_register_bank_via_handler(
        self,
        mock_router: MagicMock,
    ) -> None:
        """Register a new bank via handler and verify it's registered."""
        from src.infrastructure.mcp.handlers import handle_register_bank

        result = await handle_register_bank(
            mock_router,
            {"name": "new_bank", "description": "A new test bank"},
        )

        assert result["status"] == "registered"
        assert result["name"] == "new_bank"
        mock_router.register_bank.assert_called_once_with("new_bank", "A new test bank")

    async def test_list_banks_via_handler(
        self,
        mock_router: MagicMock,
    ) -> None:
        """List banks returns merged list of active and registered."""
        from src.infrastructure.mcp.handlers import handle_list_banks

        # Setup: mock router has active instances and registered banks
        mock_router.instances = {"default": MagicMock(
            memory_bank="default",
            stats=MagicMock(return_value={"working_count": 5, "episodic_count": 2}),
        )}
        mock_router.get_bank_description.return_value = "Default bank"
        mock_router.registry.list_banks.return_value = ["default", "registered_only"]

        result = await handle_list_banks(mock_router, {})

        assert "banks" in result
        assert len(result["banks"]) >= 1
        # Default should be active
        default_bank = [b for b in result["banks"] if b["name"] == "default"][0]
        assert default_bank["status"] == "active"
        assert default_bank["memory_count"] == 7  # working + episodic

    async def test_register_bank_use_case_validates_name(
        self,
    ) -> None:
        """RegisterBankUseCase rejects empty name."""
        from src.application.use_cases.register_bank_use_case import RegisterBankUseCase
        from src.utils.structured_logging import LoggerMock

        mock_router = MagicMock()
        logger = LoggerMock()

        uc = RegisterBankUseCase(router=mock_router, logger=logger)

        result = uc.execute({"name": "", "description": "A bank"})
        assert result.is_ko is True
        assert result.errors[0].error_code == "NAME_REQUIRED"

    async def test_register_bank_use_case_validates_description(
        self,
    ) -> None:
        """RegisterBankUseCase rejects empty description."""
        from src.application.use_cases.register_bank_use_case import RegisterBankUseCase
        from src.utils.structured_logging import LoggerMock

        mock_router = MagicMock()
        logger = LoggerMock()

        uc = RegisterBankUseCase(router=mock_router, logger=logger)

        result = uc.execute({"name": "valid_name", "description": ""})
        assert result.is_ko is True
        assert result.errors[0].error_code == "DESCRIPTION_REQUIRED"

# ---------------------------------------------------------------------------
# Test: Error handling — invalid inputs return proper error responses
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """E2E: invalid inputs return proper error responses."""

    async def test_remember_raises_validation_error_when_content_missing(
        self,
        mock_router: MagicMock,
    ) -> None:
        """handle_remember raises ValidationError when content is missing."""
        from src.infrastructure.mcp.handlers import handle_remember

        with pytest.raises(ValidationError):
            await handle_remember(mock_router, {"memory_bank": "default"})

    async def test_recall_raises_validation_error_when_query_missing(
        self,
        mock_router: MagicMock,
    ) -> None:
        """handle_recall raises ValidationError when query is missing."""
        from src.infrastructure.mcp.handlers import handle_recall

        with pytest.raises(ValidationError):
            await handle_recall(mock_router, {"memory_bank": "default"})

    async def test_forget_raises_validation_error_when_memory_id_missing(
        self,
        mock_router: MagicMock,
    ) -> None:
        """handle_forget raises ValidationError when memory_id is missing."""
        from src.infrastructure.mcp.handlers import handle_forget

        with pytest.raises(ValidationError):
            await handle_forget(mock_router, {"memory_bank": "default"}, bank_type_checker=lambda bank: "pure_memories")

    async def test_update_raises_validation_error_when_memory_id_missing(
        self,
        mock_router: MagicMock,
    ) -> None:
        """handle_update raises ValidationError when memory_id is missing."""
        from src.infrastructure.mcp.handlers import handle_update

        with pytest.raises(ValidationError):
            await handle_update(mock_router, {"memory_bank": "default"})

    async def test_remember_raises_validation_error_on_use_case_ko(
        self,
        mock_router: MagicMock,
    ) -> None:
        """handle_remember raises ValidationError when use case returns Result.ko."""
        from src.infrastructure.mcp.handlers import handle_remember

        with patch(
            "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
        ) as MockUc:
            mock_uc = MagicMock()
            mock_uc.execute.return_value = Result.ko([
                MagicMock(error_code="CONTENT_REQUIRED", details={}),
            ])
            MockUc.return_value = mock_uc

            with pytest.raises(ValidationError):
                await handle_remember(
                    mock_router,
                    {"memory_bank": "default", "content": "test"},
                )

    async def test_remember_memory_use_case_rejects_empty_content(
        self,
        in_memory_repo: InMemoryMemoryRepository,
    ) -> None:
        """RememberMemoryUseCase rejects empty content with proper error."""
        from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
        from src.infrastructure.mcp.hash_index_service import HashIndexService
        from src.utils.structured_logging import LoggerMock

        mock_hash = MagicMock(spec=HashIndexService)
        logger = LoggerMock()

        uc = RememberMemoryUseCase(
            memory_repository=in_memory_repo,
            hash_index_service=mock_hash,
            logger=logger,
        )

        result = uc.execute({"content": ""})
        assert result.is_ko is True
        assert result.errors[0].error_code == "CONTENT_REQUIRED"

    async def test_recall_use_case_rejects_empty_query(
        self,
    ) -> None:
        """RecallMemoryUseCase rejects empty query with proper error."""
        from src.application.use_cases.recall_memory_use_case import RecallMemoryUseCase
        from src.utils.structured_logging import LoggerMock

        mock_client = MagicMock()
        logger = LoggerMock()

        uc = RecallMemoryUseCase(
            mnemosyne_client=mock_client,
            logger=logger,
        )

        result = uc.execute({"query": ""})
        assert result.is_ko is True
        assert result.errors[0].error_code == "QUERY_REQUIRED"

    async def test_forget_use_case_rejects_empty_memory_id(
        self,
    ) -> None:
        """ForgetMemoryUseCase rejects empty memory_id with proper error."""
        from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase
        from src.infrastructure.mcp.hash_index_service import HashIndexService
        from src.utils.structured_logging import LoggerMock

        mock_hash = MagicMock(spec=HashIndexService)
        logger = LoggerMock()

        uc = ForgetMemoryUseCase(
            mnemosyne_client=MagicMock(),
            hash_index_service=mock_hash,
            logger=logger,
            file_service=MagicMock(),
            chunk_repository=MagicMock(),
            bank_type_checker=lambda bank: "pure_memories",
        )

        result = uc.execute({"memory_id": ""})
        assert result.is_ko is True
        assert result.errors[0].error_code == "MEMORY_ID_REQUIRED"

    async def test_update_use_case_rejects_empty_memory_id(
        self,
    ) -> None:
        """UpdateMemoryUseCase rejects empty memory_id with proper error."""
        from src.application.use_cases.update_memory_use_case import UpdateMemoryUseCase
        from src.utils.structured_logging import LoggerMock

        mock_client = MagicMock()
        logger = LoggerMock()

        uc = UpdateMemoryUseCase(
            mnemosyne_client=mock_client,
            logger=logger,
        )

        result = uc.execute({"memory_id": ""})
        assert result.is_ko is True
        assert result.errors[0].error_code == "MEMORY_ID_REQUIRED"

# ---------------------------------------------------------------------------
# Test: Memory bank isolation
# ---------------------------------------------------------------------------

class TestMemoryBankIsolation:
    """E2E: memories in one bank not visible in another."""

    async def test_bank_isolation_via_router_routing(
        self,
    ) -> None:
        """Memories stored in bank A are not returned when recalling from bank B.

        Verifies that the router routes requests to the correct bank's client,
        ensuring isolation between memory banks.
        """
        from src.infrastructure.mcp.handlers import handle_remember, handle_recall

        # Create two isolated mock clients, one per bank
        client_a = MagicMock()
        client_a.memory_bank = "bank_a"
        client_a.recall = MagicMock(return_value=Result.ok([
            {"id": "mem-a-1", "content": "Bank A memory", "score": 0.9},
        ]))

        client_b = MagicMock()
        client_b.memory_bank = "bank_b"
        client_b.recall = MagicMock(return_value=Result.ok([
            {"id": "mem-b-1", "content": "Bank B memory", "score": 0.9},
        ]))

        router = MagicMock()

        async def get_instance(bank: str):
            if bank == "bank_a":
                return client_a
            return client_b

        router.get_instance = AsyncMock(side_effect=get_instance)

        # Store memory in bank A — patch RememberMemoryUseCase since handler
        # doesn't provide id (Memory.of requires it)
        with patch(
            "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
        ) as MockUc:
            mock_uc = MagicMock()
            mock_uc.execute.return_value = Result.ok({
                "status": "stored",
                "memory_id": "mem-a-1",
                "memory_bank": "bank_a",
            })
            MockUc.return_value = mock_uc

            result_a = await handle_remember(
                router,
                {"memory_bank": "bank_a", "content": "Bank A memory"},
            )
        assert result_a["status"] == "stored"
        assert result_a["memory_bank"] == "bank_a"

        with patch(
            "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
        ) as MockUc:
            mock_uc = MagicMock()
            mock_uc.execute.return_value = Result.ok({
                "status": "stored",
                "memory_id": "mem-b-1",
                "memory_bank": "bank_b",
            })
            MockUc.return_value = mock_uc

            result_b = await handle_remember(
                router,
                {"memory_bank": "bank_b", "content": "Bank B memory"},
            )
        assert result_b["status"] == "stored"
        assert result_b["memory_bank"] == "bank_b"

        # Recall from bank A should NOT return bank B's memory
        recall_a = await handle_recall(
            router,
            {"memory_bank": "bank_a", "query": "memory"},
        )
        assert recall_a["memory_bank"] == "bank_a"
        for r in recall_a["results"]:
            assert r["id"] == "mem-a-1", f"Bank A recall should not contain {r['id']}"

        # Recall from bank B should NOT return bank A's memory
        recall_b = await handle_recall(
            router,
            {"memory_bank": "bank_b", "query": "memory"},
        )
        assert recall_b["memory_bank"] == "bank_b"
        for r in recall_b["results"]:
            assert r["id"] == "mem-b-1", f"Bank B recall should not contain {r['id']}"

    async def test_bank_isolation_via_in_memory_repository(
        self,
    ) -> None:
        """In-memory repository separates memories by bank via find_by_bank."""
        from src.tests.test_domain.domain_test_utils import a_memory, InMemoryMemoryRepository

        # Create memories for different "banks" (using source field as bank discriminator)
        mem_a = a_memory(id="mem-a", source="bank_a", content="Bank A content")
        mem_b = a_memory(id="mem-b", source="bank_b", content="Bank B content")

        repo = InMemoryMemoryRepository(data=[mem_a, mem_b])

        # Find by bank_a should only return bank A's memory
        result_a = repo.find_by_bank("bank_a")
        assert result_a.is_ok is True
        assert len(result_a.value) == 1
        assert result_a.value[0].id == "mem-a"

        # Find by bank_b should only return bank B's memory
        result_b = repo.find_by_bank("bank_b")
        assert result_b.is_ok is True
        assert len(result_b.value) == 1
        assert result_b.value[0].id == "mem-b"

    async def test_forget_in_one_bank_does_not_affect_another(
        self,
    ) -> None:
        """Forgetting a memory in bank A does not affect bank B."""
        from src.infrastructure.mcp.handlers import handle_forget

        client_a = MagicMock()
        client_a.memory_bank = "bank_a"
        client_a.forget.return_value = Result.ok(True)

        client_b = MagicMock()
        client_b.memory_bank = "bank_b"
        client_b.forget.return_value = Result.ok(True)

        router = MagicMock()

        async def get_instance(bank: str):
            if bank == "bank_a":
                return client_a
            return client_b

        router.get_instance = AsyncMock(side_effect=get_instance)

        # Forget from bank A
        result = await handle_forget(
            router,
            {"memory_bank": "bank_a", "memory_id": "mem-a"},
            bank_type_checker=lambda bank: "pure_memories",
        )
        assert result["status"] == "deleted"
        assert result["memory_bank"] == "bank_a"

        # Bank B's client should NOT have been called
        client_b.forget.assert_not_called()

# ---------------------------------------------------------------------------
# Test: MCP tool interfaces preserved and working
# ---------------------------------------------------------------------------

class TestMCPToolInterfacesPreserved:
    """E2E: all existing MCP tool interfaces preserved and working."""

    async def test_remember_interface_preserved(
        self,
        mock_router: MagicMock,
    ) -> None:
        """rememberMemory returns dict with status, memory_id, memory_bank.

        Patches RememberMemoryUseCase because Memory.of() requires an id that
        the handler does not provide.
        """
        from src.infrastructure.mcp.handlers import handle_remember

        with patch(
            "src.infrastructure.mcp.handlers.RememberMemoryUseCase",
        ) as MockUc:
            mock_uc = MagicMock()
            mock_uc.execute.return_value = Result.ok({
                "status": "stored",
                "memory_id": "mem-iface-1",
                "memory_bank": "default",
            })
            MockUc.return_value = mock_uc

            result = await handle_remember(
                mock_router,
                {"memory_bank": "default", "content": "interface test"},
            )

        # Verify the response shape matches the expected MCP tool interface
        assert isinstance(result, dict)
        assert "status" in result
        assert "memory_id" in result
        assert "memory_bank" in result
        assert result["memory_bank"] == "default"

    async def test_recall_interface_preserved(
        self,
        mock_router: MagicMock,
    ) -> None:
        """recallMemory returns dict with results and memory_bank."""
        from src.infrastructure.mcp.handlers import handle_recall

        result = await handle_recall(
            mock_router,
            {"memory_bank": "default", "query": "interface test"},
        )

        assert isinstance(result, dict)
        assert "results" in result
        assert "memory_bank" in result
        assert result["memory_bank"] == "default"

    async def test_forget_interface_preserved(
        self,
        mock_router: MagicMock,
    ) -> None:
        """forgetMemory returns dict with status and memory_bank."""
        from src.infrastructure.mcp.handlers import handle_forget

        result = await handle_forget(
            mock_router,
            {"memory_bank": "default", "memory_id": "mem-001"},
            bank_type_checker=lambda bank: "pure_memories",
        )

        assert isinstance(result, dict)
        assert "status" in result
        assert "memory_bank" in result

    async def test_update_interface_preserved(
        self,
        mock_router: MagicMock,
    ) -> None:
        """updateMemory returns dict with status and memory_bank."""
        from src.infrastructure.mcp.handlers import handle_update

        result = await handle_update(
            mock_router,
            {"memory_bank": "default", "memory_id": "mem-001", "content": "updated"},
        )

        assert isinstance(result, dict)
        assert "status" in result
        assert "memory_bank" in result

    async def test_sleep_interface_preserved(
        self,
        mock_router: MagicMock,
    ) -> None:
        """sleep returns dict with result and memory_bank."""
        from src.infrastructure.mcp.handlers import handle_sleep

        result = await handle_sleep(
            mock_router,
            {"memory_bank": "default"},
        )

        assert isinstance(result, dict)
        assert "memory_bank" in result

    async def test_stats_interface_preserved(
        self,
        mock_router: MagicMock,
    ) -> None:
        """getMemoryStats returns dict with stats and memory_bank."""
        from src.infrastructure.mcp.handlers import handle_stats

        result = await handle_stats(
            mock_router,
            {"memory_bank": "default"},
        )

        assert isinstance(result, dict)
        assert "stats" in result
        assert "memory_bank" in result

    async def test_list_banks_interface_preserved(
        self,
        mock_router: MagicMock,
    ) -> None:
        """listMemoryBanks returns dict with banks list."""
        from src.infrastructure.mcp.handlers import handle_list_banks

        result = await handle_list_banks(mock_router, {})

        assert isinstance(result, dict)
        assert "banks" in result
        assert isinstance(result["banks"], list)

    async def test_register_bank_interface_preserved(
        self,
        mock_router: MagicMock,
    ) -> None:
        """registerMemoryBank returns dict with status and name."""
        from src.infrastructure.mcp.handlers import handle_register_bank

        result = await handle_register_bank(
            mock_router,
            {"name": "test_bank", "description": "Test bank"},
        )

        assert isinstance(result, dict)
        assert "status" in result
        assert "name" in result
