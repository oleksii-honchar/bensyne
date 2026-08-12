"""Memory bank registry — in-memory mapping of memory bank name to description."""

from __future__ import annotations


DEFAULT_DESCRIPTIONS: dict[str, str] = {
    "default": "Default personal memory — general conversation context, preferences, and facts",
}


class MemoryBankRegistry:
    """In-memory registry mapping memory bank names to descriptions.

    Initialized with DEFAULT_DESCRIPTIONS. Supports register (upsert) and get operations.
    """

    def __init__(self) -> None:
        self._descriptions: dict[str, str] = dict(DEFAULT_DESCRIPTIONS)

    def register(self, name: str, description: str) -> None:
        """Register or update a memory bank description (idempotent upsert).

        Args:
            name: Memory bank name.
            description: Human-readable description of the memory bank.
        """
        self._descriptions[name] = description

    def get(self, name: str) -> str | None:
        """Get description for a memory bank, or None if not registered.

        Args:
            name: Memory bank name.

        Returns:
            Description string or None.
        """
        return self._descriptions.get(name)

    def list_banks(self) -> list[str]:
        """Return all registered memory bank names.

        Returns:
            List of memory bank name strings.
        """
        return list(self._descriptions.keys())
