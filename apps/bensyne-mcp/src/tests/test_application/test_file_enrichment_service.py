"""Unit tests for FileEnrichmentService (D7 — shared two-phase enrichment).

The service enriches recall/search result memories with a `file_enrichment`
block built from REAL entity values (File, FileChunk, FileRelation) via
FileService read passthroughs. Pure memories (no chunk row) pass through
with `file_enrichment: None` and all other fields byte-identical to input.

TDD: these tests were written before the service existed (red), then the
service was implemented to make them green.
"""

from __future__ import annotations

import copy
from datetime import datetime
from typing import Any, Optional
from unittest.mock import MagicMock

import pytest

from src.application.services.file_enrichment_service import FileEnrichmentService
from src.domain.file_chunk_entity import FileChunk
from src.domain.file_entity import File
from src.domain.file_relation_entity import FileRelation
from src.domain.models.file_chunk_model import ContentType as ChunkContentType
from src.domain.models.file_model import FileStatus, SourceType
from src.domain.models.file_relation_model import Direction, RelationType
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock

NOW = datetime(2026, 1, 1, 0, 0, 0)


# ---------------------------------------------------------------------------
# Fixtures (row-based — real entity values, no stubs)
# ---------------------------------------------------------------------------


def _a_file(
    id: str = "f1",
    path: str = "/vault/notes/a.md",
    source_type: SourceType = SourceType.AGENT_SESSION,
    summary: Optional[str] = None,
    total_chunks: int = 0,
    average_importance: float = 0.0,
    metadata: Optional[dict[str, str]] = None,
    keywords: Optional[list[str]] = None,
    tags: Optional[list[str]] = None,
    hash: Optional[str] = "a" * 64,
) -> File:
    return File(
        id=id,
        path=path,
        source_type=source_type,
        file_role=None,
        hash=hash,
        file_type=None,
        size=None,
        language=None,
        aggregated_keywords=keywords or [],
        aggregated_tags=tags or [],
        status=FileStatus.INDEXED,
        summary=summary,
        total_chunks=total_chunks,
        average_importance=average_importance,
        metadata=dict(metadata or {}),
        created_at=NOW,
        updated_at=NOW,
    )


def _a_chunk(
    id: str = "c1",
    file_id: str = "f1",
    memory_id: str = "mem_1",
    chunk_index: int = 0,
    section_header: Optional[str] = None,
    parent_unit_ref: Optional[str] = None,
    parent_unit_summary: Optional[str] = None,
    content_hash: Optional[str] = None,
) -> FileChunk:
    return FileChunk(
        id=id,
        file_id=file_id,
        memory_id=memory_id,
        chunk_index=chunk_index,
        start_line=0,
        end_line=10,
        content_hash=content_hash,
        content_type=ChunkContentType.TEXT,
        is_partial=False,
        section_header=section_header,
        parent_unit_ref=parent_unit_ref,
        parent_unit_summary=parent_unit_summary,
        created_at=NOW,
        updated_at=NOW,
    )


def _a_relation(
    id: str = "r1",
    source_file_id: str = "f1",
    target_file_id: str = "f2",
    relation_type: RelationType = RelationType.SIBLING,
    strength: float = 0.5,
) -> FileRelation:
    return FileRelation(
        id=id,
        source_file_id=source_file_id,
        target_file_id=target_file_id,
        relation_type=relation_type,
        strength=strength,
        direction=Direction.UNIDIRECTIONAL,
        description=None,
        created_at=NOW,
        updated_at=NOW,
    )


def _a_memory(
    id: str = "mem_1",
    content: str = "chunk content",
    importance: float = 0.7,
    relevance_score: float = 0.9,
) -> dict[str, Any]:
    return {
        "id": id,
        "content": content,
        "importance": importance,
        "relevance_score": relevance_score,
    }


def _make_service(
    file: Optional[File] = None,
    chunks: Optional[list[FileChunk]] = None,
    relations: Optional[list[FileRelation]] = None,
    related_files: Optional[dict[str, File]] = None,
) -> tuple[FileEnrichmentService, MagicMock]:
    """Build a service over a fake FileService with the given row data."""
    file_service = MagicMock()

    chunk_by_memory: dict[str, FileChunk] = {c.memory_id: c for c in (chunks or [])}

    def get_chunk(memory_id: str) -> Result[FileChunk | None]:
        return Result.ok(chunk_by_memory.get(memory_id))

    file_service.get_chunk_by_memory_id.side_effect = get_chunk
    file_service.get_file_by_id.return_value = Result.ok(file)
    file_service.get_chunks_by_file_id.return_value = Result.ok(list(chunks or []))
    file_service.get_relations_by_file_id.return_value = Result.ok(list(relations or []))

    related: dict[str, File] = dict(related_files or {})

    def get_related(target_id: str) -> Result[File | None]:
        return Result.ok(related.get(target_id))

    file_service.get_related_file_by_id.side_effect = get_related

    service = FileEnrichmentService(file_service=file_service, logger=LoggerMock())
    return service, file_service


