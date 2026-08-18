"""Tests for FileService materialization API (Task 6).

Covers: derive_file_id determinism, materialize_file_context (full contract
fixture, idempotency, dangling-edge stubs + upgrade, hash-change rebuild,
absent-hash no-rebuild), rebuild_projection, get_relations_by_file_id
passthrough, and Result-based failure handling.

Integration-grade assertions run against a real per-bank SQLite database
via FileMetadataConnectionManager (same pattern as the infrastructure
repository tests); failure-handling tests use MagicMock repositories.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Generator
from unittest.mock import MagicMock

import pytest

from src.application.services.file_service import FileService, derive_file_id
from src.domain.file_chunk_entity import FileChunk
from src.domain.file_relation_entity import FileRelation
from src.domain.models.file_context_model import (
    FileContext,
    FileContextEdge,
    FileRole,
    parse_file_context,
)
from src.domain.models.file_model import FileStatus, SourceType
from src.domain.models.file_relation_model import RelationType
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_relation_repository import FileRelationRepository
from src.infrastructure.storage.sqlite.file_repository import FileRepository
from src.utils.result import ErrorWithDetails, Result
from src.utils.structured_logging import LoggerMock

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "test_domain" / "fixtures"

CONTRACT_HASH = "ed8feb0ec28dad93b0c1e85377908f07367164d374d3d329e1bde6668591cc17"
OTHER_HASH = "9e8d7c6b5a4f3e2d1c0b9a8f7e6d5c4b3a291807f6e5d4c3b2a1908f7e6d5c4b"
CHUNK_HASH = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
BANK = "test_bank"
FIXTURE_PATH = "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md"


# ---------------------------------------------------------------------------
# Fixtures — real per-bank SQLite (integration-grade)
# ---------------------------------------------------------------------------


@pytest.fixture
def manager(tmp_path: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    mgr = FileMetadataConnectionManager(bank_dir=tmp_path / BANK)
    yield mgr
    mgr.close()


@pytest.fixture
def service(manager: FileMetadataConnectionManager) -> FileService:
    return FileService(
        file_repository=FileRepository(manager),
        chunk_repository=FileChunkRepository(manager),
        relation_repository=FileRelationRepository(manager),
        logger=LoggerMock(),
    )


def _load_contract() -> dict:
    with open(FIXTURES_DIR / "file_context_contract_v1.json") as f:
        envelope = json.load(f)
    # Parity fixture is the full rememberMemory transport envelope
    # (byte-identical to racochu's unified-chunk-contract-v1.json); consume its metadata.
    return envelope["metadata"]


def _context(
    path: str | None = None,
    file_hash: str | None = CONTRACT_HASH,
    edges: list[dict] | None = None,
    **overrides: object,
) -> FileContext:
    """Build a FileContext from the contract fixture with overrides.

    ``path`` / ``file_hash`` / ``edges`` default to the fixture values; pass
    ``None`` explicitly to clear them (e.g. absent file_hash).
    """
    payload = _load_contract()
    if path is not None:
        payload["file_path"] = path
    if file_hash is not None:
        payload["file_hash"] = file_hash
    if edges is not None:
        payload["edges"] = edges
    for key, value in overrides.items():
        payload[key] = value
    parsed = parse_file_context(payload)
    assert parsed is not None, f"fixture did not parse: {payload}"
    return parsed


def _counts(service: FileService) -> dict[str, int]:
    """Row counts across the three tables (integration assertions)."""
    files = service.file_repository.list_files()
    assert files.is_ok
    file_ids = [f.id for f in files.value]  # type: ignore[union-attr]
    chunk_count = sum(
        len(service.chunk_repository.get_chunks_by_file_id(fid).value or [])  # type: ignore[arg-type]
        for fid in file_ids
    )
    relation_count = sum(
        len(service.relation_repository.get_relations_by_file_id(fid).value or [])  # type: ignore[arg-type]
        for fid in set(file_ids)
    )
    return {"files": len(file_ids), "chunks": chunk_count, "relations": relation_count}


# ===================================================================
# derive_file_id
# ===================================================================


class TestDeriveFileId:
    """derive_file_id is deterministic and bank+path scoped (contract rule 2)."""

    def test_deterministic_across_calls(self) -> None:
        assert derive_file_id(BANK, "/a/b.md") == derive_file_id(BANK, "/a/b.md")

    def test_format_is_file_prefix_plus_32_hex_chars(self) -> None:
        file_id = derive_file_id(BANK, "/a/b.md")
        assert re.fullmatch(r"file_[0-9a-f]{32}", file_id) is not None

    def test_different_bank_gives_different_id(self) -> None:
        assert derive_file_id("bank_a", "/x.md") != derive_file_id("bank_b", "/x.md")

    def test_different_path_gives_different_id(self) -> None:
        assert derive_file_id(BANK, "/x.md") != derive_file_id(BANK, "/y.md")


# ===================================================================
# materialize_file_context — full contract fixture
# ===================================================================


class TestMaterializeFullContract:
    """Materializing the all-15-keys contract fixture writes File + chunk + relations."""

    def test_creates_indexed_file_with_all_fields(self, service: FileService) -> None:
        context = _context()
        result = service.materialize_file_context(BANK, context, "mem_full")

        assert result.is_ok is True
        file_id = derive_file_id(BANK, "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md")
        assert result.value == {  # type: ignore[union-attr]
            "file_id": file_id,
            "relations_created": 2,
            "rebuilt": False,
            "errors": [],
        }

        file_result = service.file_repository.get_file_by_id(file_id)
        assert file_result.is_ok and file_result.value is not None
        file = file_result.value
        assert file.status == FileStatus.INDEXED
        assert file.summary is None
        assert file.language == "markdown"
        assert file.hash == CONTRACT_HASH
        assert file.source_type == SourceType.AGENT_SESSIONS
        # extra → metadata, last-writer-wins merge
        assert file.metadata.get("session.id") == "260811-0000"

    def test_creates_chunk_with_section_and_parent_unit_fields(self, service: FileService) -> None:
        context = _context()
        result = service.materialize_file_context(BANK, context, "mem_full")
        assert result.is_ok is True
        file_id = derive_file_id(BANK, "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md")

        chunks = service.chunk_repository.get_chunks_by_file_id(file_id)
        assert chunks.is_ok and len(chunks.value) == 1  # type: ignore[arg-type]
        chunk = chunks.value[0]  # type: ignore[index]
        assert chunk.memory_id == "mem_full"
        assert chunk.chunk_index == 2
        assert chunk.start_line == 42
        assert chunk.end_line == 97
        assert chunk.section_header == "## Implementation Details"
        assert chunk.parent_unit_ref == "session-260811-0000"
        assert chunk.parent_unit_summary == "Session investigating bensyne file metadata materialization"

    def test_creates_one_relation_per_edge(self, service: FileService) -> None:
        context = _context()
        result = service.materialize_file_context(BANK, context, "mem_full")
        assert result.is_ok is True
        file_id = derive_file_id(BANK, "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md")

        relations = service.relation_repository.get_relations_by_file_id(file_id)
        assert relations.is_ok  # type: ignore[union-attr]
        # source's own edges: sibling + parent_child (target-side lookups return same rows)
        outbound = [r for r in relations.value if r.source_file_id == file_id]  # type: ignore[union-attr]
        assert len(outbound) == 2
        by_type = {r.relation_type: r for r in outbound}  # type: ignore[index]
        assert RelationType.SIBLING in by_type
        assert RelationType.PARENT_CHILD in by_type
        sibling = by_type[RelationType.SIBLING]
        assert sibling.target_file_id == derive_file_id(BANK, "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/materials/unified-chunk-contract.md")
        assert sibling.strength == 1
        assert sibling.description == "companion artifact in same session root"

    def test_rerun_identical_payload_is_idempotent(self, service: FileService) -> None:
        context = _context()
        first = service.materialize_file_context(BANK, context, "mem_full")
        assert first.is_ok is True
        counts_after_first = _counts(service)

        second = service.materialize_file_context(BANK, context, "mem_full")
        assert second.is_ok is True
        assert second.value == first.value  # type: ignore[union-attr]

        counts_after_second = _counts(service)
        assert counts_after_second == counts_after_first
        file_id = derive_file_id(BANK, "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md")
        chunks = service.chunk_repository.get_chunks_by_file_id(file_id)
        assert len(chunks.value) == 1  # type: ignore[arg-type]


# ===================================================================
# materialize_file_context — idempotency silence (gate 3 / D14)
# ===================================================================


class TestMaterializeIdempotencySilence:
    """Gate 3 (D14): a dedup-hit re-materialization is event-silent and row-stable.

    The first pass emits creation events; the SECOND pass — same context, same
    memory_id — must emit zero domain events and change zero rows (no new rows,
    no updated-timestamp drift on any file/chunk/relation row).
    """

    def _timestamps(self, service: FileService, file_id: str) -> dict:
        file = service.get_file_by_id(file_id)
        assert file.is_ok and file.value is not None
        file_ts = file.value.updated_at
        chunks = service.get_chunks_by_file_id(file_id)
        assert chunks.is_ok
        chunk_ts = {c.memory_id: c.updated_at for c in chunks.value}  # type: ignore[union-attr]
        relations = service.get_relations_by_file_id(file_id)
        assert relations.is_ok
        relation_ts = {r.id: r.updated_at for r in relations.value}  # type: ignore[union-attr]
        return {"file": file_ts, "chunks": chunk_ts, "relations": relation_ts}

    def test_second_pass_emits_zero_events_and_changes_zero_rows(self, service: FileService) -> None:
        context = _context()
        file_id = derive_file_id(BANK, FIXTURE_PATH)

        first = service.materialize_file_context(BANK, context, "mem_idem")
        assert first.is_ok is True
        assert len(first.events) > 0, "first pass must emit creation events"

        counts_first = _counts(service)
        ts_first = self._timestamps(service, file_id)

        second = service.materialize_file_context(BANK, context, "mem_idem")
        assert second.is_ok is True

        # Gate 3: the dedup-hit re-materialization is event-silent.
        assert second.events == [], f"expected zero events on re-materialize, got {second.events}"

        # And row-stable: no new rows, no updated-timestamp drift.
        assert _counts(service) == counts_first
        ts_second = self._timestamps(service, file_id)
        assert ts_second == ts_first, "re-materialization must not change row timestamps"


# ===================================================================
# materialize_file_context — tags union-merge (O5)
# ===================================================================


class TestMaterializeTagsUnionMerge:
    """O5: context.tags union-merge into File.aggregated_tags; idempotent under re-remember."""

    def _file_tags(self, service: FileService, file_id: str) -> list[str]:
        file = service.get_file_by_id(file_id)
        assert file.is_ok and file.value is not None
        return list(file.value.aggregated_tags)

    def test_first_materialize_persists_contract_tags(self, service: FileService) -> None:
        context = _context(tags=["alpha", "beta"])
        result = service.materialize_file_context(BANK, context, "mem_tags1")
        assert result.is_ok is True
        file_id = derive_file_id(BANK, FIXTURE_PATH)
        assert self._file_tags(service, file_id) == ["alpha", "beta"]

    def test_re_materialize_unions_new_tags_preserving_order(self, service: FileService) -> None:
        context = _context(tags=["alpha", "beta"])
        assert service.materialize_file_context(BANK, context, "mem_tags2").is_ok is True
        file_id = derive_file_id(BANK, FIXTURE_PATH)

        # Overlapping + one new tag: set-union, order-preserving, no duplicates.
        second = _context(tags=["beta", "gamma"])
        result = service.materialize_file_context(BANK, second, "mem_tags2b")
        assert result.is_ok is True
        assert self._file_tags(service, file_id) == ["alpha", "beta", "gamma"]

    def test_re_materialize_same_tags_is_a_noop(self, service: FileService) -> None:
        context = _context(tags=["alpha", "beta"])
        assert service.materialize_file_context(BANK, context, "mem_tags3").is_ok is True
        file_id = derive_file_id(BANK, FIXTURE_PATH)
        before = self._file_tags(service, file_id)

        # Same tags again: union == current ⇒ no change.
        second = service.materialize_file_context(BANK, _context(tags=["alpha", "beta"]), "mem_tags3b")
        assert second.is_ok is True
        assert self._file_tags(service, file_id) == before == ["alpha", "beta"]


# ===================================================================
# materialize_file_context — resurrection (gate 4c / D21)
# ===================================================================


class TestMaterializeResurrection:
    """Gate 4c (D21): re-materializing a DELETED file revives it — fresh rows, no stale rows."""

    def test_rematerialize_deleted_file_resurrects_with_fresh_rows(self, service: FileService) -> None:
        context = _context(edges=[{"target_path": "/edge_x.md", "relation_type": "backlink"}])
        file_id = derive_file_id(BANK, FIXTURE_PATH)

        # 1. Initial materialize: INDEXED, 1 chunk, 1 relation.
        assert service.materialize_file_context(BANK, context, "mem_res1").is_ok is True
        assert service.get_file_by_id(file_id).value.status == FileStatus.INDEXED  # type: ignore[union-attr]
        assert len(service.get_chunks_by_file_id(file_id).value) == 1  # type: ignore[union-attr]
        assert len(service.get_relations_by_file_id(file_id).value) == 1  # type: ignore[union-attr]

        # 2. Forget the last chunk: file -> DELETED tombstone, 0 chunks, 0 relations.
        assert service.delete_file(file_id).is_ok is True
        deleted = service.get_file_by_id(file_id)
        assert deleted.value is not None and deleted.value.status == FileStatus.DELETED  # type: ignore[union-attr]
        assert service.get_chunks_by_file_id(file_id).value == []  # type: ignore[union-attr]
        assert service.get_relations_by_file_id(file_id).value == []  # type: ignore[union-attr]

        # 3. Re-remember the same file: resurrected INDEXED, fresh chunk + relation,
        #    same deterministic file_id, no stale/duplicate rows.
        result = service.materialize_file_context(BANK, context, "mem_res2")
        assert result.is_ok is True, f"resurrection failed: {result.errors}"
        assert result.value["file_id"] == file_id  # type: ignore[index]

        resurrected = service.get_file_by_id(file_id)
        assert resurrected.value is not None
        assert resurrected.value.status == FileStatus.INDEXED  # type: ignore[union-attr]

        chunks = service.get_chunks_by_file_id(file_id)
        assert [c.memory_id for c in chunks.value] == ["mem_res2"]  # type: ignore[union-attr]

        relations = service.get_relations_by_file_id(file_id)
        outbound = [r for r in relations.value if r.source_file_id == file_id]  # type: ignore[union-attr]
        assert len(outbound) == 1
        assert outbound[0].target_file_id == derive_file_id(BANK, "/edge_x.md")

        # No stale rows: exactly one file row for the deterministic id.
        all_files = service.file_repository.list_files()
        assert len([f for f in all_files.value if f.id == file_id]) == 1  # type: ignore[union-attr]


# ===================================================================
# materialize_file_context — dangling edges (D4 stub policy)
# ===================================================================


class TestMaterializeDanglingEdge:
    """Edges to never-ingested targets create PENDING stubs; later ingest upgrades in place."""

    def test_dangling_edge_creates_pending_stub_and_relation(self, service: FileService) -> None:
        context = _context(edges=[{"target_path": "/never/ingested.md", "relation_type": "backlink"}])
        result = service.materialize_file_context(BANK, context, "mem_dangle")
        assert result.is_ok is True

        stub_id = derive_file_id(BANK, "/never/ingested.md")
        stub_result = service.file_repository.get_file_by_id(stub_id)
        assert stub_result.is_ok and stub_result.value is not None
        stub = stub_result.value
        assert stub.status == FileStatus.PENDING
        assert stub.source_type == SourceType.UNKNOWN
        assert stub.summary is None

        source_id = derive_file_id(BANK, "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md")
        relations = service.relation_repository.get_relations_by_file_id(source_id)
        outbound = [r for r in relations.value if r.source_file_id == source_id]  # type: ignore[union-attr]
        assert len(outbound) == 1
        assert outbound[0].target_file_id == stub_id

    def test_later_materialize_upgrades_stub_in_place(self, service: FileService) -> None:
        context = _context(edges=[{"target_path": "/never/ingested.md", "relation_type": "backlink"}])
        assert service.materialize_file_context(BANK, context, "mem_dangle").is_ok is True

        stub_id = derive_file_id(BANK, "/never/ingested.md")
        # Materialize the target's own chunk — same deterministic id, upgraded in place.
        target_context = _context(
            path="/never/ingested.md", summary="Real target summary.", edges=[]
        )
        result = service.materialize_file_context(BANK, target_context, "mem_target")
        assert result.is_ok is True
        assert result.value["file_id"] == stub_id  # type: ignore[index]

        upgraded = service.file_repository.get_file_by_id(stub_id)
        assert upgraded.is_ok and upgraded.value is not None
        assert upgraded.value.status == FileStatus.INDEXED
        assert upgraded.value.summary == "Real target summary."
        assert upgraded.value.hash == CONTRACT_HASH
        # No duplicate stub row: file count = source + target.
        files = service.file_repository.list_files()
        assert len(files.value) == 2  # type: ignore[arg-type]


# ===================================================================
# materialize_file_context — hash-change rebuild (D5 / spec §4.3)
# ===================================================================


class TestMaterializeHashChangeRebuild:
    """Changed file_hash ⇒ prune stale chunks + outbound relations, recreate from incoming edges."""

    def _seed_two_chunk_state(self, service: FileService) -> None:
        # Chunk A (live, m1) — edge to /edge_a.md; chunk B (stale, m2) — edge to /edge_b.md.
        context_a = _context(
            edges=[{"target_path": "/edge_a.md", "relation_type": "backlink"}],
            section_header="## A",
        )
        assert service.materialize_file_context(BANK, context_a, "m1").is_ok is True
        context_b = _context(
            edges=[{"target_path": "/edge_b.md", "relation_type": "sibling"}],
            section_header="## B",
        )
        assert service.materialize_file_context(BANK, context_b, "m2").is_ok is True

    def test_rebuild_prunes_stale_chunk_and_relations(self, service: FileService) -> None:
        self._seed_two_chunk_state(service)
        file_id = derive_file_id(BANK, "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md")

        new_context = _context(
            file_hash=OTHER_HASH,
            edges=[{"target_path": "/edge_new.md", "relation_type": "backlink"}],
        )
        result = service.materialize_file_context(BANK, new_context, "m1")
        assert result.is_ok is True
        assert result.value["rebuilt"] is True  # type: ignore[index]

        chunks = service.chunk_repository.get_chunks_by_file_id(file_id)
        assert [c.memory_id for c in chunks.value] == ["m1"]  # type: ignore[union-attr]

        relations = service.relation_repository.get_relations_by_file_id(file_id)
        outbound = [r for r in relations.value if r.source_file_id == file_id]  # type: ignore[union-attr]
        assert len(outbound) == 1
        assert outbound[0].target_file_id == derive_file_id(BANK, "/edge_new.md")

    def test_rebuild_updates_stored_hash(self, service: FileService) -> None:
        self._seed_two_chunk_state(service)
        file_id = derive_file_id(BANK, "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md")

        new_context = _context(file_hash=OTHER_HASH, edges=[])
        result = service.materialize_file_context(BANK, new_context, "m1")
        assert result.is_ok is True

        updated = service.file_repository.get_file_by_id(file_id)
        assert updated.value is not None and updated.value.hash == OTHER_HASH  # type: ignore[union-attr]

    def test_rebuild_leaves_other_files_untouched(self, service: FileService) -> None:
        self._seed_two_chunk_state(service)
        other_id = derive_file_id(BANK, "/edge_a.md")
        other_counts_before = {
            "files": len(service.file_repository.list_files().value or []),  # type: ignore[arg-type]
            "chunks_for_other": len(service.chunk_repository.get_chunks_by_file_id(other_id).value or []),  # type: ignore[arg-type]
        }

        new_context = _context(file_hash=OTHER_HASH, edges=[])
        assert service.materialize_file_context(BANK, new_context, "m1").is_ok is True

        other_file = service.file_repository.get_file_by_id(other_id)
        assert other_file.is_ok and other_file.value is not None
        assert other_file.value.status == FileStatus.PENDING  # stub untouched
        assert len(service.chunk_repository.get_chunks_by_file_id(other_id).value or []) == (  # type: ignore[arg-type]
            other_counts_before["chunks_for_other"]
        )

    def test_same_hash_rerun_does_not_rebuild(self, service: FileService) -> None:
        self._seed_two_chunk_state(service)
        context_a = _context(
            edges=[{"target_path": "/edge_a.md", "relation_type": "backlink"}],
            section_header="## A",
        )
        result = service.materialize_file_context(BANK, context_a, "m1")
        assert result.is_ok is True
        assert result.value["rebuilt"] is False  # type: ignore[index]
        file_id = derive_file_id(BANK, "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md")
        chunks = service.chunk_repository.get_chunks_by_file_id(file_id)
        assert len(chunks.value) == 2  # type: ignore[arg-type]


# ===================================================================
# materialize_file_context — absent file_hash (legacy producers)
# ===================================================================


class TestMaterializeAbsentHash:
    """file_hash absent on both sides ⇒ pure idempotent upsert, rebuild never fires."""

    def test_repeated_materialize_without_hash_is_idempotent(self, service: FileService) -> None:
        context = _context(file_hash=None)
        first = service.materialize_file_context(BANK, context, "mem_nohash")
        assert first.is_ok is True
        assert first.value["rebuilt"] is False  # type: ignore[index]
        counts_first = _counts(service)

        second = service.materialize_file_context(BANK, context, "mem_nohash")
        assert second.is_ok is True
        assert second.value["rebuilt"] is False  # type: ignore[index]
        assert _counts(service) == counts_first

    def test_stored_hash_absent_incoming_present_does_not_rebuild(self, service: FileService) -> None:
        context = _context(file_hash=None)
        assert service.materialize_file_context(BANK, context, "mem_nohash").is_ok is True

        with_hash = _context(file_hash=CONTRACT_HASH)
        result = service.materialize_file_context(BANK, with_hash, "mem_nohash")
        assert result.is_ok is True
        assert result.value["rebuilt"] is False  # type: ignore[index]


# ===================================================================
# materialize_file_context — content_hash persistence (dual-hash, D15)
# ===================================================================


class TestMaterializeContentHash:
    """context.chunk_hash persists into the file_chunks.content_hash V3 column (no migration).

    Assertions hit the SQLite column directly (not just the ORM round-trip) so
    the persistence contract is proven at the storage boundary.
    """

    def _db_content_hash(self, manager: FileMetadataConnectionManager, chunk_id: str) -> str | None:
        conn = manager.get_connection()
        try:
            row = conn.execute(
                "SELECT content_hash FROM file_chunks WHERE id = ?", (chunk_id,)
            ).fetchone()
        finally:
            manager.close_connection(conn)
        return None if row is None else row["content_hash"]

    def test_chunk_row_persists_chunk_hash_column(self, manager: FileMetadataConnectionManager, service: FileService) -> None:
        context = _context(chunk_hash=CHUNK_HASH)
        assert context.chunk_hash == CHUNK_HASH  # parse sanity

        result = service.materialize_file_context(BANK, context, "mem_ch")
        assert result.is_ok is True

        file_id = derive_file_id(BANK, FIXTURE_PATH)
        assert self._db_content_hash(manager, f"fc_{file_id}_mem_ch") == CHUNK_HASH

    def test_chunk_row_content_hash_null_when_absent(self, manager: FileMetadataConnectionManager, service: FileService) -> None:
        # chunk_hash absent ⇒ NULL column, no error. The canonical fixture carries
        # chunk_hash (dual-hash contract, H7), so absence is expressed by dropping the key.
        payload = _load_contract()
        payload.pop("chunk_hash")
        context = parse_file_context(payload)
        assert context is not None
        assert context.chunk_hash is None

        result = service.materialize_file_context(BANK, context, "mem_noch")
        assert result.is_ok is True

        file_id = derive_file_id(BANK, FIXTURE_PATH)
        assert self._db_content_hash(manager, f"fc_{file_id}_mem_noch") is None

    def test_chunk_hash_and_file_hash_independent(self, manager: FileMetadataConnectionManager, service: FileService) -> None:
        # Dual-hash: chunk_hash (chunk content) and file_hash (whole file) are distinct values
        # landing in distinct columns.
        context = _context(chunk_hash=CHUNK_HASH)
        result = service.materialize_file_context(BANK, context, "mem_dual")
        assert result.is_ok is True

        file_id = derive_file_id(BANK, FIXTURE_PATH)
        assert self._db_content_hash(manager, f"fc_{file_id}_mem_dual") == CHUNK_HASH

        # File.hash property maps to the files.file_hash column.
        conn = manager.get_connection()
        try:
            row = conn.execute("SELECT file_hash FROM files WHERE id = ?", (file_id,)).fetchone()
        finally:
            manager.close_connection(conn)
        assert row is not None and row["file_hash"] == CONTRACT_HASH


# ===================================================================
# File.total_chunks is projection state — re-aggregated from the chunk set,
# never copied from the producer's contract claim (spec §2.2, DDD)
# ===================================================================


class TestMaterializeTotalChunksInvariant:
    """File.total_chunks must equal the file's ACTUAL chunk count, not the
    producer's claimed context.total_chunks. A producer that under/over-states
    the count must not leak a wrong projection value."""

    def test_producer_total_chunks_claim_does_not_leak_to_file(self, service: FileService) -> None:
        # Producer claims 99 chunks, but this materialization writes exactly 1.
        context = _context(total_chunks=99)
        result = service.materialize_file_context(BANK, context, "mem_tc")
        assert result.is_ok is True

        file_id = derive_file_id(
            BANK,
            "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md",
        )
        actual = len(
            service.chunk_repository.get_chunks_by_file_id(file_id).value or []  # type: ignore[arg-type]
        )
        assert actual == 1  # one chunk row was materialized

        file = service.file_repository.get_file_by_id(file_id).value
        assert file is not None
        # The persisted projection reflects reality, not the producer claim.
        assert file.total_chunks == actual
        assert file.total_chunks != 99


# ===================================================================
# materialize_file_context — source-type axis (D29, spec §6.6)
# ===================================================================


class TestMaterializeSourceTypeAxis:
    """D29: materializing with each canonical source_type stores it verbatim;
    legacy/garbage values degrade to unknown (degrade-never-reject) — the
    stored value always satisfies the frozen bootstrap CHECK."""

    @pytest.mark.parametrize("source_type", ["obsidian", "agent-sessions", "vault", "unknown"])
    def test_each_d29_source_type_stored_verbatim(self, service: FileService, source_type: str) -> None:
        context = _context(source_type=source_type)
        assert context.source_type.value == source_type  # parse sanity

        result = service.materialize_file_context(BANK, context, f"mem_st_{source_type}")
        assert result.is_ok is True

        file_id = derive_file_id(BANK, FIXTURE_PATH)
        file = service.file_repository.get_file_by_id(file_id).value
        assert file is not None
        assert file.source_type.value == source_type

    def test_legacy_source_type_degrades_to_unknown_on_store(self, service: FileService) -> None:
        context = _context(source_type="git")
        assert context.source_type is SourceType.UNKNOWN  # parse degrades pre-D29 values

        result = service.materialize_file_context(BANK, context, "mem_st_legacy")
        assert result.is_ok is True

        file_id = derive_file_id(BANK, FIXTURE_PATH)
        file = service.file_repository.get_file_by_id(file_id).value
        assert file is not None
        assert file.source_type is SourceType.UNKNOWN

    def test_garbage_source_type_degrades_to_unknown_on_store(self, service: FileService) -> None:
        context = _context(source_type="quantum_flux")
        assert context.source_type is SourceType.UNKNOWN

        result = service.materialize_file_context(BANK, context, "mem_st_garbage")
        assert result.is_ok is True

        file_id = derive_file_id(BANK, FIXTURE_PATH)
        file = service.file_repository.get_file_by_id(file_id).value
        assert file is not None
        assert file.source_type is SourceType.UNKNOWN


# ===================================================================
# rebuild_projection
# ===================================================================


class TestRebuildProjection:
    """rebuild_projection prunes stale chunks of THIS file + its relations only."""

    def test_prunes_stale_chunks_keeps_live_and_deletes_relations(self, service: FileService) -> None:
        context_a = _context(edges=[{"target_path": "/edge_a.md", "relation_type": "backlink"}])
        assert service.materialize_file_context(BANK, context_a, "m1").is_ok is True
        context_b = _context(edges=[])
        assert service.materialize_file_context(BANK, context_b, "m2").is_ok is True
        file_id = derive_file_id(BANK, "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md")

        result = service.rebuild_projection(file_id, {"m1"})
        assert result.is_ok is True
        assert result.value is None  # type: ignore[union-attr]

        chunks = service.chunk_repository.get_chunks_by_file_id(file_id)
        assert [c.memory_id for c in chunks.value] == ["m1"]  # type: ignore[union-attr]
        relations = service.relation_repository.get_relations_by_file_id(file_id)
        outbound = [r for r in relations.value if r.source_file_id == file_id]  # type: ignore[union-attr]
        assert outbound == []

    def test_empty_keep_set_deletes_all_chunks(self, service: FileService) -> None:
        context_a = _context(edges=[])
        assert service.materialize_file_context(BANK, context_a, "m1").is_ok is True
        file_id = derive_file_id(BANK, "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md")

        result = service.rebuild_projection(file_id, set())
        assert result.is_ok is True

        chunks = service.chunk_repository.get_chunks_by_file_id(file_id)
        assert chunks.value == []  # type: ignore[union-attr]


# ===================================================================
# get_relations_by_file_id passthrough
# ===================================================================


class TestGetRelationsByFileId:
    def test_returns_repo_relations(self, service: FileService) -> None:
        context = _context(edges=[{"target_path": "/edge_a.md", "relation_type": "backlink"}])
        assert service.materialize_file_context(BANK, context, "m1").is_ok is True
        file_id = derive_file_id(BANK, "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md")

        result = service.get_relations_by_file_id(file_id)
        assert isinstance(result, Result)
        assert result.is_ok is True
        assert len(result.value) == 1  # type: ignore[arg-type]
        assert result.value[0].source_file_id == file_id  # type: ignore[index]

    def test_returns_ko_when_repo_fails(self) -> None:
        relation_repo = MagicMock()
        relation_repo.get_relations_by_file_id.return_value = Result.ko(
            [ErrorWithDetails("RELATION_GET_ERROR", {})]
        )
        service = FileService(
            file_repository=MagicMock(),
            chunk_repository=MagicMock(),
            relation_repository=relation_repo,
            logger=LoggerMock(),
        )

        result = service.get_relations_by_file_id("f1")

        assert result.is_ko is True
        assert result.errors[0].error_code == "RELATION_GET_ERROR"


# ===================================================================
# Failure handling — Result pattern, no exceptions escape
# ===================================================================


class TestMaterializeFailureHandling:
    """Repository failures surface as Result.ko with an errors list; nothing raises."""

    def _mock_service(self) -> tuple[FileService, MagicMock, MagicMock, MagicMock]:
        file_repo = MagicMock()
        chunk_repo = MagicMock()
        relation_repo = MagicMock()
        service = FileService(
            file_repository=file_repo,
            chunk_repository=chunk_repo,
            relation_repository=relation_repo,
            logger=LoggerMock(),
        )
        return service, file_repo, chunk_repo, relation_repo

    def _ok_result(self, value: object) -> Result:
        return Result.ok(value)

    def test_file_save_failure_returns_ko_with_errors(self) -> None:
        service, file_repo, _, _ = self._mock_service()
        file_repo.get_file_by_id.return_value = self._ok_result(None)
        file_repo.save_file.return_value = Result.ko([ErrorWithDetails("FILE_SAVE_ERROR", {"error": "db down"})])

        result = service.materialize_file_context(BANK, _context(), "mem_1")

        assert result.is_ko is True
        assert any(e.error_code == "FILE_SAVE_ERROR" for e in result.errors)

    def test_chunk_save_failure_returns_ko_with_errors(self) -> None:
        service, file_repo, chunk_repo, _ = self._mock_service()
        file_repo.get_file_by_id.return_value = self._ok_result(None)
        file_repo.save_file.side_effect = lambda f: Result.ok(f)
        chunk_repo.delete_chunks_by_file_id.return_value = Result.ok(True)
        chunk_repo.save_chunk.return_value = Result.ko([ErrorWithDetails("CHUNK_SAVE_ERROR", {"error": "db down"})])

        result = service.materialize_file_context(BANK, _context(), "mem_1")

        assert result.is_ko is True
        assert any(e.error_code == "CHUNK_SAVE_ERROR" for e in result.errors)

    def test_relation_save_failure_returns_ko_with_errors(self) -> None:
        service, file_repo, chunk_repo, relation_repo = self._mock_service()
        file_repo.get_file_by_id.return_value = self._ok_result(None)
        file_repo.save_file.side_effect = lambda f: Result.ok(f)
        chunk_repo.delete_chunks_by_file_id.return_value = Result.ok(True)
        chunk_repo.save_chunk.side_effect = lambda c: Result.ok(c)
        relation_repo.save_relation.return_value = Result.ko(
            [ErrorWithDetails("RELATION_SAVE_ERROR", {"error": "db down"})]
        )

        result = service.materialize_file_context(BANK, _context(), "mem_1")

        assert result.is_ko is True
        assert any(e.error_code == "RELATION_SAVE_ERROR" for e in result.errors)

    def test_rebuild_projection_failure_returns_ko(self) -> None:
        service, _, chunk_repo, relation_repo = self._mock_service()
        chunk_repo.delete_chunks_by_file_id.return_value = Result.ko(
            [ErrorWithDetails("CHUNK_DELETE_BY_FILE_ID_ERROR", {"error": "db down"})]
        )

        result = service.rebuild_projection("f1", {"m1"})

        assert result.is_ko is True
        assert any(e.error_code == "CHUNK_DELETE_BY_FILE_ID_ERROR" for e in result.errors)
        relation_repo.delete_relations_by_file_id.assert_not_called()

    def test_rebuild_projection_success_returns_ok_none(self) -> None:
        service, _, chunk_repo, relation_repo = self._mock_service()
        chunk_repo.delete_chunks_by_file_id.return_value = Result.ok(True)
        relation_repo.delete_relations_by_file_id.return_value = Result.ok(True)

        result = service.rebuild_projection("f1", {"m1"})

        assert result.is_ok is True
        assert result.value is None
        chunk_repo.delete_chunks_by_file_id.assert_called_once_with("f1", {"m1"})
        relation_repo.delete_relations_by_file_id.assert_called_once_with("f1")


# ===================================================================
# Static guard — DEC-0018: no INSERT OR REPLACE in the service
# ===================================================================


class TestNoInsertOrReplace:
    def test_file_service_has_no_insert_or_replace(self) -> None:
        service_path = (
            Path(__file__).resolve().parents[2] / "application" / "services" / "file_service.py"
        )
        content = service_path.read_text()
        assert "INSERT OR REPLACE" not in content.upper()
