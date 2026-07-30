"""Namespace router with async locking and LRU eviction."""

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
from src.services.namespace.pool import evict_if_over_limit

logger = logging.getLogger(__name__)


class NamespaceRouter:
    """Route MCP tool calls to namespace-scoped Mnemosyne instances.

    Features:
    - Double-checked locking for thread-safe instance creation
    - Default instance created at boot
    - Dynamic instance creation on first request per namespace
    - LRU eviction (oldest created non-default) when over max_instances
    """

    def __init__(self, config: InstancePoolConfig, bank_manager: BankManager) -> None:
        self.config = config
        self.bank_manager = bank_manager
        self.instances: Dict[str, MnemosyneClient] = {}
        self._lock: Optional[Lock] = None

        # Start default instance at boot
        self.instances["default"] = self._create_instance("default")
        logger.info("Default namespace instance created")

    def _get_lock(self) -> Lock:
        """Lazy-initialize asyncio.Lock to avoid event loop issues in tests."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _create_instance(self, namespace: str) -> MnemosyneClient:
        """Create a new MnemosyneClient for the given namespace."""
        client = MnemosyneClient(namespace=namespace, bank_manager=self.bank_manager)
        logger.info("Created instance for namespace: %s", namespace)
        return client

    async def get_instance(self, namespace: str) -> MnemosyneClient:
        """Get or create instance for namespace using double-checked locking.

        Args:
            namespace: The namespace to get an instance for.

        Returns:
            MnemosyneClient instance for the namespace.
        """
        # First check (before lock) — fast path for cached instances
        if namespace in self.instances:
            self.instances[namespace].last_accessed = time.time()
            return self.instances[namespace]

        async with self._get_lock():
            # Second check (after lock) — prevent duplicate creation
            if namespace not in self.instances:
                self.instances[namespace] = self._create_instance(namespace)
                await self._evict_if_over_limit()
            return self.instances[namespace]

    async def _evict_if_over_limit(self) -> None:
        """Evict oldest (first created) non-default instance when over max limit."""
        evict_if_over_limit(self.instances, self.config)

    def get_active_instances(self) -> int:
        """Return count of active instances for health endpoint."""
        return len(self.instances)

    def get_active_namespaces(self) -> Set[str]:
        """Return set of active namespace names for health endpoint."""
        return set(self.instances.keys())
