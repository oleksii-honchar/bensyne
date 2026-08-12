"""Mnemosyne client wrapper."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Dict, List, Optional

if TYPE_CHECKING:
    from src.infrastructure.mnemosyne.bank_manager import BankManager

logger = logging.getLogger(__name__)


class MnemosyneClient:
    """Wraps mnemosyne.Mnemosyne for a single memory bank.

    Wraps Mnemosyne by delegating operations to the underlying Mnemosyne instance.
    Tracks created_at for LRU eviction in the instance pool.
    """

    def __init__(self, memory_bank: str, bank_manager: BankManager) -> None:
        self.memory_bank = memory_bank
        self.created_at = time.time()
        self._bank_manager = bank_manager

        # Lazy import to avoid pulling in mnemosyne at import time
        from mnemosyne.core.memory import Mnemosyne

        db_path = bank_manager.get_bank_db_path(memory_bank)
        logger.info("[MnemosyneClient] Initializing: memory_bank=%s, db_path=%s", memory_bank, db_path)
        self._instance = Mnemosyne(bank=memory_bank, db_path=str(db_path))
        logger.info("[MnemosyneClient] Created instance: memory_bank=%s, db_path=%s", memory_bank, self._instance.db_path)

    # ------------------------------------------------------------------
    # MnemosyneClient implementation
    # ------------------------------------------------------------------

    def remember(self, content: str, source: str = "conversation", **kwargs: Any) -> Dict[str, Any]:
        """Store a durable memory."""
        memory_id = self._instance.remember(content=content, source=source, **kwargs)
        return {"memory_id": memory_id, "status": "stored"}

    def recall(self, query: str, limit: int = 10, **kwargs: Any) -> List[Dict[str, Any]]:
        """Search for relevant memories."""
        return self._instance.recall(query=query, top_k=limit, **kwargs)

    def forget(self, memory_id: str) -> Dict[str, Any]:
        """Delete a memory."""
        ok = self._instance.forget(memory_id)
        return {"status": "deleted" if ok else "not_found", "memory_id": memory_id}

    def update(self, memory_id: str, content: Optional[str] = None, importance: Optional[float] = None) -> Dict[str, Any]:
        """Update memory content or importance."""
        ok = self._instance.update(memory_id, content=content, importance=importance)
        return {"status": "updated" if ok else "not_found", "memory_id": memory_id}

    def sleep(self) -> Dict[str, Any]:
        """Trigger memory consolidation."""
        return self._instance.sleep()

    def stats(self) -> Dict[str, Any]:
        """Return memory statistics."""
        return self._instance.get_stats()

    def get(self, memory_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific memory by ID."""
        return self._instance.get(memory_id)
