"""MemoryBankService — application service orchestrating memory bank business ops.

The SOLE business API for bank operations (U7/U14): pure orchestration over
``MemoryBankRepository`` + the ``MemoryBank`` aggregate. No path resolution,
no client-instance management, no infrastructure wiring — those concerns
live in the infrastructure layer. Pattern: ``FileService`` (application
service over infrastructure repositories).

Business rules (spec §4.3):
- ``register_memory_bank`` — existing row → ``update_description`` + save;
  absent → ``MemoryBank.of`` + save. Validation failures propagate as
  ``Result.ko`` (``INVALID_MEMORY_BANK`` from the aggregate/domain, never
  swallowed).
- ``ensure_default_bank`` — idempotent startup seed: creates the ``default``
  row only when absent; NEVER overwrites an existing description. Repository
  errors are logged, not raised.
"""

from __future__ import annotations

import structlog.stdlib
from src.domain.memory_bank_aggregate import MemoryBank
from src.infrastructure.bank.memory_bank_repository import MemoryBankRepository
from src.utils.result import ErrorWithDetails, Result


class MemoryBankService:
    """Application service for memory bank operations — the bank layer's business API.

    Every operation is: read via the repository → a domain mutation (via
    ``MemoryBank.of`` / ``update_description``) → one ``save``. All business
    operations return ``Result[T]``; ``ensure_default_bank`` is a fire-and-forget
    seed (repository errors logged, never raised).
    """

    def __init__(
        self,
        memory_bank_repository: MemoryBankRepository,
        logger: structlog.stdlib.BoundLogger,
    ) -> None:
        self.memory_bank_repository = memory_bank_repository
        self._logger = logger

    # ------------------------------------------------------------------
    # Structured logging helpers
    # ------------------------------------------------------------------

    def _log_info(self, event: str, **kwargs: object) -> None:
        """Emit an info-level structured log entry."""
        self._logger.info(event, service="memory_bank_service", **kwargs)

    def _log_debug(self, event: str, **kwargs: object) -> None:
        """Emit a debug-level structured log entry."""
        self._logger.debug(event, service="memory_bank_service", **kwargs)

    # ------------------------------------------------------------------
    # Business operations
    # ------------------------------------------------------------------

    def register_memory_bank(self, name: str, description: str) -> Result[MemoryBank]:
        """Register a memory bank: create on absent, update description on existing.

        Existing row (via ``find_by_id``) → ``update_description(description)`` +
        save; absent → ``MemoryBank.of(name, description)`` + save. Validation
        failures from the aggregate/domain propagate as ``Result.ko``
        (``INVALID_MEMORY_BANK``) — never swallowed.
        """
        self._log_info(
            "Registering memory bank", method="register_memory_bank", name=name
        )

        existing_result = self.memory_bank_repository.find_by_id(name)
        if existing_result.is_ko:
            return existing_result  # type: ignore[return-value]

        existing = existing_result.value
        if existing is not None:
            updated_result = existing.update_description(description)
            if updated_result.is_ko:
                return updated_result  # type: ignore[return-value]
            updated = updated_result.value
            if updated is None:
                return Result.ko(
                    [ErrorWithDetails("INVALID_MEMORY_BANK", {"name": name})]
                )  # type: ignore[return-value]
            save_result = self.memory_bank_repository.save(updated)
            if save_result.is_ko:
                return save_result  # type: ignore[return-value]
            self._log_info(
                "Memory bank updated",
                method="register_memory_bank",
                name=name,
                description=description,
            )
            return updated_result

        created_result = MemoryBank.of(name, description)
        if created_result.is_ko:
            return created_result  # type: ignore[return-value]
        created = created_result.value
        if created is None:
            return Result.ko(
                [ErrorWithDetails("INVALID_MEMORY_BANK", {"name": name})]
            )  # type: ignore[return-value]
        save_result = self.memory_bank_repository.save(created)
        if save_result.is_ko:
            return save_result  # type: ignore[return-value]
        self._log_info(
            "Memory bank registered",
            method="register_memory_bank",
            name=name,
            status=created.status,
        )
        return created_result

    def get_memory_bank(self, name: str) -> Result[MemoryBank | None]:
        """Return the bank by name (``None`` when absent) — repository delegate."""
        self._log_info("Getting memory bank", method="get_memory_bank", name=name)
        return self.memory_bank_repository.find_by_id(name)

    def list_memory_banks(self) -> Result[list[MemoryBank]]:
        """Return all banks — repository delegate."""
        self._log_info("Listing memory banks", method="list_memory_banks")
        return self.memory_bank_repository.list()

    def ensure_default_bank(self, description: str) -> None:
        """Idempotent startup seed for the ``default`` bank.

        Creates the ``default`` row only when absent; NEVER overwrites an
        existing description. Repository errors are logged (not raised) so a
        storage failure cannot abort server boot.
        """
        find_result = self.memory_bank_repository.find_by_id("default")
        if find_result.is_ko:
            self._logger.error(
                "Default bank lookup failed",
                service="memory_bank_service",
                method="ensure_default_bank",
                errors=find_result.get_formatted_errors(),
            )
            return
        if find_result.value is not None:
            self._log_debug(
                "Default bank already present, skipping seed",
                method="ensure_default_bank",
                name="default",
            )
            return

        created_result = MemoryBank.of("default", description)
        if created_result.is_ko:
            self._logger.error(
                "Default bank seed rejected",
                service="memory_bank_service",
                method="ensure_default_bank",
                errors=created_result.get_formatted_errors(),
            )
            return
        created = created_result.value
        if created is None:
            self._logger.error(
                "Default bank seed rejected",
                service="memory_bank_service",
                method="ensure_default_bank",
                errors=created_result.get_formatted_errors(),
            )
            return

        save_result = self.memory_bank_repository.save(created)
        if save_result.is_ko:
            self._logger.error(
                "Default bank seed save failed",
                service="memory_bank_service",
                method="ensure_default_bank",
                errors=save_result.get_formatted_errors(),
            )
            return
        self._log_info(
            "Default bank seeded",
            method="ensure_default_bank",
            name="default",
            status=created.status,
        )
