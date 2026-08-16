"""RegisterBankUseCase — registers a memory bank via the MemoryBankRouter.

Validates name and description, then delegates to router.register_bank().
Returns Result with status='registered' and the bank name.
"""

from typing import TYPE_CHECKING

import structlog.stdlib
from src.application.use_cases.base_use_case import BaseUseCase
from src.utils.result import ErrorWithDetails, Result

if TYPE_CHECKING:
    from src.infrastructure.bank.router import MemoryBankRouter


class RegisterBankUseCase(BaseUseCase[dict, dict]):
    """Orchestrates memory bank registration via MemoryBankRouter."""

    def __init__(self, router: "MemoryBankRouter", logger: structlog.stdlib.BoundLogger) -> None:
        super().__init__(logger)
        self.router = router

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that name and description are present and non-empty."""
        if not parameters.get("name"):
            return Result.ko([ErrorWithDetails("NAME_REQUIRED", {})])
        if not parameters.get("description"):
            return Result.ko([ErrorWithDetails("DESCRIPTION_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Register the bank via the router."""
        name = parameters["name"]
        description = parameters["description"]

        self.logger.info(
            "Registering bank",
            use_case="register_bank",
            method="execute_internal",
            name=name,
        )

        self.router.register_bank(name, description)

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
