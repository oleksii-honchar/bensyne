"""ListBanksUseCase — lists all memory banks from the MemoryBankRouter.

Returns a merged list of active instances and registered banks with
status, memory_count, description, and bank fields.
"""

from typing import TYPE_CHECKING

import structlog.stdlib
from src.application.use_cases.base_use_case import BaseUseCase
from src.utils.result import Result

if TYPE_CHECKING:
    from src.infrastructure.bank.router import MemoryBankRouter


class ListBanksUseCase(BaseUseCase[dict, dict]):
    """Orchestrates listing of all memory banks via MemoryBankRouter."""

    def __init__(self, router: "MemoryBankRouter", logger: structlog.stdlib.BoundLogger) -> None:
        super().__init__(logger)
        self.router = router

    def validate_params(self, parameters: dict) -> Result[dict]:
        """ListBanksUseCase requires no parameters."""
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Build merged list of active instances and registered banks."""
        self.logger.info(
            "Listing banks",
            use_case="list_banks",
            method="execute_internal",
        )

        banks = []
        seen = set()

        # Active instances
        for bank_name, client in self.router.instances.items():
            description = self.router.get_bank_description(bank_name)

            stats = client.stats()
            memory_count = 0
            if isinstance(stats, dict):
                working = stats.get("working_count") or stats.get("working") or 0
                episodic = stats.get("episodic_count") or stats.get("episodic") or 0
                memory_count = working + episodic

            banks.append(
                {
                    "name": bank_name,
                    "bank": client.memory_bank,
                    "description": description or "",
                    "memory_count": memory_count,
                    "status": "active",
                }
            )
            seen.add(bank_name)

        # Registered but not active
        for bank_name in self.router.registry.list_banks():
            if bank_name not in seen:
                description = self.router.get_bank_description(bank_name)
                banks.append(
                    {
                        "name": bank_name,
                        "bank": bank_name,
                        "description": description or "",
                        "memory_count": 0,
                        "status": "registered",
                    }
                )

        self.logger.info(
            "Banks listed",
            use_case="list_banks",
            method="execute_internal",
            banks_count=len(banks),
        )

        return Result.ok({"banks": banks})