# ---------------------------------------------------------------------------
# AC 1 — file-based memory: real values, sorted relations, related files
# ---------------------------------------------------------------------------


class TestFileBasedMemoryEnrichment:
    def test_enriches_file_based_memory_with_real_file_values(self) -> None:
        """Fixture: file with 3 chunks, relations to 2 files (0.9 / 0.4).

        file.total_chunks is the REAL entity value; relations sorted
        strength-descending; related_files carries id/path/summary/relation.
        """
        source = _a_file(
            total_chunks=3,
            average_importance=0.82,
            summary="File A summary",
            metadata={"session.id": "sess_42"},
        )
        chunks = [
            _a_chunk(id="c1", memory_id="mem_1"),
            _a_chunk(id="c2", memory_id="mem_x", chunk_index=1),
            _a_chunk(id="c3", memory_id="mem_y", chunk_index=2),
        ]
        relations = [
            _a_relation(id="r_low", target_file_id="f3", strength=0.4),
            _a_relation(id="r_high", target_file_id="f2", relation_type=RelationType.BACKLINK, strength=0.9),
        ]
        related_files = {
            "f2": _a_file(id="f2", path="/vault/notes/b.md", summary="File B summary"),
            "f3": _a_file(id="f3", path="/vault/notes/c.md", summary="File C summary"),
        }
        service, _ = _make_service(source, chunks, relations, related_files)

        results = service.enrich([_a_memory()])

        assert len(results) == 1
        enrichment = results[0]["file_enrichment"]
        assert enrichment is not None

        # file block — REAL entity values (no hardcoded zeros/empty dict)
        assert enrichment["file"]["id"] == "f1"
        assert enrichment["file"]["path"] == "/vault/notes/a.md"
        assert enrichment["file"]["total_chunks"] == 3
        assert enrichment["file"]["average_importance"] == pytest.approx(0.82)
        assert enrichment["file"]["metadata"] == {"session.id": "sess_42"}

        # relations — capped at limit (default 5, both fit), strength-descending
        strengths = [r["strength"] for r in enrichment["relations"]]
        assert strengths == [0.9, 0.4]
        relation_ids = [r["id"] for r in enrichment["relations"]]
        assert relation_ids == ["r_high", "r_low"]

        # related_files — one entry per relation's other end
        related = enrichment["related_files"]
        assert len(related) == 2
        top = related[0]
        assert top["id"] == "f2"
        assert top["path"] == "/vault/notes/b.md"
        assert top["summary"] == "File B summary"
        assert top["relation"] == "backlink"
        second = related[1]
        assert second["id"] == "f3"
        assert second["relation"] == "sibling"

    def test_related_file_missing_from_storage_is_skipped(self) -> None:
        """A relation whose other end has no File row is skipped (no crash)."""
        source = _a_file(total_chunks=1)
        chunks = [_a_chunk()]
        relations = [
            _a_relation(id="r_ok", target_file_id="f2", strength=0.9),
            _a_relation(id="r_dangling", target_file_id="f_gone", strength=0.5),
        ]
        related_files = {"f2": _a_file(id="f2", path="/b.md")}
        service, _ = _make_service(source, chunks, relations, related_files)

        results = service.enrich([_a_memory()])
        enrichment = results[0]["file_enrichment"]

        assert [r["id"] for r in enrichment["relations"]] == ["r_ok", "r_dangling"]
        assert [rf["id"] for rf in enrichment["related_files"]] == ["f2"]


# ---------------------------------------------------------------------------
# AC 2 — limit cap
# ---------------------------------------------------------------------------


class TestRelationLimitCap:
    def test_limit_caps_relations_to_top_n_by_strength(self) -> None:
        """limit=1 ⇒ only the strongest (0.9) relation is present."""
        source = _a_file(total_chunks=3)
        chunks = [_a_chunk()]
        relations = [
            _a_relation(id="r_low", target_file_id="f3", strength=0.4),
            _a_relation(id="r_high", target_file_id="f2", strength=0.9),
        ]
        related_files = {
            "f2": _a_file(id="f2", path="/b.md"),
            "f3": _a_file(id="f3", path="/c.md"),
        }
        service, _ = _make_service(source, chunks, relations, related_files)

        results = service.enrich([_a_memory()], limit=1)
        enrichment = results[0]["file_enrichment"]

        assert [r["id"] for r in enrichment["relations"]] == ["r_high"]
        assert [rf["id"] for rf in enrichment["related_files"]] == ["f2"]


