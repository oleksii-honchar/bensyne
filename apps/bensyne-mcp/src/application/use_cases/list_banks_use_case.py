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
from src.utils.result import ErrorWithDetails, Result

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

    MAX_LIMIT: int = 1000

    def validate_params(self, parameters: dict) -> Result[dict]:
        """Validate optional pagination/enrichment parameters.

        - ``limit``: optional int 1..1000 (None/absent = full enumeration).
        - ``offset``: optional int >= 0 (default 0).
        - ``enrich``: optional bool (default True). ``False`` returns the
          cheap merged skeleton WITHOUT the per-bank live-count walk — used
          by discovery (SearchMemoryBankUseCase) which ranks on name +
          description only.
        """
        limit = parameters.get("limit")
        if limit is not None and (
            not isinstance(limit, int)
            or isinstance(limit, bool)
            or limit < 1
            or limit > self.MAX_LIMIT
        ):
            return Result.ko([ErrorWithDetails("INVALID_LIMIT", {"limit": limit})])

        offset = parameters.get("offset", 0)
        if offset is None:
            offset = 0
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            return Result.ko([ErrorWithDetails("INVALID_OFFSET", {"offset": offset})])

        enrich = parameters.get("enrich", True)
        if not isinstance(enrich, bool):
            return Result.ko([ErrorWithDetails("INVALID_ENRICH", {"enrich": enrich})])

        merged = dict(parameters)
        merged["limit"] = limit
        merged["offset"] = offset
        merged["enrich"] = enrich
        return Result.ok(merged)

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

        # 4. Slice-BOUND live enrichment (Plan 8): the merged view above is the
        # cheap skeleton; the per-bank router.get_stats_for walk (transient
        # full client per bank — the measured ~20 s path at ~900 banks) runs
        # ONLY for entries actually returned. With ``enrich=False`` the
        # skeleton is returned as-is (discovery ranks on name + description).
        # (R6: the router resolves the memory entity from the incoming bank
        # name.) On ko (missing/corrupt db) keep the stored value (ADR-7
        # honest fallback).
        names = sorted(banks)
        total = len(names)
        offset: int = parameters.get("offset", 0)
        limit: int | None = parameters.get("limit")
        page = names[offset : offset + limit] if limit is not None else names[offset:]

        if parameters.get("enrich", True):
            for bank_name in page:
                entry = banks[bank_name]
                if entry["status"] == "active":
                    continue
                stats_result = self.router.get_stats_for(bank_name)
                if stats_result.is_ok and stats_result.value is not None:
                    entry["memory_count"] = stats_result.value.get("total_memories", 0)
                else:
                    self.logger.warning(
                        "Could not read live memory count; keeping stored value",
                        use_case="list_banks",
                        method="execute_internal",
                        memory_bank=bank_name,
                        errors=stats_result.get_formatted_errors(),
                    )

        result = [banks[name] for name in page]

        self.logger.info(
            "Banks listed",
            use_case="list_banks",
            method="execute_internal",
            banks_count=len(result),
            total=total,
            offset=offset,
            limit=limit,
            enriched=parameters.get("enrich", True),
        )

        return Result.ok({"banks": result, "total": total})
