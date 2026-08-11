"""MnemosyneClient — Result-returning wrapper around the external Mnemosyne library.

Replaces the current client that returns raw dicts. Each method wraps the
library's call with try/except, converting exceptions to Result.ko with
DATABASE_ERROR.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from src.domain.result import ErrorWithDetails, Result
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

        logger.info("Initializing MnemosyneClient", memory_bank=memory_bank, data_dir=data_dir)
        return Mnemosyne(memory_bank=memory_bank, data_dir=data_dir)

    # ------------------------------------------------------------------
    # Public API — all methods return Result
    # ------------------------------------------------------------------

    def remember(self, **kwargs: Any) -> Result[Dict[str, Any]]:
        """Store a durable memory."""
        try:
            value = self._instance.remember(**kwargs)
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne remember failed", memory_bank=self.memory_bank, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])

    def recall(self, query: str, limit: int = 5) -> Result[List[Dict[str, Any]]]:
        """Search for relevant memories."""
        try:
            value = self._instance.recall(query=query, limit=limit)
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne recall failed", memory_bank=self.memory_bank, query=query, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])

    def forget(self, memory_id: str) -> Result[Dict[str, Any]]:
        """Delete a memory."""
        try:
            value = self._instance.forget(memory_id=memory_id)
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne forget failed", memory_bank=self.memory_bank, memory_id=memory_id, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])

    def update(self, memory_id: str, **kwargs: Any) -> Result[Dict[str, Any]]:
        """Update memory content or importance."""
        try:
            value = self._instance.update(memory_id=memory_id, **kwargs)
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne update failed", memory_bank=self.memory_bank, memory_id=memory_id, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])

    def sleep(self) -> Result[Dict[str, Any]]:
        """Trigger memory consolidation."""
        try:
            value = self._instance.sleep()
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne sleep failed", memory_bank=self.memory_bank, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])

    def stats(self) -> Result[Dict[str, Any]]:
        """Return memory statistics."""
        try:
            value = self._instance.stats()
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne stats failed", memory_bank=self.memory_bank, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])
