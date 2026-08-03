"""Namespace registry — in-memory mapping of namespace name to description."""

from __future__ import annotations

from typing import Dict, List

DEFAULT_DESCRIPTIONS: Dict[str, str] = {
    "default": "Default personal memory — general conversation context, preferences, and facts",
}


class NamespaceRegistry:
    """In-memory registry mapping namespace names to descriptions.

    Initialized with DEFAULT_DESCRIPTIONS. Supports register (upsert) and get operations.
    """

    def __init__(self) -> None:
        self._descriptions: Dict[str, str] = dict(DEFAULT_DESCRIPTIONS)

    def register(self, name: str, description: str) -> None:
        """Register or update a namespace description (idempotent upsert).

        Args:
            name: Namespace name.
            description: Human-readable description of the namespace.
        """
        self._descriptions[name] = description

    def get(self, name: str) -> str | None:
        """Get description for a namespace, or None if not registered.

        Args:
            name: Namespace name.

        Returns:
            Description string or None.
        """
        return self._descriptions.get(name)

    def list_namespaces(self) -> List[str]:
        """Return all registered namespace names.

        Returns:
            List of namespace name strings.
        """
        return list(self._descriptions.keys())
