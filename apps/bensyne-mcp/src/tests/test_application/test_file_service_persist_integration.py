"""Task 5 — persistence contract integration tests (spec §3.2 / §6.1 / §6.2).

Real per-bank SQLite database (FileMetadataConnectionManager), no mocks on
the repositories. Proves the _load_aggregate + _persist chokepoint
semantics end-to-end:

1. File-only flows (update_file) leave chunk and relation rows
   byte-identical — the write flags never touch rows that were not loaded.
2. Legacy fr_{source}_{target} relation rows converge to the canonical
   fr_{source}_{target}_{type} id on the first service persist that loads
   them, with content preserved and no duplicate rows.
3. remove_chunk prunes the removed chunk row and keeps surviving rows.

No logger assertions — every assertion is on row identity / counts /
entity values.
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from src.application.services.file_service import FileService, derive_file_id
from src.domain.file_chunk_entity import FileChunk
from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.file_relation_entity import Direction, FileRelation, RelationType
from src.domain.models.file_context_model import FileContext, FileContextEdge
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_relation_repository import FileRelationRepository
from src.infrastructure.storage.sqlite.file_repository import FileRepository
from src.utils.structured_logging import LoggerMock

NOW = datetime(2026, 1, 1, 0, 0, 0)
HASH_A = "a" * 64
HASH_B = "b" * 64

# ---------------------------------------------------------------------------
# Fixtures — real per-bank SQLite (integration-grade)
# ---------------------------------------------------------------------------


@pytest.fixture
def manager(tmp_path: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    mgr = FileMetadataConnectionManager(bank_dir=tmp_path / "persist_bank")
    yield mgr
    mgr.close()


@pytest.fixture
def file_repo(manager: FileMetadataConnectionManager) -> FileRepository:
    return FileRepository(manager)


@pytest.fixture
def chunk_repo(manager: FileMetadataConnectionManager) -> FileChunkRepository:
    return FileChunkRepository(manager)


@pytest.fixture
def relation_repo(manager: FileMetadataConnectionManager) -> FileRelationRepository:
    return FileRelationRepository(manager)


@pytest.fixture
def file_service(
    manager: FileMetadataConnectionManager,
) -> FileService:
    return FileService(
        file_repository=FileRepository(manager),
        chunk_repository=FileChunkRepository(manager),
        relation_repository=FileRelationRepository(manager),
        logger=LoggerMock(),
    )


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_file(file_repo: FileRepository, file_id: str = "f1", path: str = "/vault/f.md") -> File:
    result = File.of(
        {
            "id": file_id,
            "path": path,
            "source_type": SourceType.UNKNOWN,
            "hash": HASH_A,
            "status": FileStatus.INDEXED,
            "created_at": NOW,
        }
    )
    assert result.is_ok, f"Failed to seed file {file_id}: {result.errors}"
    saved = file_repo.save_file(result.value)
    assert saved.is_ok, f"Failed to save file {file_id}: {saved.errors}"
    return saved.value


def _seed_chunk(chunk_repo: FileChunkRepository, file_id: str, memory_id: str, chunk_index: int = 0) -> FileChunk:
    result = FileChunk.of(
        {
            "id": f"fc_{file_id}_{memory_id}",
            "file_id": file_id,
            "memory_id": memory_id,
            "chunk_index": chunk_index,
            "start_line": 1,
            "end_line": 10,
            # Deterministic valid hex content hash per memory.
            "content_hash": hashlib.sha256(memory_id.encode("utf-8")).hexdigest(),
        }
    )
    assert result.is_ok, f"Failed to seed chunk {memory_id}: {result.errors}"
    saved = chunk_repo.save_chunk(result.value)
    assert saved.is_ok, f"Failed to save chunk {memory_id}: {saved.errors}"
    return saved.value


def _seed_relation(
    relation_repo: FileRelationRepository,
    id: str,
    source_file_id: str,
    target_file_id: str,
    relation_type: RelationType,
    strength: float = 0.7,
    description: str | None = "seeded",
) -> FileRelation:
    result = FileRelation.of(
        {
            "id": id,
            "source_file_id": source_file_id,
            "target_file_id": target_file_id,
            "relation_type": relation_type,
            "strength": strength,
            "direction": Direction.UNIDIRECTIONAL,
            "description": description,
            "created_at": NOW,
        }
    )
    assert result.is_ok, f"Failed to seed relation {id}: {result.errors}"
    saved = relation_repo.save_relation(result.value)
    assert saved.is_ok, f"Failed to save relation {id}: {saved.errors}"
    return saved.value


def _chunk_row_ids(chunk_repo: FileChunkRepository, file_id: str) -> list[str]:
    result = chunk_repo.get_chunks_by_file_id(file_id)
    assert result.is_ok
    return sorted(c.id for c in result.value)


def _relation_rows(relation_repo: FileRelationRepository, file_id: str) -> dict[str, tuple]:
    """Snapshot all relation rows touching file_id as (id → immutable content tuple)."""
    result = relation_repo.get_relations_by_file_id(file_id)
    assert result.is_ok
    return {
        r.id: (
            r.source_file_id,
            r.target_file_id,
            r.relation_type,
            r.strength,
            r.direction,
            r.description,
            r.created_at,
            r.updated_at,
        )
        for r in result.value
    }


# ---------------------------------------------------------------------------
# 1. File-only flows leave child rows byte-identical
# ---------------------------------------------------------------------------


class TestFileOnlyFlowRowIdentity:
    """update_file is a file-only flow: zero writes to chunk/relation rows."""

    def test_update_file_leaves_chunk_and_relation_rows_byte_identical(
        self,
        file_service: FileService,
        file_repo: FileRepository,
        chunk_repo: FileChunkRepository,
        relation_repo: FileRelationRepository,
    ) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2", "/vault/g.md")
        _seed_chunk(chunk_repo, "f1", "mem_1", chunk_index=0)
        _seed_chunk(chunk_repo, "f1", "mem_2", chunk_index=1)
        _seed_relation(relation_repo, "fr_f1_f2_parent_child", "f1", "f2", RelationType.PARENT_CHILD)
        _seed_relation(relation_repo, "fr_f1_f2_sibling", "f1", "f2", RelationType.SIBLING, strength=0.3)

        chunks_before = _chunk_row_ids(chunk_repo, "f1")
        relations_before = _relation_rows(relation_repo, "f1")

        result = file_service.update_file("bank1", "f1", {"summary": "refreshed summary"})

        assert result.is_ok is True
        # The file row was actually updated.
        updated = file_repo.get_file_by_id("f1")
        assert updated.is_ok and updated.value is not None
        assert updated.value.summary == "refreshed summary"
        # Child rows byte-identical (ids AND content, incl. timestamps).
        assert _chunk_row_ids(chunk_repo, "f1") == chunks_before
        assert _relation_rows(relation_repo, "f1") == relations_before

    def test_update_file_on_absent_file_returns_ko_and_creates_no_row(
        self,
        file_service: FileService,
        file_repo: FileRepository,
    ) -> None:
        """update_file never fabricates identity: absent file_id → ko, no row."""
        # Seed one unrelated file so the bank has rows to count against.
        _seed_file(file_repo, "f_existing")
        rows_before = file_repo.list_files()
        assert rows_before.is_ok
        count_before = len(rows_before.value)

        result = file_service.update_file("bank1", "no_such_file", {"summary": "x"})

        assert result.is_ko is True
        # No row for the unknown id...
        absent = file_repo.get_file_by_id("no_such_file")
        assert absent.is_ok and absent.value is None
        # ...and the file table size is unchanged (no implicit create).
        rows_after = file_repo.list_files()
        assert rows_after.is_ok
        assert len(rows_after.value) == count_before

# ---------------------------------------------------------------------------
# 2. Legacy relation id convergence (spec §6.2)
# ---------------------------------------------------------------------------


class TestLegacyRelationConvergence:
    """Stored legacy fr_{s}_{t} rows converge to canonical ids on first persist."""

    def test_legacy_row_converges_on_first_service_persist(
        self,
        file_service: FileService,
        file_repo: FileRepository,
        relation_repo: FileRelationRepository,
    ) -> None:
        """A materialization persist that loads a stored legacy fr_{s}_{t} row
        converges it to the canonical id, with content preserved."""
        f1 = derive_file_id("bank1", "/vault/f.md")
        f2 = derive_file_id("bank1", "/vault/g.md")
        _seed_file(file_repo, f1, "/vault/f.md")
        _seed_file(file_repo, f2, "/vault/g.md")
        # Pre-convergence legacy row: id without the relation-type suffix.
        _seed_relation(
            relation_repo,
            f"fr_{f1}_{f2}",
            f1,
            f2,
            RelationType.PARENT_CHILD,
            strength=0.7,
            description="legacy",
        )

        context = FileContext(
            contract_version=1,
            file_path="/vault/f.md",
            chunk_index=0,
            total_chunks=1,
            section_header=None,
            start_line=None,
            end_line=None,
            source_type=SourceType.UNKNOWN,
            file_role=None,
            language=None,
            # Must equal the stored hash — otherwise rebuild_projection fires
            # and invalidates the convergence under test.
            file_hash=HASH_A,
            chunk_hash=None,
            summary=None,
            parent_unit=None,
            edges=(
                FileContextEdge(
                    target_path="/vault/g.md",
                    relation_type=RelationType.PARENT_CHILD,
                    strength=0.7,
                    description="legacy",
                ),
            ),
            tags=(),
            extra={},
        )

        result = file_service.materialize_file_context("bank1", context, "mem_converge")

        assert result.is_ok is True
        # The legacy row is gone.
        legacy = relation_repo.get_relation_by_id(f"fr_{f1}_{f2}")
        assert legacy.is_ok and legacy.value is None
        # The canonical row exists with content preserved.
        canonical = relation_repo.get_relation_by_id(f"fr_{f1}_{f2}_parent_child")
        assert canonical.is_ok and canonical.value is not None
        row = canonical.value
        assert row.strength == 0.7
        assert row.description == "legacy"
        assert row.relation_type == RelationType.PARENT_CHILD
        # Exactly one row for this pair — no duplicate.
        pair = relation_repo.get_by_pair(f1, f2, RelationType.PARENT_CHILD)
        assert pair.is_ok and pair.value is not None
        assert pair.value.id == f"fr_{f1}_{f2}_parent_child"
        all_rows = relation_repo.get_relations_by_file_id(f1)
        assert all_rows.is_ok
        assert len(all_rows.value) == 1

    def test_legacy_row_and_canonical_row_coexisting_converge_to_one(
        self,
        file_service: FileService,
        file_repo: FileRepository,
        chunk_repo: FileChunkRepository,
        relation_repo: FileRelationRepository,
    ) -> None:
        """Worst-case pre-convergence state: both ids stored for the same pair.
        Any full persist (here: remove_chunk) loads both rows and converges
        them to the single canonical row."""
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2", "/vault/g.md")
        _seed_chunk(chunk_repo, "f1", "mem_a", chunk_index=0)
        _seed_relation(relation_repo, "fr_f1_f2", "f1", "f2", RelationType.SIBLING, strength=0.5)
        _seed_relation(
            relation_repo,
            "fr_f1_f2_sibling",
            "f1",
            "f2",
            RelationType.SIBLING,
            strength=0.9,
        )

        result = file_service.remove_chunk("f1", "mem_a")

        assert result.is_ok is True
        legacy = relation_repo.get_relation_by_id("fr_f1_f2")
        assert legacy.is_ok and legacy.value is None
        canonical = relation_repo.get_relation_by_id("fr_f1_f2_sibling")
        assert canonical.is_ok and canonical.value is not None
        all_rows = relation_repo.get_relations_by_file_id("f1")
        assert all_rows.is_ok
        assert len(all_rows.value) == 1


# ---------------------------------------------------------------------------
# 3. Chunk prune via keep-set on remove_chunk
# ---------------------------------------------------------------------------


class TestRemoveChunkRowPrune:
    """remove_chunk prunes the removed row and keeps surviving rows intact."""

    def test_remove_chunk_prunes_removed_row_keeps_survivors(
        self,
        file_service: FileService,
        file_repo: FileRepository,
        chunk_repo: FileChunkRepository,
    ) -> None:
        _seed_file(file_repo, "f1")
        _seed_chunk(chunk_repo, "f1", "mem_a", chunk_index=0)
        _seed_chunk(chunk_repo, "f1", "mem_b", chunk_index=1)
        before = _chunk_row_ids(chunk_repo, "f1")
        assert before == ["fc_f1_mem_a", "fc_f1_mem_b"]

        result = file_service.remove_chunk("f1", "mem_a")

        assert result.is_ok is True
        after = _chunk_row_ids(chunk_repo, "f1")
        assert after == ["fc_f1_mem_b"]
        survivor = chunk_repo.get_chunk_by_memory_id("mem_b")
        assert survivor.is_ok and survivor.value is not None
        assert survivor.value.chunk_index == 1


# ---------------------------------------------------------------------------
# 4. get_by_pair on real SQLite (service-side visibility)
# ---------------------------------------------------------------------------


class TestGetByPairIntegration:
    """get_by_pair as seen through the service's relation repository."""

    def test_get_by_pair_finds_seeded_row(
        self,
        file_repo: FileRepository,
        relation_repo: FileRelationRepository,
    ) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2", "/vault/g.md")
        _seed_relation(relation_repo, "fr_f1_f2_dependency", "f1", "f2", RelationType.DEPENDENCY)

        result = relation_repo.get_by_pair("f1", "f2", RelationType.DEPENDENCY)

        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "fr_f1_f2_dependency"

    def test_get_by_pair_clean_not_found(
        self,
        file_repo: FileRepository,
        relation_repo: FileRelationRepository,
    ) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2", "/vault/g.md")

        result = relation_repo.get_by_pair("f1", "f2", RelationType.DEPENDENCY)

        assert result.is_ok is True
        assert result.value is None