# ---------------------------------------------------------------------------
# AC 3 — summary_chain (three separate tests)
# ---------------------------------------------------------------------------


class TestSummaryChain:
    def test_summary_chain_includes_file_summary_when_set(self) -> None:
        """File.summary set ⇒ first element of the chain is File.summary."""
        source = _a_file(summary="The file-level summary", total_chunks=1)
        chunks = [_a_chunk()]
        service, _ = _make_service(source, chunks)

        results = service.enrich([_a_memory()])
        chain = results[0]["file_enrichment"]["summary_chain"]

        assert chain[0] == "The file-level summary"

    def test_summary_chain_includes_distinct_parent_unit_summaries(self) -> None:
        """Distinct non-null parent-unit summaries of the file's chunks appear in order."""
        source = _a_file(summary="File S", total_chunks=3)
        chunks = [
            _a_chunk(id="c1", memory_id="mem_1", parent_unit_ref="ch1", parent_unit_summary="Chapter 1 summary"),
            _a_chunk(id="c2", memory_id="m2", chunk_index=1, parent_unit_ref="ch1", parent_unit_summary="Chapter 1 summary"),
            _a_chunk(id="c3", memory_id="m3", chunk_index=2, parent_unit_ref="ch2", parent_unit_summary="Chapter 2 summary"),
        ]
        service, _ = _make_service(source, chunks)

        results = service.enrich([_a_memory()])
        chain = results[0]["file_enrichment"]["summary_chain"]

        assert chain == ["File S", "Chapter 1 summary", "Chapter 2 summary"]

    def test_summary_chain_falls_back_to_mechanical_summary_when_file_summary_none(self) -> None:
        """File.summary is None ⇒ mechanical path+keywords+tags fallback leads the chain."""
        source = _a_file(
            path="/vault/deep/note.md",
            summary=None,
            total_chunks=1,
            keywords=["alpha", "beta"],
            tags=["t1", "t2"],
        )
        chunks = [
            _a_chunk(id="c1", memory_id="mem_1", section_header="## Section One"),
            _a_chunk(id="c2", memory_id="m2", chunk_index=1, parent_unit_summary="Unit X"),
        ]
        service, _ = _make_service(source, chunks)

        results = service.enrich([_a_memory()])
        chain = results[0]["file_enrichment"]["summary_chain"]

        # Mechanical fallback: path + keywords + tags (no summary stored)
        assert "/vault/deep/note.md" in chain[0]
        assert "alpha, beta" in chain[0]
        assert "t1, t2" in chain[0]
        # Distinct parent-unit summaries still appended after the fallback
        assert chain[1:] == ["Unit X"]


# ---------------------------------------------------------------------------
# AC 4 — pure memory passthrough (byte-identical)
# ---------------------------------------------------------------------------


class TestPureMemoryPassthrough:
    def test_pure_memory_gets_null_enrichment_and_untouched_fields(self) -> None:
        """No chunk row ⇒ file_enrichment is None; every other field deep-equal."""
        memory = _a_memory(id="mem_pure", content="pure recall")
        service, file_service = _make_service()

        results = service.enrich([memory])

        assert len(results) == 1
        result = results[0]
        assert result["file_enrichment"] is None

        # Byte-identical: only the enrichment key may differ from input.
        expected = dict(memory)
        expected["file_enrichment"] = None
        assert result == expected
        for key, value in memory.items():
            assert result[key] == value, f"field {key!r} was modified"

        # No file-layer lookups beyond the chunk probe
        file_service.get_file_by_id.assert_not_called()
        file_service.get_relations_by_file_id.assert_not_called()

    def test_pure_memory_input_dict_not_mutated(self) -> None:
        """The input memory dict is not mutated in place (immutability)."""
        memory = _a_memory(id="mem_pure")
        snapshot = copy.deepcopy(memory)
        service, _ = _make_service()

        service.enrich([memory])

        assert memory == snapshot


# ---------------------------------------------------------------------------
# AC 5 — source_type_enrichment from File.metadata extra keys
# ---------------------------------------------------------------------------


