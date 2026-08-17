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
        assert file.source_type == SourceType.AGENT_SESSION
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
        chunk_repo.save_chunk.return_value = Result.ko([ErrorWithDetails("CHUNK_SAVE_ERROR", {"error": "db down"})])

        result = service.materialize_file_context(BANK, _context(), "mem_1")

        assert result.is_ko is True
        assert any(e.error_code == "CHUNK_SAVE_ERROR" for e in result.errors)

    def test_relation_save_failure_returns_ko_with_errors(self) -> None:
        service, file_repo, chunk_repo, relation_repo = self._mock_service()
        file_repo.get_file_by_id.return_value = self._ok_result(None)
        file_repo.save_file.side_effect = lambda f: Result.ok(f)
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
