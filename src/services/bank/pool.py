"""Instance pool management with LRU eviction."""

from __future__ import annotations

from typing import TYPE_CHECKING, Dict

from src.domain.models import InstancePoolConfig
from src.utils.structured_logging import get_logger

if TYPE_CHECKING:
    from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient

logger = get_logger(__name__)

DEFAULT_BANK = "default"


def evict_if_over_limit(
    instances: Dict[str, MnemosyneClient],
    config: InstancePoolConfig,
) -> None:
    """Evict oldest (first created) non-default instance when over max limit.

    This is a synchronous helper used by MemoryBankRouter after acquiring its lock.

    Args:
        instances: The instances dictionary managed by the router.
        config: Instance pool configuration containing max_instances.
    """
    while len(instances) > config.max_instances:
        # Find oldest non-default instance by created_at
        non_default = {
            k: v for k, v in instances.items() if k != DEFAULT_BANK
        }

        if not non_default:
            # Should never happen since default is excluded from eviction
            logger.warning("No non-default instances to evict, stopping eviction")
            break

        target = min(non_default.keys(), key=lambda k: non_default[k].created_at)
        del instances[target]
        logger.info("Evicted oldest instance", memory_bank=target)
