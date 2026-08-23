"""RegisterBankUseCase — registers a memory bank via MemoryBankService.

Validates name and description, then delegates to
``memory_bank_service.register_memory_bank()``. Business rules live in the
application service (create-on-absent, update-description-on-existing);
validation failures propagate as ``Result.ko``.
Returns Result with status='registered' and the bank name.
"""

from typing import TYPE_CHECKING

import structlog.stdlib
from src.application.use_cases.base_use_case import BaseUseCase
from src.utils.result import ErrorWithDetails, Result

if TYPE_CHECKING:
    from src.application.services.memory_bank_service import MemoryBankService


class RegisterBankUseCase(BaseUseCase[dict, dict]):
    """Orchestrates memory bank registration via MemoryBankService."""

    def __init__(
        self,
        memory_bank_service: "MemoryBankService",
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        super().__init__(logger)
        self.memory_bank_service = memory_bank_service

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that name and description are present and non-empty."""
        if not parameters.get("name"):
            return Result.ko([ErrorWithDetails("NAME_REQUIRED", {})])  # type: ignore[return-value]
        if not parameters.get("description"):
            return Result.ko([ErrorWithDetails("DESCRIPTION_REQUIRED", {})])  # type: ignore[return-value]
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Register the bank via the service."""
        name = parameters["name"]
        description = parameters["description"]

        self.logger.info(
            "Registering bank",
            use_case="register_bank",
            method="execute_internal",
            name=name,
        )

        result = self.memory_bank_service.register_memory_bank(name, description)
        if result.is_ko:
            return result  # type: ignore[return-value]

        self.logger.info(
            "Bank registered",
            use_case="register_bank",
            method="execute_internal",
            name=name,
        )

        return Result.ok(
            {
                "status": "registered",
                "name": name,
            }
        )
