"""Unit tests for ListBanksUseCase and RegisterBankUseCase."""

from unittest.mock import MagicMock

import pytest

from src.application.use_cases.list_banks_use_case import ListBanksUseCase
from src.application.use_cases.register_bank_use_case import RegisterBankUseCase
from src.domain.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock


class TestRegisterBankUseCase:
    """Test RegisterBankUseCase validation and registration logic."""

    @pytest.fixture
    def router(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(self, router, logger) -> RegisterBankUseCase:
        return RegisterBankUseCase(
            router=router,
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

    def test_execute_registers_bank_via_router(self, use_case, router) -> None:
        """Successful execution should call router.register_bank with name and description."""
        result = use_case.execute({"name": "my-bank", "description": "A test bank"})

        assert result.is_ok is True
        router.register_bank.assert_called_once_with("my-bank", "A test bank")

    def test_execute_returns_registered_status_and_name(self, use_case) -> None:
        """Result should contain status='registered' and the bank name."""
        result = use_case.execute({"name": "my-bank", "description": "A test bank"})

        assert result.is_ok is True
        assert result.value["status"] == "registered"
        assert result.value["name"] == "my-bank"

    def test_execute_returns_ko_when_name_empty(self, use_case) -> None:
        """Execute with empty name should return Result.ko without calling router."""
        result = use_case.execute({"name": "", "description": "desc"})

        assert result.is_ko is True
        assert result.errors[0].error_code == "NAME_REQUIRED"

    def test_execute_returns_ko_when_description_empty(self, use_case) -> None:
        """Execute with empty description should return Result.ko without calling router."""
        result = use_case.execute({"name": "my-bank", "description": ""})

        assert result.is_ko is True
        assert result.errors[0].error_code == "DESCRIPTION_REQUIRED"


class TestListBanksUseCase:
    """Test ListBanksUseCase bank listing logic."""

    @pytest.fixture
    def router(self) -> MagicMock:
        router = MagicMock()
        # Simulate active instances: "default" and "ns1"
        mock_default = MagicMock()
        mock_default.memory_bank = "default"
        mock_default.stats.return_value = {"working": 5, "episodic": 3}

        mock_ns1 = MagicMock()
        mock_ns1.memory_bank = "ns1"
        mock_ns1.stats.return_value = {"working": 10, "episodic": 0}

        router.instances = {
            "default": mock_default,
            "ns1": mock_ns1,
        }
        # Simulate registry: "default", "ns1", and "ns2" (registered but not active)
        router.registry.list_banks.return_value = ["default", "ns1", "ns2"]
        router.get_bank_description.side_effect = lambda name: {
            "default": "Default personal memory",
            "ns1": "Namespace one",
            "ns2": "Namespace two",
        }.get(name)

        return router

    @pytest.fixture
    def logger(self) -> LoggerMock:
        return LoggerMock()

    @pytest.fixture
    def use_case(self, router, logger) -> ListBanksUseCase:
        return ListBanksUseCase(
            router=router,
            logger=logger,
        )

    # -- Validation --

    def test_validate_params_accepts_empty_params(self, use_case) -> None:
        """ListBanksUseCase requires no parameters, so empty dict passes."""
        result = use_case.validate_params({})

        assert result.is_ok is True

    # -- Execution --

    def test_execute_returns_merged_active_and_registered_banks(self, use_case) -> None:
        """Result should include both active instances and registered-only banks."""
        result = use_case.execute({})

        assert result.is_ok is True
        banks = result.value["banks"]
        names = {b["name"] for b in banks}
        # All three: default (active), ns1 (active), ns2 (registered only)
        assert names == {"default", "ns1", "ns2"}

    def test_execute_active_banks_have_status_active(self, use_case) -> None:
        """Active instances should have status='active'."""
        result = use_case.execute({})
        banks = result.value["banks"]

        for bank in banks:
            if bank["name"] in ("default", "ns1"):
                assert bank["status"] == "active"

    def test_execute_registered_only_banks_have_status_registered(self, use_case) -> None:
        """Banks that are registered but not active should have status='registered'."""
        result = use_case.execute({})
        banks = result.value["banks"]

        ns2 = next(b for b in banks if b["name"] == "ns2")
        assert ns2["status"] == "registered"

    def test_execute_active_banks_include_memory_count(self, use_case) -> None:
        """Active banks should include memory_count from stats."""
        result = use_case.execute({})
        banks = result.value["banks"]

        default_bank = next(b for b in banks if b["name"] == "default")
        assert default_bank["memory_count"] == 8  # 5 working + 3 episodic

        ns1_bank = next(b for b in banks if b["name"] == "ns1")
        assert ns1_bank["memory_count"] == 10  # 10 working + 0 episodic

    def test_execute_registered_only_banks_have_zero_memory_count(self, use_case) -> None:
        """Registered-only banks should have memory_count=0."""
        result = use_case.execute({})
        banks = result.value["banks"]

        ns2 = next(b for b in banks if b["name"] == "ns2")
        assert ns2["memory_count"] == 0

    def test_execute_each_bank_has_required_fields(self, use_case) -> None:
        """Each bank entry should have name, bank, description, memory_count, status."""
        result = use_case.execute({})
        banks = result.value["banks"]

        required_fields = {"name", "bank", "description", "memory_count", "status"}
        for bank in banks:
            assert set(bank.keys()) == required_fields

    def test_execute_includes_description_from_router(self, use_case) -> None:
        """Each bank should include description from the router's registry."""
        result = use_case.execute({})
        banks = result.value["banks"]

        default_bank = next(b for b in banks if b["name"] == "default")
        assert default_bank["description"] == "Default personal memory"

        ns2 = next(b for b in banks if b["name"] == "ns2")
        assert ns2["description"] == "Namespace two"

    def test_execute_bank_field_matches_memory_bank(self, use_case) -> None:
        """The 'bank' field should match the client's memory_bank for active instances."""
        result = use_case.execute({})
        banks = result.value["banks"]

        default_bank = next(b for b in banks if b["name"] == "default")
        assert default_bank["bank"] == "default"

        ns1 = next(b for b in banks if b["name"] == "ns1")
        assert ns1["bank"] == "ns1"
