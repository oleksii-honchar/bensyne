"""Unit tests for ListBanksUseCase and RegisterBankUseCase.

Task 7 rewire: business goes through ``MemoryBankService``, technical data
(instance pool + filesystem scan) through the router. The use cases no longer
touch the router's removed registry duties (removed in Task 3).
"""

from datetime import datetime
from unittest.mock import MagicMock

import pytest

from src.application.use_cases.list_banks_use_case import ListBanksUseCase
from src.application.use_cases.register_bank_use_case import RegisterBankUseCase
from src.domain.memory_bank_aggregate import MemoryBank
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock


def _bank(
    name: str,
    description: str = "desc",
    status: str = "registered",
    memory_count: int = 0,
) -> MemoryBank:
    """Build a MemoryBank aggregate directly (no factory side effects)."""
    return MemoryBank(
        name=name,
        description=description,
        status=status,
        created_at=datetime.now(),
        last_accessed=None,
        memory_count=memory_count,
        memories=[],
    )


class TestRegisterBankUseCase:
    """Test RegisterBankUseCase validation and registration logic (via service)."""

    @pytest.fixture
    def memory_bank_service(self) -> MagicMock:
        service = MagicMock()
        service.register_memory_bank.return_value = Result.ok(_bank("my-bank"))
        return service

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(self, memory_bank_service, logger) -> RegisterBankUseCase:
        return RegisterBankUseCase(
            memory_bank_service=memory_bank_service,
            logger=logger,
        )

    # -- Validation --

    def test_validate_params_rejects_empty_name(self, use_case) -> None:
        """Empty name should return Result.ko with NAME_REQUIRED."""
        result = use_case.validate_params({"name": "", "description": "desc"})

        assert result.is_ko is True
        assert result.errors[0].error_code == "NAME_REQUIRED"

    def test_validate_params_rejects_missing_name(self, use_case) -> None:
        """Missing name should return Result.ko with NAME_REQUIRED."""
        result = use_case.validate_params({"description": "desc"})

        assert result.is_ko is True
        assert result.errors[0].error_code == "NAME_REQUIRED"

    def test_validate_params_rejects_empty_description(self, use_case) -> None:
        """Empty description should return Result.ko with DESCRIPTION_REQUIRED."""
        result = use_case.validate_params({"name": "my-bank", "description": ""})

        assert result.is_ko is True
        assert result.errors[0].error_code == "DESCRIPTION_REQUIRED"

    def test_validate_params_rejects_missing_description(self, use_case) -> None:
        """Missing description should return Result.ko with DESCRIPTION_REQUIRED."""
        result = use_case.validate_params({"name": "my-bank"})

        assert result.is_ko is True
        assert result.errors[0].error_code == "DESCRIPTION_REQUIRED"

    def test_validate_params_accepts_valid_params(self, use_case) -> None:
        """Valid name and description should pass validation."""
        result = use_case.validate_params({"name": "my-bank", "description": "A test bank"})

        assert result.is_ok is True
        assert result.value["name"] == "my-bank"
        assert result.value["description"] == "A test bank"

    # -- Execution --

    def test_execute_calls_service_register_memory_bank(self, use_case, memory_bank_service) -> None:
        """Successful execution should call memory_bank_service.register_memory_bank."""
        result = use_case.execute({"name": "my-bank", "description": "A test bank"})

        assert result.is_ok is True
        memory_bank_service.register_memory_bank.assert_called_once_with(
            "my-bank", "A test bank"
        )

    def test_execute_returns_registered_status_and_name(self, use_case) -> None:
        """Result should contain status='registered' and the bank name."""
        result = use_case.execute({"name": "my-bank", "description": "A test bank"})

        assert result.is_ok is True
        assert result.value["status"] == "registered"
        assert result.value["name"] == "my-bank"

    def test_execute_propagates_service_ko(self, memory_bank_service, use_case) -> None:
        """A service Result.ko (e.g. INVALID_MEMORY_BANK) propagates as use-case Result.ko."""
        memory_bank_service.register_memory_bank.return_value = Result.ko(
            [ErrorWithDetails("INVALID_MEMORY_BANK", {"name": "bad-name"})]
        )

        result = use_case.execute({"name": "bad-name", "description": "x"})

        assert result.is_ko is True
        assert result.errors[0].error_code == "INVALID_MEMORY_BANK"

    def test_execute_returns_ko_when_name_empty(self, use_case, memory_bank_service) -> None:
        """Execute with empty name should return Result.ko without calling the service."""
        result = use_case.execute({"name": "", "description": "desc"})

        assert result.is_ko is True
        assert result.errors[0].error_code == "NAME_REQUIRED"
        memory_bank_service.register_memory_bank.assert_not_called()

    def test_execute_returns_ko_when_description_empty(self, use_case, memory_bank_service) -> None:
        """Execute with empty description should return Result.ko without calling the service."""
        result = use_case.execute({"name": "my-bank", "description": ""})

        assert result.is_ko is True
        assert result.errors[0].error_code == "DESCRIPTION_REQUIRED"
        memory_bank_service.register_memory_bank.assert_not_called()


