"""Unit tests for BaseUseCase execute/validate_params/execute_internal pattern."""

from abc import abstractmethod
from typing import Generic, TypeVar

import pytest

from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.exceptions import DomainException
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock


ParamsT = TypeVar("ParamsT")
ReturnT = TypeVar("ReturnT")


class ConcreteUseCase(BaseUseCase[ParamsT, ReturnT], Generic[ParamsT, ReturnT]):
    """Concrete use case for testing BaseUseCase behavior."""

    def __init__(self, logger, validate_result=None, execute_result=None, raise_exc=None):
        super().__init__(logger)
        self._validate_result = validate_result
        self._execute_result = execute_result
        self._raise_exc = raise_exc

    def validate_params(self, parameters: ParamsT) -> Result[ParamsT]:
        if self._validate_result is not None:
            return self._validate_result
        return Result.ok(parameters)

    def execute_internal(self, parameters: ParamsT) -> Result[ReturnT]:
        if self._raise_exc is not None:
            raise self._raise_exc
        if self._execute_result is not None:
            return self._execute_result
        return Result.ok(parameters)  # type: ignore


class TestBaseUseCase:
    """Test the BaseUseCase execute pattern."""

    def test_execute_returns_ko_when_validate_params_fails(self) -> None:
        """execute() returns Result.ko when validate_params returns ko."""
        logger = LoggerMock()
        expected_error = ErrorWithDetails("INVALID_PARAM", {"field": "name"})
        validate_result = Result.ko([expected_error])
        use_case = ConcreteUseCase(logger, validate_result=validate_result)

        result = use_case.execute(None)  # type: ignore

        assert result.is_ko is True
        assert result.value is None
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "INVALID_PARAM"
        assert result.errors[0].details == {"field": "name"}

    def test_execute_returns_ko_when_execute_internal_raises_domain_exception(self) -> None:
        """execute() catches DomainException and returns Result.ko with error code and details."""
        logger = LoggerMock()
        exc = DomainException("DOMAIN_ERROR", {"reason": "invariant violated"})
        use_case = ConcreteUseCase(logger, raise_exc=exc)

        result = use_case.execute("params")

        assert result.is_ko is True
        assert result.value is None
        assert len(result.errors) == 1
        assert result.errors[0].error_code == "DOMAIN_ERROR"
        assert result.errors[0].details == {"reason": "invariant violated"}

    def test_execute_returns_ok_when_validation_and_execution_succeed(self) -> None:
        """execute() returns Result.ok when both validate_params and execute_internal succeed."""
        logger = LoggerMock()
        expected_value = "success_value"
        execute_result = Result.ok(expected_value)
        use_case = ConcreteUseCase(logger, execute_result=execute_result)

        result = use_case.execute("params")

        assert result.is_ok is True
        assert result.value == expected_value
        assert len(result.errors) == 0
