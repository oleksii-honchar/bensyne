"""Memory bank router with async locking and LRU eviction."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Dict, Optional, Set

if TYPE_CHECKING:
    from asyncio import Lock

from src.domain.models import InstancePoolConfig
from src.infrastructure.mnemosyne.bank_manager import BankManager
from src.infrastructure.mnemosyne.client import MnemosyneClient
from src.services.bank.pool import evict_if_over_limit
from src.services.bank.registry import MemoryBankRegistry

logger = logging.getLogger(__name__)


class MemoryBankRouter:
    """Route MCP tool calls to memory-bank-scoped Mnemosyne instances.

    Features:
    - Double-checked locking for thread-safe instance creation
    - Default instance created at boot
    - Dynamic instance creation on first request per memory bank
    - LRU eviction (oldest created non-default) when over max_instances
    """

    def __init__(self, config: InstancePoolConfig, bank_manager: BankManager) -> None:
        self.config = config
        self.bank_manager = bank_manager
        self.registry = MemoryBankRegistry()
        self.instances: Dict[str, MnemosyneClient] = {}
        self._lock: Optional[Lock] = None

        # Start default instance at boot
        self.instances["default"] = self._create_instance("default")
        logger.info("Default memory bank instance created")

    def _get_lock(self) -> Lock:
        """Lazy-initialize asyncio.Lock to avoid event loop issues in tests."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _create_instance(self, memory_bank: str) -> MnemosyneClient:
        """Create a new MnemosyneClient for the given memory bank."""
        client = MnemosyneClient(memory_bank=memory_bank, bank_manager=self.bank_manager)
        logger.info("Created instance for memory_bank: %s", memory_bank)
        return client

    async def get_instance(self, memory_bank: str) -> MnemosyneClient:
        """Get or create instance for memory bank using double-checked locking.

        Args:
            memory_bank: The memory bank to get an instance for.

        Returns:
            MnemosyneClient instance for the memory bank.
        """
        logger.debug(
            "[router] get_instance called for memory_bank=%s, current_instances=%s",
            memory_bank,
            list(self.instances.keys()),
        )

        # First check (before lock) — fast path for cached instances
        if memory_bank in self.instances:
            self.instances[memory_bank].last_accessed = time.time()
            logger.debug("[router] HIT cached instance for memory_bank=%s", memory_bank)
            return self.instances[memory_bank]

        async with self._get_lock():
            # Second check (after lock) — prevent duplicate creation
            if memory_bank not in self.instances:
                logger.debug("[router] Creating new instance for memory_bank=%s", memory_bank)
                self.instances[memory_bank] = self._create_instance(memory_bank)
                await self._evict_if_over_limit()
                logger.debug("[router] Active instances after creation: %s", list(self.instances.keys()))
            return self.instances[memory_bank]

    async def _evict_if_over_limit(self) -> None:
        """Evict oldest (first created) non-default instance when over max limit."""
        evict_if_over_limit(self.instances, self.config)

    def get_active_instances(self) -> int:
        """Return count of active instances for health endpoint."""
        return len(self.instances)

    def get_active_banks(self) -> Set[str]:
        """Return set of active memory bank names for health endpoint."""
        return set(self.instances.keys())

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