class TestListBanksUseCase:
    """Test ListBanksUseCase merged listing (filesystem ∪ pool ∪ registry)."""

    @pytest.fixture
    def router(self) -> MagicMock:
        router = MagicMock()
        router.instances = {}
        router.list_bank_dirs.return_value = []
        return router

    @pytest.fixture
    def memory_bank_service(self) -> MagicMock:
        service = MagicMock()
        service.list_memory_banks.return_value = Result.ok([])
        return service

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(self, memory_bank_service, router, logger) -> ListBanksUseCase:
        return ListBanksUseCase(
            memory_bank_service=memory_bank_service,
            router=router,
            logger=logger,
        )

    # -- Validation --

    def test_validate_params_accepts_empty_params(self, use_case) -> None:
        """ListBanksUseCase requires no parameters, so empty dict passes."""
        result = use_case.validate_params({})

        assert result.is_ok is True

    # -- Merge behavior --

    def test_bank_present_only_on_disk_is_on_disk(self, router, use_case) -> None:
        """A dir-only bank → status='on_disk', empty description, memory_count 0."""
        router.list_bank_dirs.return_value = ["disk-only"]
        router.get_stats_for.return_value = Result.ko(
            [ErrorWithDetails("MEMORY_BANK_DB_NOT_FOUND", {"bank": "disk-only"})]
        )

        result = use_case.execute({})

        assert result.is_ok is True
        bank = result.value["banks"][0]
        assert bank["name"] == "disk-only"
        assert bank["status"] == "on_disk"
        assert bank["description"] == ""
        assert bank["memory_count"] == 0

    def test_bank_present_only_in_registry_uses_stored_fields(
        self, memory_bank_service, router, use_case
    ) -> None:
        """Registry-only bank, db unreadable → stored status + description + stored memory_count KEPT."""
        memory_bank_service.list_memory_banks.return_value = Result.ok(
            [_bank("reg-only", description="Stored description", status="suspended", memory_count=4)]
        )
        router.get_stats_for.return_value = Result.ko(
            [ErrorWithDetails("MEMORY_BANK_DB_NOT_FOUND", {"bank": "reg-only"})]
        )

        result = use_case.execute({})

        assert result.is_ok is True
        bank = result.value["banks"][0]
        assert bank["name"] == "reg-only"
        assert bank["status"] == "suspended"
        assert bank["description"] == "Stored description"
        assert bank["memory_count"] == 4

    def test_registry_only_bank_with_db_gets_live_memory_count(
        self, memory_bank_service, router, use_case
    ) -> None:
        """Registry-only bank with a readable db → live total_memories overrides stale stored count."""
        memory_bank_service.list_memory_banks.return_value = Result.ok(
            [_bank("reg-only", description="Stored description", status="registered", memory_count=4)]
        )
        router.get_stats_for.return_value = Result.ok({"total_memories": 252})

        result = use_case.execute({})

        assert result.is_ok is True
        bank = result.value["banks"][0]
        assert bank["name"] == "reg-only"
        assert bank["status"] == "registered"
        assert bank["memory_count"] == 252

    def test_bank_in_pool_is_active_with_live_memory_count(self, router, use_case) -> None:
        """Pool bank → status='active' + live memory_count from get_stats."""
        client = MagicMock()
        client.memory_bank = "pooled"
        client.get_stats.return_value = Result.ok({"total_memories": 11})
        router.instances = {"pooled": client}

        result = use_case.execute({})

        assert result.is_ok is True
        bank = result.value["banks"][0]
        assert bank["name"] == "pooled"
        assert bank["status"] == "active"
        assert bank["memory_count"] == 11
        router.get_stats_for.assert_not_called()

    def test_duplicate_names_deduped_precedence_active(self, router, memory_bank_service, use_case) -> None:
        """A bank in ALL three sources yields exactly ONE entry, status active (pool wins),
        description from registry, live memory_count."""
        client = MagicMock()
        client.memory_bank = "shared"
        client.get_stats.return_value = Result.ok({"total_memories": 9})
        router.instances = {"shared": client}
        router.list_bank_dirs.return_value = ["shared"]
        memory_bank_service.list_memory_banks.return_value = Result.ok(
            [_bank("shared", description="Stored desc", status="suspended", memory_count=2)]
        )

        result = use_case.execute({})

        assert result.is_ok is True
        banks = result.value["banks"]
        assert len(banks) == 1
        bank = banks[0]
        assert bank["name"] == "shared"
        assert bank["status"] == "active"
        assert bank["memory_count"] == 9
        assert bank["description"] == "Stored desc"
        router.get_stats_for.assert_not_called()

    def test_all_entries_have_shape_with_name_equal_bank(self, router, memory_bank_service, use_case) -> None:
        """Every entry is {name, bank, description, memory_count, status} with name == bank."""
        client = MagicMock()
        client.memory_bank = "pooled"
        client.get_stats.return_value = Result.ok({"total_memories": 3})
        router.instances = {"pooled": client}
        router.list_bank_dirs.return_value = ["disk-only"]
        memory_bank_service.list_memory_banks.return_value = Result.ok(
            [_bank("reg-only", description="desc", status="registered", memory_count=1)]
        )
        router.get_stats_for.return_value = Result.ko(
            [ErrorWithDetails("MEMORY_BANK_DB_NOT_FOUND", {"bank": "reg-only"})]
        )

        result = use_case.execute({})

        required_fields = {"name", "bank", "description", "memory_count", "status"}
        assert len(result.value["banks"]) == 3
        for bank in result.value["banks"]:
            assert set(bank.keys()) == required_fields
            assert bank["name"] == bank["bank"]


