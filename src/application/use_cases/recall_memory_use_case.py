"""RecallMemoryUseCase — searches memories via MnemosyneClient.

Validates non-empty query, delegates to MnemosyneClient.recall,
and returns Result with results and memory_bank.
"""

import structlog.stdlib
from src.infrastructure.mnemosyne.client import MnemosyneClient
from src.application.use_cases.base_use_case import BaseUseCase
from src.domain.result import ErrorWithDetails, Result


class RecallMemoryUseCase(BaseUseCase[dict, dict]):
    """Orchestrates memory recall via MnemosyneClient."""

    def __init__(self, mnemosyne_client: MnemosyneClient, logger: structlog.stdlib.BoundLogger) -> None:
        super().__init__(logger)
        self.mnemosyne_client = mnemosyne_client

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate that query is present and non-empty."""
        if not parameters.get("query"):
            return Result.ko([ErrorWithDetails("QUERY_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute recall via MnemosyneClient."""
        query = parameters["query"]
        limit = parameters.get("limit", 10)
        memory_bank = parameters.get("memory_bank", "default")

        results = self.mnemosyne_client.recall(query, limit)

        return Result.ok({
            "results": results,
            "memory_bank": memory_bank,
        })
