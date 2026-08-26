"""MnemosyneClient — Result-returning wrapper around the external Mnemosyne library.

Replaces the current client that returns raw dicts. Each method wraps the
library's call with try/except, converting exceptions to Result.ko with
DATABASE_ERROR.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.domain.memory_entity import Memory
    from src.infrastructure.bank.router import MemoryBankRouter

from src.infrastructure.config.data_dir import resolve_data_dir
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import get_logger

logger = get_logger(__name__)


class MnemosyneClient:
    """Wrapper for external Mnemosyne service (library).

    Wraps the library's remember/recall/forget/update/sleep/stats methods
    with Result-based error handling.
    """

    def __init__(
        self,
        memory_bank: str,
        data_dir: str | None = None,
        memory_bank_router: MemoryBankRouter | None = None,
    ) -> None:
        self.memory_bank = memory_bank
        self.memory_bank_router = memory_bank_router
        self.created_at = time.time()
        self.last_accessed = time.time()
        # Resolution order: explicit (config/CLI) -> DATA_DIR env -> "./data".
        resolved_data_dir = resolve_data_dir(data_dir)
        self._data_dir = resolved_data_dir
        self._instance = self._create_instance(memory_bank=memory_bank, data_dir=resolved_data_dir)

    def _create_instance(self, memory_bank: str, data_dir: str) -> Any:
        """Create the underlying Mnemosyne library instance.

        Overridable in tests via monkeypatch/patch.
        """
        # Lazy import to avoid pulling in mnemosyne at import time
        from mnemosyne.core.memory import Mnemosyne

        # Resolve db_path via the router (single path authority, DEC-0064/U11):
        # ALL banks incl. default go to {data_dir}/banks/{bank}/mnemosyne.db.
        # When no router is given (direct construction/tests), keep the legacy
        # inline behavior so the layout does not silently shift.
        data_path = Path(data_dir)
        if self.memory_bank_router is not None:
            db_path = self.memory_bank_router.get_bank_db_path(memory_bank)
        elif memory_bank == "default":
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

    def get_stats(self) -> Result[dict[str, Any]]:
        """Return memory statistics.

        When a router is present (DEC-0066/S7): the returned ``banks`` key is
        overwritten with the canonical filesystem view (``router.list_bank_dirs()``)
        and the phantom nested ``<bank_dir>/banks`` directory (a mnemosyne library
        mkdir side effect) is removed when it exists and is empty at any depth.
        Bank data files are never touched. Without a router the plain library
        result is returned unchanged.
        """
        try:
            value = self._instance.get_stats()
            if self.memory_bank_router is not None:
                self._remove_phantom_banks_dir()
                value["banks"] = self.memory_bank_router.list_bank_dirs()
            return Result.ok(value)
        except Exception as exc:
            logger.error("Mnemosyne stats failed", memory_bank=self.memory_bank, error=str(exc))
            return Result.ko(errors=[ErrorWithDetails("DATABASE_ERROR", {"detail": str(exc)})])

    def _remove_phantom_banks_dir(self) -> None:
        """Remove the phantom nested <bank_dir>/banks dir created by the library.

        The mnemosyne library mkdirs ``{parent(bank_db)}/banks`` during
        ``get_stats`` (memory.py side effect). Only removed when it is empty at
        any depth; otherwise left in place with a warning. Never touches files.
        """
        phantom = Path(self._data_dir) / "banks" / self.memory_bank / "banks"
        if not phantom.is_dir():
            return
        if not self._dir_is_empty(phantom):
            logger.warning(
                "Phantom banks dir left in place (non-empty)",
                memory_bank=self.memory_bank,
                path=str(phantom),
            )
            return
        shutil.rmtree(phantom)
        logger.info(
            "Removed empty phantom banks dir",
            memory_bank=self.memory_bank,
            path=str(phantom),
        )

    @staticmethod
    def _dir_is_empty(path: Path) -> bool:
        """Return True when the directory contains no entries at any depth."""
        for entry in path.iterdir():
            if entry.is_file():
                return False
            if entry.is_dir() and not MnemosyneClient._dir_is_empty(entry):
                return False
        return True

    def get(self, memory_id: str) -> dict | None:
        """Retrieve a single memory by id (callable contract for content composition)."""
        try:
            return self._instance.get(memory_id)
        except Exception as exc:
            logger.error(
                "Mnemosyne get failed",
                memory_bank=self.memory_bank,
                memory_id=memory_id,
                error=str(exc),
            )
            return None

    def list_memory_validities(self) -> list[tuple[str, str | None]]:
        """Return (memory_id, valid_until) for every memory in this bank.

        Covers working_memory + episodic_memory (the BEAM stores), deduplicated
        by id so a memory present in both is counted once (working wins,
        mirroring Mnemosyne.get()). Expired (valid_until in the past) and
        superseded memories are intentionally NOT filtered out — the caller
        (getPersonaStatus) needs them to derive the expired-occasional count.
        """
        conn = self._instance.conn
        pairs: dict[str, str | None] = {}

        cursor = conn.cursor()
        cursor.execute("SELECT id, valid_until FROM working_memory")
        for row in cursor.fetchall():
            pairs[str(row["id"])] = row["valid_until"]

        cursor.execute("SELECT id, valid_until FROM episodic_memory")
        for row in cursor.fetchall():
            mem_id = str(row["id"])
            # working_memory wins on collision (dedup), but keep episodic rows
            # for ids not already seen.
            pairs.setdefault(mem_id, row["valid_until"])

        return list(pairs.items())