# ---------------------------------------------------------------------------
# 5. DELETED cascade at _persist (D20, spec §6.3) — status-driven, single
#    location. A persist of a DELETED file prunes its chunk rows AND its
#    relation rows (as source OR target) BEFORE saving the tombstone; a
#    non-DELETED persist leaves child rows byte-identical.
# ---------------------------------------------------------------------------


class TestDeletedCascade:
    """Persisting a DELETED file prunes chunks + relations (both sides), then
    saves the tombstone. The cascade is status-driven, not call-site-driven."""

    def test_deleted_persist_prunes_chunks_and_relations_both_sides(
        self,
        file_service: FileService,
        file_repo: FileRepository,
        chunk_repo: FileChunkRepository,
        relation_repo: FileRelationRepository,
    ) -> None:
        """f1 has chunks + relations as BOTH source (f1→f2) and target (f3→f1).
        Deleting f1 prunes all of them; unrelated rows of f2/f3 stay intact."""
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2", "/vault/g.md")
        _seed_file(file_repo, "f3", "/vault/h.md")
        _seed_chunk(chunk_repo, "f1", "mem_a", chunk_index=0)
        _seed_chunk(chunk_repo, "f1", "mem_b", chunk_index=1)
        _seed_chunk(chunk_repo, "f2", "mem_g", chunk_index=0)
        _seed_chunk(chunk_repo, "f3", "mem_h", chunk_index=0)
        # f1 as source, f1 as target, plus an unrelated f2→f3 edge.
        _seed_relation(relation_repo, "fr_f1_f2_sibling", "f1", "f2", RelationType.SIBLING)
        _seed_relation(relation_repo, "fr_f3_f1_dependency", "f3", "f1", RelationType.DEPENDENCY)
        _seed_relation(relation_repo, "fr_f2_f3_parent_child", "f2", "f3", RelationType.PARENT_CHILD)

        f2_chunks_before = _chunk_row_ids(chunk_repo, "f2")
        f3_chunks_before = _chunk_row_ids(chunk_repo, "f3")
        f2_relations_before = _relation_rows(relation_repo, "f2")
        f3_relations_before = _relation_rows(relation_repo, "f3")

        result = file_service.delete_file("f1")

        assert result.is_ok is True
        # Tombstone: file row still exists and is marked DELETED.
        tomb = file_repo.get_file_by_id("f1")
        assert tomb.is_ok and tomb.value is not None
        assert tomb.value.status == FileStatus.DELETED
        # f1's chunk rows are gone.
        assert _chunk_row_ids(chunk_repo, "f1") == []
        # f1's relation rows are gone as BOTH source and target.
        assert _relation_rows(relation_repo, "f1") == {}
        # The f1→f2 edge is gone from f2's (target) view; the unrelated
        # f2→f3 edge survives with byte-identical content + timestamps.
        f2_relations_after = _relation_rows(relation_repo, "f2")
        assert "fr_f1_f2_sibling" not in f2_relations_after
        assert f2_relations_after == {"fr_f2_f3_parent_child": f2_relations_before["fr_f2_f3_parent_child"]}
        # The f3→f1 edge is gone from f3's (source) view; the unrelated f2→f3
        # edge (f3 is target) survives byte-identical.
        f3_relations_after = _relation_rows(relation_repo, "f3")
        assert "fr_f3_f1_dependency" not in f3_relations_after
        assert f3_relations_after == {
            "fr_f2_f3_parent_child": f3_relations_before["fr_f2_f3_parent_child"]
        }
        # Chunk rows of f2/f3 are untouched.
        assert _chunk_row_ids(chunk_repo, "f2") == f2_chunks_before
        assert _chunk_row_ids(chunk_repo, "f3") == f3_chunks_before
        # f2/f3 file rows are untouched — still exist, not DELETED.
        for fid in ("f2", "f3"):
            row = file_repo.get_file_by_id(fid)
            assert row.is_ok and row.value is not None
            assert row.value.status != FileStatus.DELETED

    def test_non_deleted_full_persist_leaves_rows_byte_identical(
        self,
        file_service: FileService,
        file_repo: FileRepository,
        chunk_repo: FileChunkRepository,
        relation_repo: FileRelationRepository,
    ) -> None:
        """A non-DELETED full-flow persist (remove_chunk) must NOT fire the
        cascade: existing relation rows (both sides) stay byte-identical and
        the keep-set prune drops exactly the removed chunk row."""
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2", "/vault/g.md")
        _seed_file(file_repo, "f3", "/vault/h.md")
        _seed_chunk(chunk_repo, "f1", "mem_a", chunk_index=0)
        _seed_chunk(chunk_repo, "f1", "mem_b", chunk_index=1)
        _seed_relation(relation_repo, "fr_f1_f2_sibling", "f1", "f2", RelationType.SIBLING)
        _seed_relation(relation_repo, "fr_f3_f1_dependency", "f3", "f1", RelationType.DEPENDENCY)

        relations_before = _relation_rows(relation_repo, "f1")

        result = file_service.remove_chunk("f1", "mem_a")

        assert result.is_ok is True
        # The keep-set prune drops exactly the removed chunk row.
        chunks_after = _chunk_row_ids(chunk_repo, "f1")
        assert chunks_after == ["fc_f1_mem_b"]
        # Both relation rows (f1 as source AND target) survive byte-identically.
        assert _relation_rows(relation_repo, "f1") == relations_before
        # File stays INDEXED — the cascade did not fire.
        row = file_repo.get_file_by_id("f1")
        assert row.is_ok and row.value is not None
        assert row.value.status == FileStatus.INDEXED
