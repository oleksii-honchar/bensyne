"""Memory bank router with async locking and LRU eviction.

Uses the new Result-returning MnemosyneClient and structured logging.
"""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from asyncio import Lock

from src.domain.config_models import InstancePoolConfig
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.infrastructure.bank.pool import evict_if_over_limit
from src.infrastructure.bank.registry import MemoryBankRegistry
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
        self.registry = MemoryBankRegistry()
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

    def get_bank_description(self, memory_bank: str) -> str | None:
        """Get description for a memory bank from the registry.

        Args:
            memory_bank: The memory bank name.

        Returns:
            Description string or None if not registered.
        """
        return self.registry.get(memory_bank)

    def register_bank(self, name: str, description: str) -> None:
        """Register or update a memory bank description (delegates to registry).

        Args:
            name: Memory bank name.
            description: Human-readable description.
        """
        self.registry.register(name, description)
        logger.info(
            "Memory bank registered",
            memory_bank=name,
            description=description,
        )
