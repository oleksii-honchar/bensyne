"""UpdateMemoryUseCase — updates a memory's content or importance.

Validates non-empty memory_id, delegates to MnemosyneClient.update,
and returns Result with status and memory_bank.
"""

import structlog.stdlib
from src.infrastructure.mnemosyne.client import MnemosyneClient
from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.result import ErrorWithDetails, Result


class UpdateMemoryUseCase(BaseUseCase[dict, dict]):
    """Orchestrates memory update via MnemosyneClient."""

    def __init__(self, mnemosyne_client: MnemosyneClient, logger: structlog.stdlib.BoundLogger) -> None:
        super().__init__(logger)
        self.mnemosyne_client = mnemosyne_client

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that memory_id is present and non-empty."""
        if not parameters.get("memory_id"):
            return Result.ko([ErrorWithDetails("MEMORY_ID_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute update via MnemosyneClient."""
        memory_id = parameters["memory_id"]
        content = parameters.get("content")
        importance = parameters.get("importance")
        memory_bank = parameters.get("memory_bank", "default")

        update_result = self.mnemosyne_client.update(
            memory_id, content=content, importance=importance
        )

        return Result.ok({
            "status": update_result["status"],
            "memory_bank": memory_bank,
        })
