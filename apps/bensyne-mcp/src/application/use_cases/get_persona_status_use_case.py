"""GetPersonaStatusUseCase — persona bank materialization signal (spec §4.4, ADR-8).

Counts every memory in a persona bank and classifies it into exactly one of
three buckets, then derives the materialization signal:

  * node_memories               — file-backed (the memory id appears in the
                                  bank's file_chunks index)
  * occasional_memories         — non-file, non-expired (valid_until null or
                                  still in the future) — the pending experiences
  * expired_occasional_memories — non-file, valid_until in the past

``materialization_due`` is True when ``occasional_memories >= materialization_threshold``
(expired experiences never count). File association wins over temporality: a
file-backed memory is always a node, even if its valid_until is in the past.
"""

from __future__ import annotations

from datetime import datetime

import structlog.stdlib
from src.application.use_cases.base_use_case import BaseUseCase
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.utils.result import ErrorWithDetails, Result

# Default accumulation threshold before persona materialization is due. Tunable
# at runtime via the BENSYNE_PERSONA_MATERIALIZATION_THRESHOLD env var (handler
# reads it); the default 10 is a pilot starting point (spec §8 open decision 3).
DEFAULT_MATERIALIZATION_THRESHOLD = 10


def _valid_until_in_past(valid_until: str | None, now) -> bool:
    """True when the memory's valid_until is set and strictly in the past.

    Unparseable expiries fail toward "not expired" so an occasional memory is
    never silently dropped from the pending set over a format surprise.
    """
    if not valid_until:
        return False
    raw = str(valid_until).strip()
    candidate = raw[:-1] + "+00:00" if raw.endswith("Z") else raw
    try:
        parsed = datetime.fromisoformat(candidate)
    except (ValueError, TypeError):
        return False
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed < now


class GetPersonaStatusUseCase(BaseUseCase[dict, dict]):
    """Orchestrates the persona bank status counts and materialization signal."""

    def __init__(
        self,
        mnemosyne_client: MnemosyneClient,
        file_chunk_repository: FileChunkRepository,
        logger: structlog.stdlib.BoundLogger,
        materialization_threshold: int = DEFAULT_MATERIALIZATION_THRESHOLD,
    ) -> None:
        super().__init__(logger)
        self.mnemosyne_client = mnemosyne_client
        self.file_chunk_repository = file_chunk_repository
        self.materialization_threshold = materialization_threshold

    def validate_params(self, parameters: dict) -> Result[dict]:
        """memory_bank is mandatory — missing/empty is a validation error."""
        memory_bank = parameters.get("memory_bank")
        if not memory_bank:
            return Result.ko([ErrorWithDetails("MEMORY_BANK_REQUIRED", {})])
        return Result.ok(parameters)

    def execute_internal(self, parameters: dict) -> Result[dict]:
        """Classify every memory and derive the materialization signal."""
        now = datetime.now()

        # (memory_id, valid_until) for every memory in the bank (incl. expired).
        validities = self.mnemosyne_client.list_memory_validities()
        file_backed_ids = self.file_chunk_repository.get_file_backed_memory_ids()

        total = 0
        node_memories = 0
        occasional_memories = 0
        expired_occasional_memories = 0

        for memory_id, valid_until in validities:
            total += 1
            if memory_id in file_backed_ids:
                # File association wins: a node, regardless of its valid_until.
                node_memories += 1
            elif _valid_until_in_past(valid_until, now):
                expired_occasional_memories += 1
            else:
                occasional_memories += 1

        return Result.ok(
            {
                "total": total,
                "node_memories": node_memories,
                "occasional_memories": occasional_memories,
                "expired_occasional_memories": expired_occasional_memories,
                "materialization_due": occasional_memories >= self.materialization_threshold,
            }
        )
