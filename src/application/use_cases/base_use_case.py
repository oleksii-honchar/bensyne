"""Base use case class for the application layer.

All use cases inherit from BaseUseCase which provides the
execute / validate_params / execute_internal pattern with
Result-based error handling and structured logging.
"""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

import structlog.stdlib
from src.domain.exceptions import DomainException
from src.domain.result import ErrorWithDetails, Result

Params = TypeVar("Params")
ReturnType = TypeVar("ReturnType")


class BaseUseCase(ABC, Generic[Params, ReturnType]):
    """Base use case class for application layer."""

    def __init__(self, logger: structlog.stdlib.BoundLogger) -> None:
        self.logger = logger

    def execute(self, parameters: Params) -> Result[ReturnType]:
        try:
            validation_result = self.validate_params(parameters)
            if not validation_result.is_ok:
                return validation_result
            return self.execute_internal(validation_result.value)  # type: ignore[arg-type]
        except DomainException as e:
            self.logger.error(f"Domain error in {self.__class__.__name__}: {e}")
            return Result.ko([ErrorWithDetails(e.code, e.details)])
        except Exception as e:
            self.logger.error(f"Unexpected error in {self.__class__.__name__}: {e}")
            return Result.ko([ErrorWithDetails("INTERNAL_ERROR", {"message": str(e)})])

    @abstractmethod
    def validate_params(self, parameters: Params) -> Result[Params]:
        """Validate input parameters and return Result[Params]."""

    @abstractmethod
    def execute_internal(self, parameters: Params) -> Result[ReturnType]:
        """Execute the core use case logic and return Result[ReturnType]."""
