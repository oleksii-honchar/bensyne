"""Shape-pin tests for the canonical file block (D24.1 / gate 5 / S9).

The plain file block emitted at every retrieval site is produced by the single
entity method ``File.to_dict()`` (spec §7.1):

- searchFiles ``results[].file``
- fetchFile ``file`` (default + neighbor + partial modes)
- recallMemory ``file_enrichment.file`` (FileEnrichmentService)
- expandFileRelations ``source_file``

Before-state (pre-D24.1, code-verified 2026-08-17):

- searchFiles ``file``: 9 keys — no ``file_hash``.
- fetchFile ``file``: 12 keys — extra ``created_at``/``updated_at``;
  ``file_role`` from ``file_type``; ``total_chunks`` from the fetched-chunk
  count argument; ``average_importance`` hardcoded 0.5; ``metadata``
  hardcoded ``{}``.
- recall ``file_enrichment.file``: 7 keys — no ``file_role``/``keywords``/
  ``tags``.
- expandFileRelations ``source_file``: 3 keys (id/path/source_type).

After-state (this gate): every site emits the SAME 10-key canonical block
(legacy search keys + ``file_hash`` — spec's single-source ruling), so any
site drifting off ``File.to_dict()`` fails here. ``TestLegacyContractPreserved``
pins the keys/values that exist at each site today and must survive with
identical values for identical input (the byte-identity evidence layer —
green pre- and post-migration). The fetchFile ``created_at``/``updated_at``
keys are the one authorized retirement (spec §7.1 canonical block omits them;
D23 — timestamps are system-managed, not block fields).
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import MagicMock

from src.application.services.file_enrichment_service import FileEnrichmentService
from src.application.use_cases.expand_file_relations_use_case import ExpandFileRelationsUseCase
from src.application.use_cases.fetch_file_use_case import FetchFileUseCase
from src.application.use_cases.search_files_use_case import SearchFilesUseCase
from src.domain.file_chunk_entity import FileChunk, ContentType
from src.domain.file_entity import File
from src.domain.file_metadata_aggregate import FileMetadata
from src.domain.models.file_model import FileRole, FileStatus, SourceType
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock

NOW = datetime(2026, 1, 1, 0, 0, 0)
FILE_HASH = "f" * 64

# ---------------------------------------------------------------------------
# Canonical block contract (spec §7.1 / S9)
# ---------------------------------------------------------------------------

# Legacy SearchFilesUseCase file-block key set (pre-D24.1, L239–251).
LEGACY_SEARCH_FILE_KEYS = {
    "id",
    "path",
    "source_type",
    "file_role",
    "total_chunks",
    "keywords",
    "tags",
    "average_importance",
    "metadata",
}
# Canonical block = legacy search keys + file_hash (D15).
CANONICAL_FILE_BLOCK_KEYS = LEGACY_SEARCH_FILE_KEYS | {"file_hash"}
# FetchFile site: the keys whose values were already entity-driven pre-D24.1
# and must stay byte-identical for identical input.
LEGACY_FETCH_STABLE_KEYS = {"id", "path", "source_type", "keywords", "tags", "file_hash"}
# Enrichment site: the full pre-D24.1 key set (all entity-driven values).
LEGACY_ENRICHMENT_FILE_KEYS = {
    "id",
    "path",
    "source_type",
    "total_chunks",
    "average_importance",
    "metadata",
    "file_hash",
}


# ---------------------------------------------------------------------------
# Builders (row-based — real entity values, no stubs)
# ---------------------------------------------------------------------------


def _a_file(
    id: str = "f1",
    path: str = "/vault/notes/a.md",
    source_type: SourceType = SourceType.AGENT_SESSIONS,
    file_role: FileRole | None = None,
    hash: str | None = None,
    keywords: list[str] | None = None,
    tags: list[str] | None = None,
    total_chunks: int = 0,
    average_importance: float = 0.5,
    metadata: dict[str, str] | None = None,
) -> File:
    return File(
        id=id,
        path=path,
        source_type=source_type,
        file_role=file_role,
        hash=hash,
        file_type=None,
        size=None,
        language=None,
        aggregated_keywords=keywords or [],
        aggregated_tags=tags or [],
        status=FileStatus.INDEXED,
        summary=None,
        total_chunks=total_chunks,
        average_importance=average_importance,
        metadata=dict(metadata or {}),
        created_at=NOW,
        updated_at=NOW,
    )


def _rich_file() -> File:
    """A file with every canonical-block field set to a distinct value."""
    return _a_file(
        id="f1",
        path="/vault/notes/a.md",
        source_type=SourceType.AGENT_SESSIONS,
        file_role=FileRole.DOCS,
        hash=FILE_HASH,
        keywords=["kw1", "kw2"],
        tags=["tag1"],
        total_chunks=7,
        average_importance=0.82,
        metadata={"session.id": "sess_42"},
    )


def _a_chunk(
    id: str = "c1",
    file_id: str = "f1",
    memory_id: str = "mem_1",
    chunk_index: int = 0,
    content_hash: str | None = "abc",
) -> FileChunk:
    return FileChunk(
        id=id,
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=chunk_index,
        start_line=0,
        end_line=10,
        content_hash=content_hash,
        content_type=ContentType.TEXT,
        is_partial=False,
        section_header=None,
        parent_unit_ref=None,
        parent_unit_summary=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _a_memory(memory_id: str = "mem_1") -> dict:
    return {"id": memory_id, "content": "chunk content", "importance": 0.7, "relevance_score": 0.9}


# ---------------------------------------------------------------------------
# Site wiring helpers — one call ⇒ the file block at that retrieval site
# ---------------------------------------------------------------------------


def _search_block(file: File) -> dict:
    """searchFiles results[0].file for a single file-backed memory."""
    mnemosyne = MagicMock()
    mnemosyne.recall.return_value = [_a_memory()]
    file_service = MagicMock()
    file_service.get_chunk_by_memory_id.return_value = Result.ok(_a_chunk())
    file_service.get_file_by_id.return_value = Result.ok(file)
    file_service.get_relations_by_file_id.return_value = Result.ok([])
    file_service.get_chunks_by_file_id.return_value = Result.ok([_a_chunk()])
    use_case = SearchFilesUseCase(mnemosyne_client=mnemosyne, file_service=file_service, logger=LoggerMock())
    result = use_case.execute({"query": "q", "memory_bank": "bank"})
    assert result.is_ok is True
    return result.value["results"][0]["file"]


def _fetch_block(file: File, mode: str = "default") -> dict:
    """fetchFile response.file (include_metadata=True) in the given mode."""
    file_service = MagicMock()
    file_service.get_file_by_id.return_value = Result.ok(file)
    mnemosyne = MagicMock()
    mnemosyne.get.return_value = {"content": "Hello"}

    if mode == "partial":
        file_service.get_chunks_by_file_id.return_value = Result.ko(
            [ErrorWithDetails("CHUNK_FETCH_FAILED", {})]
        )
        params = {"file_id": "f1", "memory_bank": "bank", "include_metadata": True}
    elif mode == "neighbor":
        chunks = [_a_chunk(chunk_index=0), _a_chunk(id="c2", memory_id="mem_2", chunk_index=1)]
        file_service.get_chunks_by_file_id.return_value = Result.ok(chunks)
        mnemosyne.get.return_value = {"content": "Hello"}
        params = {"file_id": "f1", "memory_bank": "bank", "include_metadata": True, "center_chunk_index": 1, "adjacent_chunks": 1}
    else:
        file_service.get_chunks_by_file_id.return_value = Result.ok([_a_chunk()])
        params = {"file_id": "f1", "memory_bank": "bank", "include_metadata": True}

    use_case = FetchFileUseCase(
        mnemosyne_client=mnemosyne,
        file_service=file_service,
        logger=LoggerMock(),
    )
    result = use_case.execute(params)
    assert result.is_ok is True
    return result.value["file"]


def _enrichment_block(file: File) -> dict:
    """recallMemory file_enrichment.file for a single file-backed memory."""
    file_service = MagicMock()
    file_service.get_chunk_by_memory_id.return_value = Result.ok(_a_chunk())
    file_service.get_file_by_id.return_value = Result.ok(file)
    file_service.get_relations_by_file_id.return_value = Result.ok([])
    file_service.get_chunks_by_file_id.return_value = Result.ok([_a_chunk()])
    service = FileEnrichmentService(file_service=file_service, logger=LoggerMock())
    results = service.enrich([_a_memory()])
    assert results[0]["file_enrichment"] is not None
    return results[0]["file_enrichment"]["file"]


def _expand_source_block(file: File) -> dict:
    """expandFileRelations response.source_file (no relations)."""
    aggregate = FileMetadata.of(file).value
    file_service = MagicMock()
    file_service.get_file.return_value = Result.ok(aggregate)
    relation_repo = MagicMock()
    relation_repo.get_relations_by_file_id.return_value = Result.ok([])
    use_case = ExpandFileRelationsUseCase(
        mnemosyne_client=MagicMock(),
        file_service=file_service,
        relation_repository=relation_repo,
        logger=LoggerMock(),
    )
    result = use_case.execute({"file_id": "f1"})
    assert result.is_ok is True
    return result.value["source_file"]


# ---------------------------------------------------------------------------
# Legacy contract preserved (green pre- AND post-migration — byte-identity
# evidence: keys present at each site today survive with identical values)
# ---------------------------------------------------------------------------


class TestLegacyContractPreserved:
    """Keys/values that exist at each site pre-D24.1 and must survive the
    unification with identical values for identical input.

    The fetchFile ``created_at``/``updated_at`` keys are intentionally NOT
    pinned: the spec §7.1 canonical block omits them (single-source ruling —
    all sites emit the same block; D23 keeps timestamps system-managed).
    """

    def test_search_file_dict_keeps_legacy_keys_and_values(self) -> None:
        file = _rich_file()
        block = _search_block(file)
        assert LEGACY_SEARCH_FILE_KEYS <= set(block.keys())
        assert block["id"] == file.id
        assert block["path"] == file.path
        assert block["source_type"] == file.source_type.value
        assert block["file_role"] == file.file_role.value
        assert block["total_chunks"] == file.total_chunks
        assert block["keywords"] == file.aggregated_keywords
        assert block["tags"] == file.aggregated_tags
        assert block["average_importance"] == file.average_importance
        assert block["metadata"] == dict(file.metadata)

    def test_fetch_file_dict_keeps_entity_driven_keys_and_values(self) -> None:
        file = _rich_file()
        block = _fetch_block(file)
        assert LEGACY_FETCH_STABLE_KEYS <= set(block.keys())
        assert block["id"] == file.id
        assert block["path"] == file.path
        assert block["source_type"] == file.source_type.value
        assert block["keywords"] == file.aggregated_keywords
        assert block["tags"] == file.aggregated_tags
        assert block["file_hash"] == file.hash

    def test_enrichment_file_dict_keeps_existing_keys_and_values(self) -> None:
        file = _rich_file()
        block = _enrichment_block(file)
        assert LEGACY_ENRICHMENT_FILE_KEYS <= set(block.keys())
        assert block["id"] == file.id
        assert block["path"] == file.path
        assert block["source_type"] == file.source_type.value
        assert block["total_chunks"] == file.total_chunks
        assert block["average_importance"] == file.average_importance
        assert block["metadata"] == dict(file.metadata)
        assert block["file_hash"] == file.hash


# ---------------------------------------------------------------------------
# Canonical block at each site (red pre-migration, green post-migration)
# ---------------------------------------------------------------------------


class TestCanonicalBlockAtEachSite:
    """Every retrieval site emits EXACTLY the canonical 10-key block —
    legacy search keys + file_hash — with entity values via File.to_dict()."""

    def test_search_file_dict_is_canonical(self) -> None:
        file = _rich_file()
        block = _search_block(file)
        assert set(block.keys()) == CANONICAL_FILE_BLOCK_KEYS
        assert block == file.to_dict()
        assert block["file_hash"] == FILE_HASH

    def test_fetch_file_dict_is_canonical_default_mode(self) -> None:
        file = _rich_file()
        block = _fetch_block(file, mode="default")
        assert set(block.keys()) == CANONICAL_FILE_BLOCK_KEYS
        assert block == file.to_dict()
        assert block["file_hash"] == FILE_HASH

    def test_fetch_file_dict_is_canonical_neighbor_mode(self) -> None:
        file = _rich_file()
        block = _fetch_block(file, mode="neighbor")
        assert set(block.keys()) == CANONICAL_FILE_BLOCK_KEYS
        assert block == file.to_dict()
        assert block["file_hash"] == FILE_HASH

    def test_fetch_file_dict_is_canonical_partial_mode(self) -> None:
        file = _rich_file()
        block = _fetch_block(file, mode="partial")
        assert set(block.keys()) == CANONICAL_FILE_BLOCK_KEYS
        assert block == file.to_dict()
        assert block["file_hash"] == FILE_HASH

    def test_enrichment_file_dict_is_canonical(self) -> None:
        file = _rich_file()
        block = _enrichment_block(file)
        assert set(block.keys()) == CANONICAL_FILE_BLOCK_KEYS
        assert block == file.to_dict()
        assert block["file_hash"] == FILE_HASH

    def test_expand_source_file_is_canonical(self) -> None:
        """The expandFileRelations source_file block delegates to the same
        entity method (rg gate: no hand-built file dicts remain)."""
        file = _rich_file()
        block = _expand_source_block(file)
        assert set(block.keys()) == CANONICAL_FILE_BLOCK_KEYS
        assert block == file.to_dict()
        assert block["file_hash"] == FILE_HASH


# ---------------------------------------------------------------------------
# Cross-site equivalence — one entity ⇒ one block
# ---------------------------------------------------------------------------


class TestCrossSiteEquivalence:
    """Same File input ⇒ identical block at all retrieval sites (D24.1:
    'the entity method is the single source — all sites emit the same
    block')."""

    def test_all_sites_emit_identical_block_for_same_file(self) -> None:
        file = _rich_file()
        search_block = _search_block(file)
        fetch_block = _fetch_block(file, mode="default")
        enrichment_block = _enrichment_block(file)
        expand_block = _expand_source_block(file)

        assert search_block == fetch_block
        assert search_block == enrichment_block
        assert search_block == expand_block
        assert search_block == file.to_dict()