class TestSourceTypeEnrichment:
    def test_source_type_enrichment_carries_metadata_extra_keys(self) -> None:
        """agent_session file with session.* metadata ⇒ same keys in enrichment."""
        source = _a_file(
            source_type=SourceType.AGENT_SESSION,
            metadata={"session.id": "sess_42", "session.started_at": "2026-08-16T10:00:00Z"},
        )
        chunks = [_a_chunk()]
        service, _ = _make_service(source, chunks)

        results = service.enrich([_a_memory()])
        enrichment = results[0]["file_enrichment"]

        assert enrichment["source_type_enrichment"] == {
            "session.id": "sess_42",
            "session.started_at": "2026-08-16T10:00:00Z",
        }

    def test_source_type_enrichment_empty_dict_only_when_no_extra_keys(self) -> None:
        """File.metadata has no extra keys ⇒ empty dict (deliberate, documented)."""
        source = _a_file(metadata={})
        chunks = [_a_chunk()]
        service, _ = _make_service(source, chunks)

        results = service.enrich([_a_memory()])
        enrichment = results[0]["file_enrichment"]

        assert enrichment["source_type_enrichment"] == {}


# ---------------------------------------------------------------------------
# AC 6 — traversal block
# ---------------------------------------------------------------------------


class TestTraversalBlock:
    def test_traversal_carries_file_id_and_relation_ids(self) -> None:
        """traversal = {file_id, relation_ids} in the same (capped, sorted) order."""
        source = _a_file(total_chunks=1)
        chunks = [_a_chunk()]
        relations = [
            _a_relation(id="r_low", target_file_id="f3", strength=0.4),
            _a_relation(id="r_high", target_file_id="f2", strength=0.9),
        ]
        related_files = {
            "f2": _a_file(id="f2", path="/b.md"),
            "f3": _a_file(id="f3", path="/c.md"),
        }
        service, _ = _make_service(source, chunks, relations, related_files)

        results = service.enrich([_a_memory()], limit=1)
        traversal = results[0]["file_enrichment"]["traversal"]

        assert traversal["file_id"] == "f1"
        assert traversal["relation_ids"] == ["r_high"]


# ---------------------------------------------------------------------------
# Edge cases — lookup failures degrade gracefully (no exception across boundary)
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_file_row_missing_treats_memory_as_pure(self) -> None:
        """Chunk row exists but File row missing ⇒ null enrichment, untouched fields."""
        memory = _a_memory(id="mem_1")
        chunks = [_a_chunk()]
        service, file_service = _make_service(file=None, chunks=chunks)
        file_service.get_file_by_id.return_value = Result.ok(None)

        results = service.enrich([memory])

        assert results[0]["file_enrichment"] is None
        expected = dict(memory)
        expected["file_enrichment"] = None
        assert results[0] == expected

    def test_chunk_lookup_error_treats_memory_as_pure(self) -> None:
        """Chunk lookup returns Result.ko ⇒ null enrichment, untouched fields."""
        memory = _a_memory(id="mem_1")
        service, file_service = _make_service()
        file_service.get_chunk_by_memory_id.return_value = Result.ko(
            [ErrorWithDetails("DB_ERROR", {"detail": "boom"})]
        )

        results = service.enrich([memory])

        assert results[0]["file_enrichment"] is None
        expected = dict(memory)
        expected["file_enrichment"] = None
        assert results[0] == expected

    def test_relations_lookup_error_yields_empty_relations(self) -> None:
        """Relations lookup fails ⇒ empty relations, enrichment still present."""
        source = _a_file(total_chunks=1, summary="S")
        chunks = [_a_chunk()]
        service, file_service = _make_service(source, chunks)
        file_service.get_relations_by_file_id.return_value = Result.ko(
            [ErrorWithDetails("DB_ERROR", {"detail": "boom"})]
        )

        results = service.enrich([_a_memory()])
        enrichment = results[0]["file_enrichment"]

        assert enrichment is not None
        assert enrichment["relations"] == []
        assert enrichment["related_files"] == []
        assert enrichment["traversal"]["relation_ids"] == []

    def test_multiple_memories_same_file_share_one_enrichment(self) -> None:
        """Two memories of the same file ⇒ both enriched; lookups not duplicated."""
        source = _a_file(total_chunks=2, summary="S")
        chunks = [
            _a_chunk(id="c1", memory_id="mem_1"),
            _a_chunk(id="c2", memory_id="mem_2", chunk_index=1),
        ]
        service, file_service = _make_service(source, chunks)

        results = service.enrich([_a_memory(id="mem_1"), _a_memory(id="mem_2")])

        assert all(r["file_enrichment"] is not None for r in results)
        assert file_service.get_file_by_id.call_count == 1
        assert file_service.get_relations_by_file_id.call_count == 1

    def test_empty_input_returns_empty_list(self) -> None:
        service, _ = _make_service()
        assert service.enrich([]) == []