class TestListBanksStatsConsumption:
    """Test that ListBanksUseCase consumes get_stats() as a Result[dict].

    get_stats() returns Result[dict[str, Any]]; the canonical count is
    "total_memories" in the ok value. The use case must unwrap the Result and
    read total_memories, defaulting to 0 on ko or missing key.
    """

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    def _build_use_case(self, get_stats_result, logger) -> ListBanksUseCase:
        client = MagicMock()
        client.memory_bank = "default"
        client.get_stats.return_value = get_stats_result

        router = MagicMock()
        router.instances = {"default": client}
        router.list_bank_dirs.return_value = []

        memory_bank_service = MagicMock()
        memory_bank_service.list_memory_banks.return_value = Result.ok([])
        return ListBanksUseCase(
            memory_bank_service=memory_bank_service,
            router=router,
            logger=logger,
        )

    def test_memory_count_from_total_memories_when_ok(self, logger) -> None:
        """Result.ok({'total_memories': 5}) → memory_count == 5."""
        use_case = self._build_use_case(
            Result.ok({"total_memories": 5, "mode": "beam"}), logger
        )

        result = use_case.execute({})

        bank = result.value["banks"][0]
        assert bank["memory_count"] == 5

    def test_memory_count_zero_when_stats_is_ko(self, logger) -> None:
        """Result.ko(...) → memory_count == 0."""
        use_case = self._build_use_case(
            Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": "boom"})]),
            logger,
        )

        result = use_case.execute({})

        bank = result.value["banks"][0]
        assert bank["memory_count"] == 0

    def test_memory_count_zero_when_total_memories_absent(self, logger) -> None:
        """Result.ok without total_memories key → memory_count == 0."""
        use_case = self._build_use_case(Result.ok({"mode": "beam", "banks": ["default"]}), logger)

        result = use_case.execute({})

        bank = result.value["banks"][0]
        assert bank["memory_count"] == 0
