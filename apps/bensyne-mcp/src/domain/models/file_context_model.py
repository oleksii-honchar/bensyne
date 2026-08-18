"""FileContext — the wire contract for "remember this memory as part of a file."

What this is / when it fires:
    When a ``rememberMemory`` metadata payload carries a non-empty
    ``file_path``, that payload is the unified chunk contract v1. This module
    is bensyne's half of the contract: it parses + validates the payload into
    a frozen ``FileContext`` — the input declaration of ONE remember call —
    which the materialization path (``FileService.materialize_file_context``)
    then projects into the file layer (SQLite: ``files`` / ``file_chunks`` /
    ``file_relations``). Absent/empty ``file_path`` ⇒ ``None``: a pure memory,
    zero file-layer writes.

FileContext is NOT the File entity (``domain/file_entity.py``). It is
chunk-scoped (one remember call: one chunk + its edges + its hashes); ``File``
is the persisted, file-aggregated row that survives across calls (identity,
lifecycle, re-aggregated keywords/tags/importance). They share only a small
core (path, source_type, file_role, language, hash, summary) — full boundary
table: spec §2.2.

Flow:
    rememberMemory args
      → parse_file_context(metadata) → FileContext | None
      → FileService.materialize_file_context(bank, context, memory_id)
          → upsert File (deterministic id) + the FileChunk row + FileRelation rows
    Materialization is idempotent (a silent no-op on re-remember) and revives a
    DELETED file (DELETED → INDEXED) when it is re-remembered.

Where each field lands (which type owns what):
    file_path                  → File.path (+ derive_file_id → File.id)
    source_type, file_role,
    language, summary          → same-named File fields
    file_hash                  → File.hash (the whole-file content hash —
                                 canonical wire name, D12; surfaced on read,
                                 D15; a change ⇒ rebuild_projection, D5)
    extra (str→str map)        → merged into File.metadata
    tags                       → File.aggregated_tags (union-merge, idempotent)
    chunk_index, start_line,
    end_line, section_header,
    chunk_hash, parent_unit    → FileChunk row (chunk-level facts, never File)
    edges                      → FileRelation rows (+ missing-target stubs)
    contract_version           → wire-only (versioning: >1 ⇒ warn + best effort)
    total_chunks               → the producer's claim only (validation);
                                 File.total_chunks is re-aggregated from the
                                 real chunk set on the write path, never copied

Contract rules (full contract: ``materials/unified-chunk-contract.md``; the
racoohu side mirrors it — ``apps/racochu`` ``content-chunk.entity.ts`` zod
schema + the shared JSON fixture ``unified-chunk-contract-v1.json``,
byte-identical on both sides):
    Rule 1 (trigger): file_path absent/empty ⇒ None — plain memory,
                      zero file-layer writes.
    Legacy keys:      camelCase aliases map to their canonical names
                      (filePath→file_path, hash/fileHash→file_hash, …).
    Degrade, never reject: invalid source_type/file_role ⇒ unknown/None with
                      warn; malformed edges DROPPED with warn (the chunk still
                      materializes); unknown string keys captured into extra;
                      non-string unknowns ignored with warn.
    Versioning (rule 6): contract_version > 1 ⇒ warn + best-effort parse of
                      known keys.

Provenance: spec §2.2 (FileContext vs File boundary), D12–D15 (wire naming +
dual hash), D26 (materialization concept — canonical home: the vault
``materialization`` concept node).
"""

import logging
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, ValidationError, model_validator

from src.domain.models.file_model import FileRole, SourceType
from src.domain.models.file_relation_model import RelationType

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FileContextParentUnit:
    """Parent-unit summary reference (big-file sources: book=chapter, docs=section)."""

    ref: str
    summary: str | None = None


@dataclass(frozen=True)
class FileContextEdge:
    """Relation edge declared by the source strategy."""

    target_path: str
    relation_type: RelationType
    strength: float = 1.0
    description: str | None = None


@dataclass(frozen=True)
class FileContext:
    """Frozen result of parsing a unified chunk contract v1 metadata payload.

    ``tags`` and ``extra`` are stored as immutable tuples / mapping views so the
    frozen dataclass is truly immutable.
    """

    contract_version: int
    file_path: str
    chunk_index: int
    total_chunks: int
    section_header: str | None
    start_line: int | None
    end_line: int | None
    source_type: SourceType
    file_role: FileRole | None
    language: str | None
    file_hash: str | None
    chunk_hash: str | None
    summary: str | None
    parent_unit: FileContextParentUnit | None
    edges: tuple[FileContextEdge, ...] | None
    tags: tuple[str, ...]
    extra: dict[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "tags", tuple(self.tags))
        object.__setattr__(self, "edges", tuple(self.edges) if self.edges is not None else None)
        object.__setattr__(self, "extra", _FrozenStrMapping(self.extra))

    @property
    def tags_list(self) -> list[str]:
        """Mutable-list view of tags (contract field ``tags`` is a list)."""
        return list(self.tags)

    @property
    def edges_list(self) -> list[FileContextEdge] | None:
        """Mutable-list view of edges (contract field ``edges`` is an array)."""
        return list(self.edges) if self.edges is not None else None


