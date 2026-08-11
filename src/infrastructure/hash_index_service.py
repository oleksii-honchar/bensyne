"""HashIndexService — Result-returning wrapper around HashIndex for deduplication.

Wraps the SQLite-backed HashIndex from src/services/tools/dedup_index.py with
Result-based error handling. All exceptions are caught and converted to
Result.ko with HASH_INDEX_ERROR.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from src.domain.result import ErrorWithDetails, Result
from src.services.tools.dedup_index import HashIndex
from src.utils.structured_logging import get_logger

logger = get_logger(__name__)


class HashIndexService:
    """Result-returning wrapper around HashIndex for file hash deduplication.

    Maps file hashes to memory IDs to detect duplicate memories.
    """

    def __init__(self, memory_bank: str, db_path: Optional[Path] = None) -> None:
        self.memory_bank = memory_bank
        if db_path is None:
            db_path = Path("data") / memory_bank / "hash_index.db"
        self._index = HashIndex(db_path)

    def store(self, hash_value: str, memory_id: str) -> Result[None]:
        """Store a hash-to-memory_id mapping.

        Args:
            hash_value: The SHA-256 hash to index.
            memory_id: The memory ID to associate with the hash.

        Returns:
            Result.ok(None) on success, Result.ko on error.
        """
        try:
            self._index.store(hash_value, memory_id)
            return Result.ok(None)
        except Exception as exc:
            logger.error("HashIndex store failed", memory_bank=self.memory_bank, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("HASH_INDEX_ERROR", {"detail": str(exc)})])

    def lookup(self, hash_value: str) -> Result[Optional[str]]:
        """Look up a memory ID by file hash.

        Args:
            hash_value: The SHA-256 hash to look up.

        Returns:
            Result.ok(memory_id) if found, Result.ok(None) if not found,
            Result.ko on error.
        """
        try:
            memory_id = self._index.lookup(hash_value)
            return Result.ok(memory_id)
        except Exception as exc:
            logger.error("HashIndex lookup failed", memory_bank=self.memory_bank, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("HASH_INDEX_ERROR", {"detail": str(exc)})])

    def remove(self, memory_id: str) -> Result[Optional[str]]:
        """Remove the hash mapping for a memory.

        Args:
            memory_id: The memory ID to remove from the index.

        Returns:
            Result.ok(hash) with the removed hash if found, Result.ok(None) if
            not found, Result.ko on error.
        """
        try:
            removed_hash = self._index.remove(memory_id)
            return Result.ok(removed_hash)
        except Exception as exc:
            logger.error("HashIndex remove failed", memory_bank=self.memory_bank, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("HASH_INDEX_ERROR", {"detail": str(exc)})])
