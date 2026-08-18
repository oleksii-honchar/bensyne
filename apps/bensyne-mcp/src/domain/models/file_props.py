"""FileProps — caller-facing structural type for file metadata writes (D23, spec §5).

``FileProps`` mirrors the *updatable* fields of ``FileSchema``
(``src.domain.models.file_model.FileSchema``). It is structural typing for
callers only — zero runtime cost; the Pydantic schema remains the single
runtime validation source. A ``FileProps`` dict is destructured into
``File.update_metadata(**props)``, which re-validates the merged state
against ``FileSchema``.

Deliberately NOT props:
- ``id`` — identity, not a mutable property
- ``status`` — method-driven lifecycle (``mark_indexed`` / ``mark_deleted``)
- ``created_at`` / ``updated_at`` — system-managed timestamps
"""

from __future__ import annotations

from typing import TypedDict

from src.domain.models.file_model import FileRole, SourceType


class FileProps(TypedDict, total=False):
    """Partial file metadata for typed writes.

    Structural only (no runtime cost). ``total=False``: every field is
    optional, so a caller supplies only the fields it wants to change.
    The single runtime validation source is the Pydantic ``FileSchema`` —
    this TypedDict merely kills the untyped ``dict`` at the write entry point.
    """

    path: str
    source_type: SourceType
    file_role: FileRole | None
    hash: str | None
    file_type: str | None
    size: int | None
    language: str | None
    aggregated_keywords: list[str]
    aggregated_tags: list[str]
    summary: str | None
    total_chunks: int | None
    average_importance: float | None
    metadata: dict[str, str]
