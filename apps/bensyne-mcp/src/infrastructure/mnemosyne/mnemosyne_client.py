"""MnemosyneClient — Result-returning wrapper around the external Mnemosyne library.

Replaces the current client that returns raw dicts. Each method wraps the
library's call with try/except, converting exceptions to Result.ko with
DATABASE_ERROR.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.domain.memory_entity import Memory

from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import get_logger

logger = get_logger(__name__)


class MnemosyneClient:
    """Wrapper for external Mnemosyne service (library).

    Wraps the library's remember/recall/forget/update/sleep/stats methods
    with Result-based error handling.
    """

    def __init__(self, memory_bank: str, data_dir: str = "/data/mnemosyne") -> None:
        self.memory_bank = memory_bank
        self.created_at = time.time()
        self.last_accessed = time.time()
        self._instance = self._create_instance(memory_bank=memory_bank, data_dir=data_dir)

    def _create_instance(self, memory_bank: str, data_dir: str) -> Any:
        """Create the underlying Mnemosyne library instance.

        Overridable in tests via monkeypatch/patch.
        """
        # Lazy import to avoid pulling in mnemosyne at import time
        from mnemosyne.core.memory import Mnemosyne

        # Resolve db_path: default bank goes to data_dir/mnemosyne.db,
        # custom bank goes to data_dir/banks/{memory_bank}/mnemosyne.db
        data_path = Path(data_dir)
        if memory_bank == "default":
            db_path = data_path / "mnemosyne.db"
        else:
            db_path = data_path / "banks" / memory_bank / "mnemosyne.db"
            db_path.parent.mkdir(parents=True, exist_ok=True)

        logger.info("Initializing MnemosyneClient", memory_bank=memory_bank, db_path=str(db_path))
        return Mnemosyne(bank=memory_bank, db_path=str(db_path))

    # ------------------------------------------------------------------
    # Domain repository interface (called by use cases)
    # ------------------------------------------------------------------

    def save(self, memory: "Memory") -> Result["Memory"]:
        """Persist a Memory entity via the underlying Mnemosyne instance.

        Returns Result.ok(memory) with the actual memory_id from Mnemosyne.
        The returned Memory may have a different id than the input.
        """
        try:
            actual_id = self._instance.remember(
                content=memory.content,
                source=memory.source,
                importance=memory.importance,
            )
            # Use the actual ID from Mnemosyne — the input may have a placeholder
            from src.domain.memory_entity import Memory

            saved_memory = Memory(
                id=actual_id,
                content=memory.content,
                importance=memory.importance,
                source=memory.source,
                scope=memory.scope,
                created_at=memory.created_at,
                updated_at=memory.updated_at,
                veracity=memory.veracity,
                metadata=memory.metadata,
            )
            return Result.ok(saved_memory)
        except Exception as exc:
            logger.error("Mnemosyne save failed", memory_bank=self.memory_bank, memory_id=memory.id, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])

    # ------------------------------------------------------------------
    # Public API — all methods return Result
    # ------------------------------------------------------------------

    def remember(self, **kwargs: Any) -> Result[dict[str, Any]]:
        """Store a durable memory."""
        try:
            value = self._instance.remember(**kwargs)
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne remember failed", memory_bank=self.memory_bank, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])

    def recall(self, query: str, limit: int = 5) -> Result[list[dict[str, Any]]]:
        """Search for relevant memories."""
        try:
            value = self._instance.recall(query=query, top_k=limit)
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne recall failed", memory_bank=self.memory_bank, query=query, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])

    def forget(self, memory_id: str) -> Result[dict[str, Any]]:
        """Delete a memory."""
        try:
            value = self._instance.forget(memory_id=memory_id)
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne forget failed", memory_bank=self.memory_bank, memory_id=memory_id, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])

    def update(self, memory_id: str, **kwargs: Any) -> Result[dict[str, Any]]:
        """Update memory content or importance."""
        try:
            value = self._instance.update(memory_id=memory_id, **kwargs)
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne update failed", memory_bank=self.memory_bank, memory_id=memory_id, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])

    def sleep(self) -> Result[dict[str, Any]]:
        """Trigger memory consolidation."""
        try:
            value = self._instance.sleep()
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne sleep failed", memory_bank=self.memory_bank, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])

    def stats(self) -> Result[dict[str, Any]]:
        """Return memory statistics."""
        try:
            value = self._instance.stats()
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne stats failed", memory_bank=self.memory_bank, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])
