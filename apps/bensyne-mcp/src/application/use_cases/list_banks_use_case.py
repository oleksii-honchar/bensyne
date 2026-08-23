"""ListBanksUseCase — merged bank listing (filesystem ∪ pool ∪ registry).

Returns a deduped list of bank entries from three sources (DEC-0065, fixes the
2-vs-5 live mismatch):

- ``router.list_bank_dirs()`` — filesystem scan (a bank exists on disk)
- ``router.instances`` — the client instance pool (a bank is active right now)
- ``memory_bank_service.list_memory_banks()`` — memory_banks.db (stored
  description / status / memory_count)

Status precedence: ``active`` (pool) > stored status (``registered`` /
``suspended``) > ``on_disk``. Entry shape is ``{name, bank, description,
memory_count, status}`` with ``name == bank``.
"""

from typing import TYPE_CHECKING

import structlog.stdlib
from src.application.use_cases.base_use_case import BaseUseCase
from src.utils.result import Result

if TYPE_CHECKING:
    from src.application.services.memory_bank_service import MemoryBankService
    from src.infrastructure.bank.router import MemoryBankRouter


class ListBanksUseCase(BaseUseCase[dict, dict]):
    """Orchestrates the merged bank listing via MemoryBankService + MemoryBankRouter."""

    def __init__(
        self,
        memory_bank_service: "MemoryBankService",
        router: "MemoryBankRouter",
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        super().__init__(logger)
        self.memory_bank_service = memory_bank_service
        self.router = router

    def validate_params(self, parameters: dict) -> Result[dict]:
        """ListBanksUseCase requires no parameters."""
        return Result.ok(parameters)

    def _entry(self, name: str, description: str, memory_count: int, status: str) -> dict:
        """Build a list entry in the canonical shape (name == bank)."""
        return {
            "name": name,
            "bank": name,
            "description": description,
            "memory_count": memory_count,
            "status": status,
        }

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Build the merged, deduped bank listing (status precedence active > stored > on_disk)."""
        self.logger.info(
            "Listing banks",
            use_case="list_banks",
            method="execute_internal",
        )

        banks: dict[str, dict] = {}

        # 1. Filesystem — lowest precedence (a bank dir exists; may be unregistered).
        for bank_name in self.router.list_bank_dirs():
            banks[bank_name] = self._entry(bank_name, "", 0, "on_disk")

        # 2. Registry (memory_banks.db) — stored description / status / count.
        stored_result = self.memory_bank_service.list_memory_banks()
        if stored_result.is_ok and stored_result.value is not None:
            for bank in stored_result.value:
                banks[bank.name] = self._entry(
                    bank.name,
                    bank.description,
                    bank.memory_count,
                    bank.status,
                )
        else:
            self.logger.warning(
                "Could not read stored memory banks; continuing with filesystem + pool",
                use_case="list_banks",
                method="execute_internal",
                errors=stored_result.get_formatted_errors(),
            )

        # 3. Pool — highest precedence: active + live memory_count from get_stats.
        for bank_name, client in self.router.instances.items():
            stats = client.get_stats()
            if stats.is_ok and stats.value is not None:
                memory_count = stats.value.get("total_memories", 0)
            else:
                memory_count = 0

            existing = banks.get(bank_name)
            description = existing["description"] if existing else ""
            banks[bank_name] = self._entry(bank_name, description, memory_count, "active")

        result = [banks[name] for name in sorted(banks)]

        self.logger.info(
            "Banks listed",
            use_case="list_banks",
            method="execute_internal",
            banks_count=len(result),
        )

        return Result.ok({"banks": result})
