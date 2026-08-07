"""Deduplication bridge — hash extraction and index integration."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


def is_file_based_memory(arguments: dict[str, Any]) -> bool:
    """Return True if the memory arguments contain a fileHash in metadata."""
    metadata = arguments.get("metadata")
    if not isinstance(metadata, dict):
        return False
    return "fileHash" in metadata


def extract_file_hash(arguments: dict[str, Any]) -> Optional[str]:
    """Extract the fileHash from memory arguments metadata, or None if absent."""
    metadata = arguments.get("metadata")
    if not isinstance(metadata, dict):
        return None
    return metadata.get("fileHash")


def find_memory_by_hash(hash_index: Any, file_hash: str) -> Optional[str]:
    """Look up a memory_id by file hash using the hash index."""
    return hash_index.lookup(file_hash)


def index_file_hash(hash_index: Any, file_hash: str, memory_id: str) -> None:
    """Store a file_hash → memory_id mapping in the hash index."""
    hash_index.store(file_hash, memory_id)


def remove_hash_index_entry(hash_index: Any, memory_id: str) -> Optional[str]:
    """Remove the hash index entry for a given memory_id (on forget).

    Returns the file_hash that was removed, or None if no entry found.
    """
    return hash_index.remove(memory_id)