class FileContextParentUnitSchema(BaseModel):
    """Pydantic model for the parent_unit object."""

    ref: str = Field(min_length=1)
    summary: str | None = None


class FileContextEdgeSchema(BaseModel):
    """Pydantic model for a single relation edge."""

    target_path: str = Field(min_length=1)
    relation_type: RelationType
    strength: float = Field(default=1.0, ge=0.0, le=1.0)
    description: str | None = None


class FileContextSchema(BaseModel):
    """Pydantic model for the v1 contract payload (after legacy-key mapping)."""

    contract_version: int = Field(default=1, ge=1)
    file_path: str = Field(min_length=1)
    chunk_index: int = Field(default=0, ge=0)
    total_chunks: int = Field(default=1, ge=1)
    section_header: str | None = None
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    source_type: SourceType = Field(default=SourceType.UNKNOWN)
    file_role: FileRole | None = None
    language: str | None = None
    file_hash: str | None = None
    chunk_hash: str | None = None
    summary: str | None = None
    parent_unit: dict[str, Any] | None = None
    edges: list[Any] | None = None
    tags: list[str] = Field(default_factory=list)
    extra: dict[str, str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_line_range(self) -> "FileContextSchema":
        if self.start_line is not None and self.end_line is not None and self.end_line < self.start_line:
            raise ValueError(f"end_line ({self.end_line}) must be >= start_line ({self.start_line})")
        return self


# Legacy camelCase key → canonical v1 field name.
_LEGACY_KEY_MAP: dict[str, str] = {
    "breadcrumb": "file_path",
    "filePath": "file_path",
    "chunkIndex": "chunk_index",
    "totalChunks": "total_chunks",
    "sectionHeader": "section_header",
    "startLine": "start_line",
    "endLine": "end_line",
    "hash": "file_hash",
    "fileHash": "file_hash",
    "fileRole": "file_role",
}

_KNOWN_V1_KEYS: frozenset[str] = frozenset(
    {
        "contract_version",
        "file_path",
        "chunk_index",
        "total_chunks",
        "section_header",
        "start_line",
        "end_line",
        "source_type",
        "file_role",
        "language",
        "file_hash",
        "chunk_hash",
        "summary",
        "parent_unit",
        "edges",
        "tags",
        "extra",
    }
)


def _map_legacy_keys(metadata: dict[str, Any]) -> dict[str, Any]:
    """Map legacy camelCase keys onto canonical v1 field names.

    Canonical keys win over legacy aliases when both are present.
    """
    mapped: dict[str, Any] = {}
    for key, value in metadata.items():
        canonical = _LEGACY_KEY_MAP.get(key, key)
        if canonical not in mapped:
            mapped[canonical] = value
    return mapped


def _split_extra(payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Split payload into (known v1 fields, extra).

    String-valued unknown top-level keys go to ``extra``; non-string unknown
    values are ignored with a warn.
    """
    known: dict[str, Any] = {}
    extra: dict[str, str] = {}
    for key, value in payload.items():
        if key in _KNOWN_V1_KEYS:
            known[key] = value
        elif isinstance(value, str):
            extra[key] = value
        else:
            logger.warning(
                "file_context_parse_unknown_key_ignored",
                extra={"key": key, "value_type": type(value).__name__},
            )
    return known, extra


def _parse_edges(raw_edges: list[Any]) -> tuple[FileContextEdge, ...]:
    """Parse edges, dropping malformed ones with a warn (chunk still materializes)."""
    edges: list[FileContextEdge] = []
    for raw in raw_edges:
        if not isinstance(raw, dict):
            logger.warning("file_context_edge_dropped", extra={"reason": "not_an_object", "edge": raw})
            continue
        try:
            schema = FileContextEdgeSchema(**raw)
        except ValidationError as e:
            logger.warning(
                "file_context_edge_dropped",
                extra={"reason": "invalid_edge", "errors": [err.get("msg") for err in e.errors()]},
            )
            continue
        edges.append(
            FileContextEdge(
                target_path=schema.target_path,
                relation_type=schema.relation_type,
                strength=schema.strength,
                description=schema.description,
            )
        )
    return tuple(edges)


def _parse_parent_unit(raw: Any) -> FileContextParentUnit | None:
    """Parse parent_unit; malformed objects degrade to None with a warn."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        logger.warning("file_context_parent_unit_dropped", extra={"reason": "not_an_object"})
        return None
    try:
        schema = FileContextParentUnitSchema(**raw)
    except ValidationError as e:
        logger.warning(
            "file_context_parent_unit_dropped",
            extra={"reason": "invalid_parent_unit", "errors": [err.get("msg") for err in e.errors()]},
        )
        return None
    return FileContextParentUnit(ref=schema.ref, summary=schema.summary)


def _coerce_source_type(value: Any) -> SourceType:
    """Coerce source_type to a known SourceType; invalid values degrade to UNKNOWN."""
    if value is None:
        return SourceType.UNKNOWN
    try:
        return SourceType(str(value))
    except ValueError:
        logger.warning("file_context_source_type_invalid", extra={"given": str(value)})
        return SourceType.UNKNOWN


def _coerce_file_role(value: Any) -> FileRole | None:
    """Coerce file_role to a known FileRole; invalid values degrade to None."""
    if value is None:
        return None
    try:
        return FileRole(str(value))
    except ValueError:
        logger.warning("file_context_file_role_invalid", extra={"given": str(value)})
        return None


def parse_file_context(metadata: dict[str, Any] | None) -> FileContext | None:
    """Parse a unified chunk contract v1 metadata payload into a FileContext.

    Returns ``None`` when the payload is absent or carries no non-empty
    ``file_path`` (contract rule 1 — plain memory, zero file-layer writes).
    Returns ``None`` also when explicit field values violate range validators.

    See module docstring for documented decisions on legacy keys, unknown keys,
    edge dropping, and versioning.
    """
    if not isinstance(metadata, dict):
        return None

    payload = _map_legacy_keys(metadata)

    raw_file_path = payload.get("file_path")
    if not isinstance(raw_file_path, str) or not raw_file_path.strip():
        return None

    contract_version = payload.get("contract_version", 1)
    if isinstance(contract_version, int) and contract_version > 1:
        logger.warning(
            "file_context_contract_version_unsupported",
            extra={"contract_version": contract_version},
        )

    known, extra = _split_extra(payload)

    # A producer-supplied ``extra`` object is merged into the captured extras
    # (explicit keys win over dotted-key capture).
    raw_extra = known.get("extra")
    if isinstance(raw_extra, dict):
        for key, value in raw_extra.items():
            if isinstance(value, str):
                extra[str(key)] = value
            else:
                logger.warning(
                    "file_context_extra_value_ignored",
                    extra={"key": str(key), "value_type": type(value).__name__},
                )

    # Legacy best-effort: absent chunk_index/total_chunks degrade to 0/1.
    if "chunk_index" not in known or known["chunk_index"] is None:
        logger.warning("file_context_legacy_chunk_fields_defaulted", extra={"field": "chunk_index"})
        known["chunk_index"] = 0
    if "total_chunks" not in known or known["total_chunks"] is None:
        logger.warning("file_context_legacy_chunk_fields_defaulted", extra={"field": "total_chunks"})
        known["total_chunks"] = 1

    # Pre-coerce enum-ish fields so invalid values degrade instead of rejecting.
    if "source_type" in known:
        known["source_type"] = _coerce_source_type(known["source_type"])
    if "file_role" in known:
        known["file_role"] = _coerce_file_role(known["file_role"])

    known["extra"] = extra
    try:
        schema = FileContextSchema(**known)
    except ValidationError as e:
        logger.warning(
            "file_context_parse_failed",
            extra={"errors": [err.get("msg") for err in e.errors()]},
        )
        return None

    edges = _parse_edges(schema.edges) if schema.edges is not None else None

    return FileContext(
        contract_version=schema.contract_version,
        file_path=schema.file_path,
        chunk_index=schema.chunk_index,
        total_chunks=schema.total_chunks,
        section_header=schema.section_header,
        start_line=schema.start_line,
        end_line=schema.end_line,
        source_type=schema.source_type,
        file_role=schema.file_role,
        language=schema.language,
        file_hash=schema.file_hash,
        chunk_hash=schema.chunk_hash,
        summary=schema.summary,
        parent_unit=_parse_parent_unit(schema.parent_unit),
        edges=edges,
        tags=tuple(schema.tags),
        extra=dict(extra),
    )


class _FrozenStrMapping(dict[str, str]):
    """Read-only dict view so FileContext.extra is immutable."""

    def __init__(self, data: dict[str, str]) -> None:
        super().__init__(data)

    def __setitem__(self, key: str, value: str) -> None:  # type: ignore[override]
        raise TypeError("FileContext.extra is immutable")

    def __delitem__(self, key: str) -> None:  # type: ignore[override]
        raise TypeError("FileContext.extra is immutable")

    def clear(self) -> None:  # type: ignore[override]
        raise TypeError("FileContext.extra is immutable")

    def pop(self, *args: Any, **kwargs: Any) -> str:  # type: ignore[override]
        raise TypeError("FileContext.extra is immutable")

    def popitem(self) -> tuple[str, str]:  # type: ignore[override]
        raise TypeError("FileContext.extra is immutable")

    def setdefault(self, key: str, default: str | None = None) -> str:  # type: ignore[override]
        if key in self:
            return self[key]
        raise TypeError("FileContext.extra is immutable")

    def update(self, *args: Any, **kwargs: Any) -> None:  # type: ignore[override]
        raise TypeError("FileContext.extra is immutable")
