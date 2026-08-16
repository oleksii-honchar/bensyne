"""SleepUseCase — triggers memory consolidation.

Delegates to MnemosyneClient.sleep() and returns Result with
merged result dict and memory_bank.
"""

import structlog.stdlib
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.application.use_cases.base_use_case import BaseUseCase
from src.utils.result import Result


class SleepUseCase(BaseUseCase[dict, dict]):
    """Orchestrates memory consolidation via MnemosyneClient."""

    def __init__(self, mnemosyne_client: MnemosyneClient, logger: structlog.stdlib.BoundLogger) -> None:
        super().__init__(logger)
        self.mnemosyne_client = mnemosyne_client

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Sleep has no required parameters — always passes validation."""
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Execute sleep via MnemosyneClient."""
        memory_bank = parameters.get("memory_bank", "default")

        sleep_result = self.mnemosyne_client.sleep()
        if not sleep_result.is_ok:
            return sleep_result

        return Result.ok(
            {
                "result": sleep_result.value,
                "memory_bank": memory_bank,
            }
        )
