"""Namespace router module — re-exports from namespace subpackage.

Provides backward-compatible import path: src.services.namespace_router
"""

from src.services.namespace.router import NamespaceRouter

__all__ = ["NamespaceRouter"]