# ---------------------------------------------------------------------------
# AC 7 — dual-hash wire contract (D15): file_hash + chunk_hash surfaced
# ---------------------------------------------------------------------------


class TestHashSurfacing:
    """Retrieval surfaces both hashes: `file.file_hash` (from the File row)
    and top-level `chunk_hash` (the recalled memory's chunk row; null for
    legacy/absent rows — S7)."""

    def test_file_block_carries_file_hash_from_file_row(self) -> None:
        """file_hash is the real File.hash entity value (not a stub)."""
        file_hash = "f" * 64
        source = _a_file(total_chunks=1, hash=file_hash)
        chunks = [_a_chunk()]
        service, _ = _make_service(source, chunks)

        results = service.enrich([_a_memory()])
        enrichment = results[0]["file_enrichment"]

        assert enrichment is not None
        assert enrichment["file"]["file_hash"] == file_hash

    def test_file_hash_null_when_file_row_has_none(self) -> None:
        """Legacy File row with NULL hash ⇒ file_hash is null, not an error."""
        source = _a_file(total_chunks=1, hash=None)
        chunks = [_a_chunk()]
        service, _ = _make_service(source, chunks)

        results = service.enrich([_a_memory()])
        enrichment = results[0]["file_enrichment"]

        assert enrichment is not None
        assert enrichment["file"]["file_hash"] is None

    def test_enrichment_carries_recalled_chunks_content_hash(self) -> None:
        """Top-level chunk_hash = content_hash of the chunk row matching the
        recalled memory_id."""
        source = _a_file(total_chunks=1)
        chunk_hash = "c" * 64
        chunks = [_a_chunk(memory_id="mem_1", content_hash=chunk_hash)]
        service, _ = _make_service(source, chunks)

        results = service.enrich([_a_memory(id="mem_1")])
        enrichment = results[0]["file_enrichment"]

        assert enrichment is not None
        assert enrichment["chunk_hash"] == chunk_hash

    def test_chunk_hash_null_for_legacy_row(self) -> None:
        """Legacy chunk row (NULL content_hash) ⇒ chunk_hash is null, not an
        error (S7 — additive null, no backfill)."""
        source = _a_file(total_chunks=1)
        chunks = [_a_chunk(memory_id="mem_1", content_hash=None)]
        service, _ = _make_service(source, chunks)

        results = service.enrich([_a_memory(id="mem_1")])
        enrichment = results[0]["file_enrichment"]

        assert enrichment is not None
        assert enrichment["chunk_hash"] is None

    def test_chunk_hash_is_per_memory_not_shared_via_file_cache(self) -> None:
        """Two memories of the SAME file carry their OWN chunk_hash each —
        the per-file cache must not leak one memory's chunk_hash into another
        (the cached file-level block is shared; chunk_hash is per-memory)."""
        source = _a_file(total_chunks=2)
        hash_1 = "1" * 64
        hash_2 = "2" * 64
        chunks = [
            _a_chunk(id="c1", memory_id="mem_1", chunk_index=0, content_hash=hash_1),
            _a_chunk(id="c2", memory_id="mem_2", chunk_index=1, content_hash=hash_2),
        ]
        service, file_service = _make_service(source, chunks)

        results = service.enrich([_a_memory(id="mem_1"), _a_memory(id="mem_2")])

        # File-level lookups still deduplicated (cache intact).
        assert file_service.get_file_by_id.call_count == 1
        # But each memory surfaces its own chunk row's content_hash.
        assert results[0]["file_enrichment"]["chunk_hash"] == hash_1
        assert results[1]["file_enrichment"]["chunk_hash"] == hash_2

    def test_pure_memory_enrichment_still_null_with_hashes_around(self) -> None:
        """Pure memory (no chunk row) ⇒ file_enrichment stays null (D7) —
        hashes never invented for absent rows."""
        source = _a_file(total_chunks=1, hash="f" * 64)
        # Chunk exists for mem_other only — mem_pure has none.
        chunks = [_a_chunk(memory_id="mem_other", content_hash="c" * 64)]
        service, _ = _make_service(source, chunks)

        results = service.enrich([_a_memory(id="mem_pure")])

        assert results[0]["file_enrichment"] is None
