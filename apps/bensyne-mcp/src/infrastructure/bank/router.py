"""Memory bank router with async locking, LRU eviction, and path authority.

Uses the new Result-returning MnemosyneClient and structured logging.
Path rules (DEC-0062/U11, v2 uniform layout):
  - All banks (incl. default): {data_dir}/banks/{memory_bank}/{...}.db
In-memory registry duties are removed — the router is a path authority +
instance pool only (DEC-0064/U14).
"""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncio import Lock

from src.domain.config_models import InstancePoolConfig
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.infrastructure.bank.pool import evict_if_over_limit
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import get_logger

logger = get_logger(__name__)


class MemoryBankRouter:
    """Route MCP tool calls to memory-bank-scoped Mnemosyne instances.

    Features:
    - Double-checked locking for thread-safe instance creation
    - Default instance created at boot
    - Dynamic instance creation on first request per memory bank
    - LRU eviction (oldest created non-default) when over max_instances
    - Structured logging for instance creation and eviction
    """

    def __init__(self, config: InstancePoolConfig) -> None:
        self.config = config
        self.instances: dict[str, MnemosyneClient] = {}
        self._lock: Lock | None = None

        # Start default instance at boot
        self.instances["default"] = self._create_instance("default")
        logger.info("Default memory bank instance created", memory_bank="default")

    def _get_lock(self) -> Lock:
        """Lazy-initialize asyncio.Lock to avoid event loop issues in tests."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _create_instance(self, memory_bank: str) -> MnemosyneClient:
        """Create a new MnemosyneClient for the given memory bank."""
        client = MnemosyneClient(
            memory_bank=memory_bank,
            data_dir=self.config.data_dir,
            memory_bank_router=self,
        )
        logger.info(
            "Created MnemosyneClient instance",
            memory_bank=memory_bank,
            data_dir=self.config.data_dir,
        )
        return client

    async def get_instance(self, memory_bank: str) -> MnemosyneClient:
        """Get or create instance for memory bank using double-checked locking.

        Args:
            memory_bank: The memory bank to get an instance for.

        Returns:
            MnemosyneClient instance for the memory bank.
        """
        logger.debug(
            "[router] get_instance called",
            memory_bank=memory_bank,
            current_instances=list(self.instances.keys()),
        )

        # First check (before lock) — fast path for cached instances
        if memory_bank in self.instances:
            self.instances[memory_bank].last_accessed = time.time()
            logger.debug(
                "[router] HIT cached instance",
                memory_bank=memory_bank,
            )
            return self.instances[memory_bank]

        async with self._get_lock():
            # Second check (after lock) — prevent duplicate creation
            if memory_bank not in self.instances:
                logger.debug(
                    "[router] Creating new instance",
                    memory_bank=memory_bank,
                )
                self.instances[memory_bank] = self._create_instance(memory_bank)
                await self._evict_if_over_limit()
                logger.debug(
                    "[router] Active instances after creation",
                    active_instances=list(self.instances.keys()),
                )
            return self.instances[memory_bank]

    async def _evict_if_over_limit(self) -> None:
        """Evict oldest (first created) non-default instance when over max limit."""
        evict_if_over_limit(self.instances, self.config)

    def get_active_instances(self) -> int:
        """Return count of active instances for health endpoint."""
        return len(self.instances)

    def get_active_banks(self) -> set[str]:
        """Return set of active memory bank names for health endpoint."""
        return set(self.instances.keys())

    def list_banks(self) -> list[str]:
        """Return list of active memory bank names.

        Returns:
            List of memory bank name strings currently in the instance pool.
        """
        return list(self.instances.keys())

    # ------------------------------------------------------------------
    # Path authority (DEC-0064/U14) — v2 uniform paths under banks/
    # ------------------------------------------------------------------

    def _banks_root(self) -> Path:
        """Return the v2 banks root directory: {data_dir}/banks."""
        return Path(self.config.data_dir) / "banks"

    def get_bank_dir(self, memory_bank: str) -> Path:
        """Return the bank directory {data_dir}/banks/{memory_bank} (write path).

        Creates the directory (mkdir -p) so write callers can drop files.
        """
        path = self._banks_root() / memory_bank
        path.mkdir(parents=True, exist_ok=True)
        return path

    def get_bank_db_path(self, memory_bank: str) -> Path:
        """Return the mnemosyne db path for the bank (write path).

        Uniform for ALL banks incl. default: {data_dir}/banks/{bank}/mnemosyne.db.
        Ensures the parent directory exists (mkdir -p).
        """
        path = self.get_bank_dir(memory_bank) / "mnemosyne.db"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def get_mnemosyne_db_path(self, memory_bank: str) -> Path:
        """Return the mnemosyne db path (read-side, NO mkdir).

        Uniform for ALL banks incl. default: {data_dir}/banks/{bank}/mnemosyne.db.
        Does NOT create any directories or files — safe for listing/guarding.
        """
        return self._banks_root() / memory_bank / "mnemosyne.db"

    def get_stats_for(self, memory_bank: str) -> Result[dict]:
        """Return memory stats for the named bank via a TRANSIENT client.

        Resolves the memory entity repository for the bank named in the request
        (R6). The client is transient — it is NEVER added to self.instances, so
        no status flip, no LRU churn, no pool-state side effects.

        Existence guard (ADR-8): a bank without an on-disk mnemosyne.db yields
        MEMORY_BANK_DB_NOT_FOUND and never constructs a client, so no directory
        or database file is created by a stats lookup.
        """
        db_path = self.get_mnemosyne_db_path(memory_bank)
        if not db_path.exists():
            return Result.ko(
                [ErrorWithDetails("MEMORY_BANK_DB_NOT_FOUND", {"bank": memory_bank})]
            )
        client = self._create_instance(memory_bank)  # transient — NOT pooled
        return client.get_stats()

    def get_file_metadata_path(self, memory_bank: str) -> Path:
        """Return the file metadata db path (read-side, NO mkdir)."""
        return self._banks_root() / memory_bank / "file_metadata.db"

    def get_hash_index_path(self, memory_bank: str) -> Path:
        """Return the hash index db path (read-side, NO mkdir)."""
        return self._banks_root() / memory_bank / "hash_index.db"

    def list_bank_dirs(self) -> list[str]:
        """Scan {data_dir}/banks/ and return sorted bank names (read-only).

        Returns:
            Sorted list of bank names present on disk; [] when banks/ does
            not exist. No mkdir/delete side effects.
        """
        banks_root = self._banks_root()
        if not banks_root.is_dir():
            return []
        return sorted(entry.name for entry in banks_root.iterdir() if entry.is_dir())
