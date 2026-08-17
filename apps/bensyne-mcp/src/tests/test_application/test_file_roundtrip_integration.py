"""Integration round-trips for the remember → file-layer → recall pipeline (Task 18).

Four end-to-end round-trips per spec §6.4, all against a REAL per-bank SQLite
database (FileMetadataConnectionManager) with ONLY the mnemosyne client mocked:

1. remember→recall enriched round-trip — file_enrichment populated end-to-end
2. re-ingest rebuild (S7) — stale chunks pruned, keep-set chunk survives,
   relations recreated from v2 edges only, other files untouched
3. dangling stub → upgrade — PENDING stub row upgraded in place to INDEXED
   with the SAME deterministic file_id
4. forget symmetry — forgetting all chunks of a file leaves 0 chunk rows and
   0 relation rows referencing it (existing forget semantics: File marked
   DELETED, not removed)

No logger assertions anywhere — every assertion is on row counts, entity
values, or response shapes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generator

import pytest
from unittest.mock import MagicMock

from src.application.services.file_enrichment_service import FileEnrichmentService
from src.application.services.file_service import FileService, derive_file_id
from src.application.use_cases.fetch_file_use_case import FetchFileUseCase
from src.application.use_cases.forget_memory_use_case import ForgetMemoryUseCase
from src.application.use_cases.recall_memory_use_case import RecallMemoryUseCase
from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
from src.domain.file_entity import FileStatus
from src.domain.memory_entity import Memory
from src.infrastructure.mcp.hash_index_service import HashIndexService
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_relation_repository import FileRelationRepository
from src.infrastructure.storage.sqlite.file_repository import FileRepository
from src.utils.result import Result
from src.utils.structured_logging import LoggerMock

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "test_domain" / "fixtures"

BANK = "rt_bank"
PATH_F = "/vault/notes/f.md"
PATH_G = "/vault/notes/g.md"
PATH_X = "/vault/notes/never-ingested.md"

HASH_V1 = "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
HASH_V2 = "b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90ab"

# Distinct per-chunk content hashes (D13 chunk_hash) — must differ per chunk
# so the dedup index never treats them as the same memory.
CHASH_F1 = "e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4"
CHASH_F2 = "f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5"

# Contract v1 payload — same shape as test_domain/fixtures/file_context_contract_v1.json
CONTRACT_TEMPLATE = {
    "contract_version": 1,
    "file_path": PATH_F,
    "chunk_index": 0,
    "total_chunks": 2,
    "section_header": "## Section One",
    "start_line": 1,
    "end_line": 40,
    "source_type": "agent_session",
    "file_role": "docs",
    "language": "markdown",
    "file_hash": HASH_V1,
    "summary": "File-level summary of F.",
    "parent_unit": {"ref": "sec-1", "summary": "Parent unit (section) summary."},
    "edges": [
        {
            "target_path": PATH_G,
            "relation_type": "backlink",
            "strength": 0.8,
            "description": "wikilink from F to G",
        }
    ],
    "tags": ["note"],
    "extra": {"session.id": "ses_rt"},
}


def _contract(**overrides: object) -> dict:
    """Deep-copy the contract template with top-level overrides."""
    payload = json.loads(json.dumps(CONTRACT_TEMPLATE))
    for key, value in overrides.items():
        payload[key] = value
    return payload


# ---------------------------------------------------------------------------
# Fixtures — real per-bank SQLite (integration-grade)
# ---------------------------------------------------------------------------


@pytest.fixture
def manager(tmp_path: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    mgr = FileMetadataConnectionManager(bank_dir=tmp_path / BANK)
    yield mgr
    mgr.close()


@pytest.fixture
def file_service(manager: FileMetadataConnectionManager) -> FileService:
    return FileService(
        file_repository=FileRepository(manager),
        chunk_repository=FileChunkRepository(manager),
        relation_repository=FileRelationRepository(manager),
        logger=LoggerMock(),
    )


@pytest.fixture
def hash_index(tmp_path: Path, manager: FileMetadataConnectionManager) -> HashIndexService:
    # Real hash index (SQLite at tmp path) — only mnemosyne is mocked.
    return HashIndexService(memory_bank=BANK, db_path=tmp_path / "hash_index.db")


def _mock_mnemosyne() -> MagicMock:
    """Mocked MnemosyneClient: save echoes the memory id, recall/forget scripted per test."""
    client = MagicMock()

    def _save(memory: Memory) -> Result[Memory]:
        return Result.ok(memory)

    client.save.side_effect = _save
    client.recall.return_value = Result.ok([])
    client.forget.return_value = Result.ok(True)
    return client


def _remember_use_case(
    mnemosyne: MagicMock, hash_index: HashIndexService, file_service: FileService
) -> RememberMemoryUseCase:
    return RememberMemoryUseCase(
        memory_repository=mnemosyne,
        hash_index_service=hash_index,
        file_service=file_service,
        logger=LoggerMock(),
    )


def _recall_use_case(mnemosyne: MagicMock, file_service: FileService) -> RecallMemoryUseCase:
    return RecallMemoryUseCase(
        mnemosyne_client=mnemosyne,
        file_enrichment_service=FileEnrichmentService(file_service=file_service, logger=LoggerMock()),
        logger=LoggerMock(),
    )


def _forget_use_case(
    mnemosyne: MagicMock, hash_index: HashIndexService, file_service: FileService
) -> ForgetMemoryUseCase:
    return ForgetMemoryUseCase(
        mnemosyne_client=mnemosyne,
        hash_index_service=hash_index,
        logger=LoggerMock(),
        file_service=file_service,
        chunk_repository=file_service.chunk_repository,
        bank_type_checker=lambda bank: "pure_memories",
    )


def _remember_chunk(
    use_case: RememberMemoryUseCase, memory_id: str, content: str, metadata: dict
) -> tuple[dict, str]:
    """Remember one chunk; assert stored + materialized ok.

    Returns (response, actual_memory_id). The mocked mnemosyne save echoes the
    Memory entity as-is, so the generated uuid is deterministic per call —
    callers must use the returned id for recall/forget/re-ingest assertions.
    """
    response = use_case.execute(
        {
            "memory_bank": BANK,
            "content": content,
            "importance": 0.5,
            "source": "integration-test",
            "scope": "working",
            "metadata": metadata,
        }
    )
    # NOTE: get_formatted_errors() crashes on pydantic error details (ValueError
    # not JSON-serializable) — a latent production bug in Result.get_formatted_errors;
    # assert the raw errors list instead.
    assert response.is_ok, f"remember failed: {response.errors}"
    value = response.value
    assert isinstance(value, dict)
    assert value["status"] == "stored"
    materialization = value.get("file_materialization")
    assert materialization is not None, "expected file_materialization in response"
    assert materialization["status"] == "ok", f"materialization failed: {materialization}"
    return value, value["memory_id"]


def _chunk_rows(file_service: FileService, file_id: str) -> list:
    result = file_service.get_chunks_by_file_id(file_id)
    assert result.is_ok
    return result.value  # type: ignore[return-value]


def _relation_rows(file_service: FileService, file_id: str) -> list:
    result = file_service.get_relations_by_file_id(file_id)
    assert result.is_ok
    return result.value  # type: ignore[return-value]


def _file_row(file_service: FileService, file_id: str):
    result = file_service.get_file_by_id(file_id)
    assert result.is_ok
    return result.value  # may be None


FILE_ID_F = derive_file_id(BANK, PATH_F)
FILE_ID_G = derive_file_id(BANK, PATH_G)
FILE_ID_X = derive_file_id(BANK, PATH_X)


# ===================================================================
# Round-trip 1 — remember → recall enriched
# ===================================================================


class TestRememberRecallEnrichedRoundTrip:
    """Remember 2 chunks of F (with edge F→G), then recall returns a
    file-based result whose file_enrichment is populated end-to-end."""

    def test_recall_result_carries_populated_file_enrichment(
        self, file_service: FileService, hash_index: HashIndexService
    ) -> None:
        mnemosyne = _mock_mnemosyne()
        remember = _remember_use_case(mnemosyne, hash_index, file_service)

        # Chunk 1 of F — carries the F→G edge + its own chunk_hash (D13).
        chunk1_meta = _contract(chunk_index=0, total_chunks=2, chunk_hash=CHASH_F1)
        _, mid1 = _remember_chunk(remember, "m_f_1", "content of chunk one", chunk1_meta)

        # Chunk 2 of F — no edges (only the first chunk carries them).
        chunk2_meta = _contract(
            chunk_index=1,
            total_chunks=2,
            section_header="## Section Two",
            start_line=41,
            end_line=80,
            parent_unit={"ref": "sec-2", "summary": "Section two summary."},
            edges=[],
            chunk_hash=CHASH_F2,
        )
        _, mid2 = _remember_chunk(remember, "m_f_2", "content of chunk two", chunk2_meta)

        # Mocked mnemosyne recall returns both memories (by their actual ids).
        recalled = [
            {"id": mid1, "content": "content of chunk one"},
            {"id": mid2, "content": "content of chunk two"},
        ]
        mnemosyne.recall.return_value = Result.ok(recalled)

        recall = _recall_use_case(mnemosyne, file_service)
        result = recall.execute({"query": "chunk one", "memory_bank": BANK})
        assert result.is_ok, f"recall failed: {result.errors}"
        rows = result.value["results"]  # type: ignore[index]
        assert len(rows) == 2

        for row in rows:
            enrichment = row["file_enrichment"]
            assert enrichment is not None, "expected populated file_enrichment"

            # file block — real entity values.
            file_block = enrichment["file"]
            assert file_block["id"] == FILE_ID_F
            assert file_block["path"] == PATH_F
            assert file_block["total_chunks"] == 2
            assert file_block["metadata"]["session.id"] == "ses_rt"
            # Dual-hash contract (D15): file_hash from the real File row.
            assert file_block["file_hash"] == HASH_V1

            # Dual-hash contract (D15): top-level chunk_hash = the content_hash
            # of THIS recalled memory's chunk row (per-memory, not per-file).
            expected_chunk_hash = CHASH_F1 if row["id"] == mid1 else CHASH_F2
            assert enrichment["chunk_hash"] == expected_chunk_hash

            # relations — F→G present (edge from chunk 1).
            relation_rows = enrichment["relations"]
            assert len(relation_rows) == 1
            rel = relation_rows[0]
            assert rel["relation_type"] == "backlink"
            assert rel["strength"] == 0.8

            # related_files — G resolved via the stub row created by the edge.
            related = enrichment["related_files"]
            assert len(related) == 1
            assert related[0]["id"] == FILE_ID_G
            assert related[0]["path"] == PATH_G
            assert related[0]["relation"] == "backlink"

            # traversal — handles for expandFileRelations/fetchFile.
            traversal = enrichment["traversal"]
            assert traversal["file_id"] == FILE_ID_F
            assert len(traversal["relation_ids"]) == 1
            assert rel["id"] == traversal["relation_ids"][0]

    def test_chunk_rows_and_file_state_after_remember(
        self, file_service: FileService, hash_index: HashIndexService
    ) -> None:
        mnemosyne = _mock_mnemosyne()
        remember = _remember_use_case(mnemosyne, hash_index, file_service)

        _, mid1 = _remember_chunk(remember, "m_f_1", "content of chunk one", _contract(chunk_index=0))
        _, mid2 = _remember_chunk(
            remember,
            "m_f_2",
            "content of chunk two",
            _contract(chunk_index=1, edges=[]),
        )

        # F: INDEXED with 2 chunk rows; G: PENDING stub (edge target never ingested).
        file_f = _file_row(file_service, FILE_ID_F)
        assert file_f is not None
        assert file_f.status == FileStatus.INDEXED
        assert file_f.total_chunks == 2

        chunks = _chunk_rows(file_service, FILE_ID_F)
        assert sorted(c.memory_id for c in chunks) == sorted([mid1, mid2])

        # Legacy wire (no chunk_hash in metadata) ⇒ content_hash column stays
        # NULL (S7 — no backfill possible; retrieval surfaces null, not error).
        assert all(c.content_hash is None for c in chunks)

        file_g = _file_row(file_service, FILE_ID_G)
        assert file_g is not None
        assert file_g.status == FileStatus.PENDING

        relations = _relation_rows(file_service, FILE_ID_F)
        assert len(relations) == 1
        assert relations[0].source_file_id == FILE_ID_F
        assert relations[0].target_file_id == FILE_ID_G


# ===================================================================
# Round-trip 2 — re-ingest rebuild (S7)
# ===================================================================


class TestReIngestRebuild:
    """Remember F v1 (hash H1, chunks m1+m2) then F v2 (hash H2, chunk m3):
    stale chunks pruned, relations recreated from v2 edges only, file_hash
    updated to H2. S7 variant: a chunk whose memory_id IS in the keep-set
    survives; other files' rows are untouched."""

    def test_stale_chunks_pruned_and_relations_recreated(
        self, file_service: FileService, hash_index: HashIndexService
    ) -> None:
        mnemosyne = _mock_mnemosyne()
        remember = _remember_use_case(mnemosyne, hash_index, file_service)

        # v1: two chunks, edge F→G.
        _, mid1 = _remember_chunk(remember, "m_f_1", "v1 chunk one", _contract(chunk_index=0, total_chunks=2))
        _, mid2 = _remember_chunk(
            remember,
            "m_f_2",
            "v1 chunk two",
            _contract(chunk_index=1, total_chunks=2, edges=[]),
        )
        assert len(_chunk_rows(file_service, FILE_ID_F)) == 2
        assert len(_relation_rows(file_service, FILE_ID_F)) == 1

        # v2: single new chunk (mock save echoes the generated uuid), NO edges
        # (edge F→G must disappear).
        v2_meta = _contract(chunk_index=0, total_chunks=1, file_hash=HASH_V2, edges=[])
        response = remember.execute(
            {
                "memory_bank": BANK,
                "content": "v2 chunk three",
                "importance": 0.5,
                "source": "integration-test",
                "scope": "working",
                "metadata": v2_meta,
            }
        )
        assert response.is_ok
        value = response.value
        assert value["status"] == "stored"
        assert value["file_materialization"]["status"] == "ok"
        mid3 = value["memory_id"]

        # Stale chunks m1/m2 pruned; exactly one chunk row (the v2 chunk) remains.
        chunks = _chunk_rows(file_service, FILE_ID_F)
        assert len(chunks) == 1
        assert "m1" not in [c.memory_id for c in chunks]
        assert "m2" not in [c.memory_id for c in chunks]
        assert chunks[0].memory_id == mid3

        # Relations recreated from v2 edges only — v2 had none.
        relations = _relation_rows(file_service, FILE_ID_F)
        assert relations == []

        # file_hash updated to H2; G stub row still exists (untouched).
        file_f = _file_row(file_service, FILE_ID_F)
        assert file_f is not None
        assert file_f.hash == HASH_V2
        assert _file_row(file_service, FILE_ID_G) is not None

    def test_s7_keep_set_chunk_survives_stale_pruned_other_files_untouched(
        self, file_service: FileService, hash_index: HashIndexService
    ) -> None:
        mnemosyne = _mock_mnemosyne()
        remember = _remember_use_case(mnemosyne, hash_index, file_service)

        # v1: chunks m1 + m2 (edge F→G on chunk 1).
        _, mid1 = _remember_chunk(remember, "m1", "v1 chunk one", _contract(chunk_index=0, total_chunks=2))
        _, mid2 = _remember_chunk(
            remember,
            "m2",
            "v1 chunk two",
            _contract(chunk_index=1, total_chunks=2, edges=[]),
        )

        # Independent file H — must be untouched by F's rebuild.
        path_h = "/vault/notes/h.md"
        hash_h = "c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90abcd"
        file_id_h = derive_file_id(BANK, path_h)
        h_meta = json.loads(json.dumps(CONTRACT_TEMPLATE))
        h_meta.update(
            {
                "file_path": path_h,
                "file_hash": hash_h,
                "chunk_index": 0,
                "total_chunks": 1,
                "edges": [],
            }
        )
        _, mid_h1 = _remember_chunk(remember, "m_h_1", "h chunk one", h_meta)
        assert len(_chunk_rows(file_service, file_id_h)) == 1

        # v2: single new chunk (mock save echoes the generated uuid). Keep-set
        # = {current memory id} (the CURRENT call's memory id).
        v2_meta = _contract(chunk_index=0, total_chunks=1, file_hash=HASH_V2, edges=[])
        response = remember.execute(
            {
                "memory_bank": BANK,
                "content": "v2 chunk three",
                "importance": 0.5,
                "source": "integration-test",
                "scope": "working",
                "metadata": v2_meta,
            }
        )
        assert response.is_ok
        mid3 = response.value["memory_id"]  # type: ignore[index]

        # Stale m1/m2 pruned; exactly one chunk row (the v2 chunk) remains.
        chunks = _chunk_rows(file_service, FILE_ID_F)
        assert len(chunks) == 1
        assert "m1" not in [c.memory_id for c in chunks]
        assert "m2" not in [c.memory_id for c in chunks]
        assert chunks[0].memory_id == mid3

        # S7 variant: a memory id IN the keep-set is not pruned even when its
        # own materialization call triggers the rebuild — proven by the fact
        # that the v2 chunk (whose remember triggered the hash-change rebuild)
        # is present. Relations recreated from v2 edges only (v2 had none).
        assert _relation_rows(file_service, FILE_ID_F) == []

        # Other files untouched: H still has its chunk row and file row.
        h_chunks = _chunk_rows(file_service, file_id_h)
        assert [c.memory_id for c in h_chunks] == [mid_h1]
        file_h = _file_row(file_service, file_id_h)
        assert file_h is not None
        assert file_h.hash == hash_h

    def test_s7_chunk_in_keep_set_survives_when_remembered_again(
        self, file_service: FileService, hash_index: HashIndexService
    ) -> None:
        """Explicit S7: remember the SAME memory id again under a changed hash.

        The rebuild keep-set is {current memory_id}; that chunk row survives
        while stale sibling chunks are pruned."""
        mnemosyne = _mock_mnemosyne()
        remember = _remember_use_case(mnemosyne, hash_index, file_service)

        # v1: m1 + m2 (m1 will be re-remembered under v2 with the same content).
        _, mid1 = _remember_chunk(remember, "m1", "v1 chunk one", _contract(chunk_index=0, total_chunks=2))
        _, mid2 = _remember_chunk(
            remember,
            "m2",
            "v1 chunk two",
            _contract(chunk_index=1, total_chunks=2, edges=[]),
        )

        # v2: re-remember the same content (same memory id semantics) with the
        # new hash. Keep-set = {current call's memory id}.
        v2_meta = _contract(chunk_index=0, total_chunks=1, file_hash=HASH_V2, edges=[])
        response = remember.execute(
            {
                "memory_bank": BANK,
                "content": "v1 chunk one (re-ingested)",
                "importance": 0.5,
                "source": "integration-test",
                "scope": "working",
                "metadata": v2_meta,
            }
        )
        assert response.is_ok
        mid_reingested = response.value["memory_id"]  # type: ignore[index]

        # The re-ingested chunk (in keep-set) survives; stale m2 pruned.
        chunks = _chunk_rows(file_service, FILE_ID_F)
        assert sorted(c.memory_id for c in chunks) == [mid_reingested]
        assert mid2 not in [c.memory_id for c in chunks]


# ===================================================================
# Round-trip 3 — dangling stub → upgrade
# ===================================================================


class TestDanglingStubUpgrade:
    """Remember a chunk whose edge references never-ingested path X ⇒ PENDING
    stub + relation row; then remember X's own chunk (full contract) ⇒ the SAME
    file_id row upgraded in place to INDEXED with real fields."""

    def test_stub_upgraded_in_place_with_same_file_id(
        self, file_service: FileService, hash_index: HashIndexService
    ) -> None:
        mnemosyne = _mock_mnemosyne()
        remember = _remember_use_case(mnemosyne, hash_index, file_service)

        # Chunk of F with an edge to never-ingested X.
        stub_edge_meta = json.loads(json.dumps(CONTRACT_TEMPLATE))
        stub_edge_meta["edges"] = [
            {"target_path": PATH_X, "relation_type": "cross_reference", "strength": 1.0}
        ]
        _, mid_f1 = _remember_chunk(remember, "m_f_1", "f chunk referencing X", stub_edge_meta)

        # PENDING stub for X exists + relation row present.
        stub = _file_row(file_service, FILE_ID_X)
        assert stub is not None, "expected PENDING stub File row for X"
        assert stub.status == FileStatus.PENDING
        stub_id = stub.id
        assert stub_id == FILE_ID_X

        relations = _relation_rows(file_service, FILE_ID_F)
        assert len(relations) == 1
        assert relations[0].target_file_id == FILE_ID_X
        assert relations[0].relation_type.value == "cross_reference"

        # Now remember X's own chunk (full contract).
        hash_x = "d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90efabcd"
        x_meta = json.loads(json.dumps(CONTRACT_TEMPLATE))
        x_meta.update(
            {
                "file_path": PATH_X,
                "file_hash": hash_x,
                "chunk_index": 0,
                "total_chunks": 1,
                "summary": "X-level summary.",
                "edges": [],
            }
        )
        _, mid_x1 = _remember_chunk(remember, "m_x_1", "x chunk one", x_meta)

        # SAME file_id row upgraded in place — deterministic id equality.
        upgraded = _file_row(file_service, FILE_ID_X)
        assert upgraded is not None
        assert upgraded.id == stub_id, "stub and upgraded rows must share the same file_id"
        assert upgraded.status == FileStatus.INDEXED
        # Real fields populated by the full contract.
        assert upgraded.hash == hash_x
        assert upgraded.summary == "X-level summary."
        assert upgraded.total_chunks == 1

        # Exactly one row for X (upgraded in place, not duplicated).
        all_files = file_service.file_repository.list_files()
        assert all_files.is_ok
        x_rows = [f for f in all_files.value if f.id == FILE_ID_X]  # type: ignore[union-attr]
        assert len(x_rows) == 1

        # X now has its own chunk row; F's relation to X survives (rebuild only
        # fires on hash change of the file being materialized — F untouched here).
        x_chunks = _chunk_rows(file_service, FILE_ID_X)
        assert [c.memory_id for c in x_chunks] == [mid_x1]
        f_relations = _relation_rows(file_service, FILE_ID_F)
        assert len(f_relations) == 1
        assert f_relations[0].target_file_id == FILE_ID_X


# ===================================================================
# Round-trip 4 — forget symmetry
# ===================================================================


class TestForgetSymmetry:
    """Remember N chunks of F (N>=2, with a relation) → forget all N memory
    ids ⇒ existing forget semantics: File marked DELETED (not removed),
    0 file_chunk rows for F, 0 file_relation rows referencing F."""

    def test_forgetting_all_chunks_leaves_zero_rows(
        self, file_service: FileService, hash_index: HashIndexService
    ) -> None:
        mnemosyne = _mock_mnemosyne()
        remember = _remember_use_case(mnemosyne, hash_index, file_service)

        # N=3 chunks of F; chunk 1 carries the F→G edge.
        actual_ids: list[str] = []
        for i in range(3):
            meta = _contract(chunk_index=i, total_chunks=3)
            if i > 0:
                meta["edges"] = []
            _, mid = _remember_chunk(remember, f"m_f_{i + 1}", f"content of chunk {i + 1}", meta)
            actual_ids.append(mid)

        assert len(_chunk_rows(file_service, FILE_ID_F)) == 3
        assert len(_relation_rows(file_service, FILE_ID_F)) == 1

        # Forget all N memory ids (mocked mnemosyne reports deleted=True).
        forget = _forget_use_case(mnemosyne, hash_index, file_service)
        for mid in actual_ids:
            result = forget.execute({"memory_id": mid, "memory_bank": BANK})
            assert result.is_ok, f"forget {mid} failed: {result.errors}"
            assert result.value["status"] == "deleted"  # type: ignore[index]

        # Existing forget semantics: file row remains but is marked DELETED.
        file_f = _file_row(file_service, FILE_ID_F)
        assert file_f is not None
        assert file_f.status == FileStatus.DELETED

        # Exact post-forget chunk count: 0 chunk rows for F.
        assert _chunk_rows(file_service, FILE_ID_F) == []

        # BUG (production, NOT fixed in this test-only task): the forget path
        # (ForgetMemoryUseCase._cleanup_chunks_and_files → FileService.delete_file
        # → File.mark_deleted + save_file) marks the file DELETED but NEVER removes
        # its relation rows. delete_relations_by_file_id is only called from
        # rebuild_projection, not from the forget path. The F→G relation row
        # therefore survives after all chunks are forgotten — dangling reference
        # to a DELETED file (enrichment degrades via get_related_file_by_id, but
        # searchFiles/relation queries still surface it).
        # EXPECTED per spec §6.4 round-trip 4: _relation_rows(F) == [] and
        # _relation_rows(G) == []. Actual: 1 stale relation row remains.
        assert _relation_rows(file_service, FILE_ID_F) == [], (
            "BUG: forget path does not delete the file's relation rows — "
            f"stale rows: {_relation_rows(file_service, FILE_ID_F)}"
        )
        # G's relation side is symmetric — the F→G row is gone from G's view too.
        assert _relation_rows(file_service, FILE_ID_G) == []

    def test_partial_forget_keeps_file_indexed(
        self, file_service: FileService, hash_index: HashIndexService
    ) -> None:
        """Contrast case: forgetting only some chunks keeps the file INDEXED
        with the surviving chunk row (delete fires only at 0 remaining)."""
        mnemosyne = _mock_mnemosyne()
        remember = _remember_use_case(mnemosyne, hash_index, file_service)

        _, mid1 = _remember_chunk(remember, "m_f_1", "content one", _contract(chunk_index=0, total_chunks=2))
        _, mid2 = _remember_chunk(
            remember, "m_f_2", "content two", _contract(chunk_index=1, total_chunks=2, edges=[])
        )

        forget = _forget_use_case(mnemosyne, hash_index, file_service)
        result = forget.execute({"memory_id": mid1, "memory_bank": BANK})
        assert result.is_ok
        assert result.value["status"] == "deleted"  # type: ignore[index]

        chunks = _chunk_rows(file_service, FILE_ID_F)
        assert [c.memory_id for c in chunks] == [mid2]

        file_f = _file_row(file_service, FILE_ID_F)
        assert file_f is not None
        assert file_f.status == FileStatus.INDEXED

        # Partial forget must NOT delete the file's relation rows — cleanup of
        # relations fires only when the file reaches 0 chunks and is DELETED.
        relations = _relation_rows(file_service, FILE_ID_F)
        assert len(relations) == 1
        assert relations[0].source_file_id == FILE_ID_F
        assert relations[0].target_file_id == FILE_ID_G

    def test_forgetting_all_chunks_leaves_other_files_relations_untouched(
        self, file_service: FileService, hash_index: HashIndexService
    ) -> None:
        """Regression: forgetting all of F's chunks deletes only rows that
        reference F — relations between other (non-deleted) files survive."""
        mnemosyne = _mock_mnemosyne()
        remember = _remember_use_case(mnemosyne, hash_index, file_service)

        # F: 2 chunks; chunk 1 carries the F→G edge.
        actual_ids: list[str] = []
        for i in range(2):
            meta = _contract(chunk_index=i, total_chunks=2)
            if i > 0:
                meta["edges"] = []
            _, mid = _remember_chunk(remember, f"m_f_{i + 1}", f"content of chunk {i + 1}", meta)
            actual_ids.append(mid)

        # Independent pair H→K (neither references F).
        path_h = "/vault/notes/h.md"
        path_k = "/vault/notes/k.md"
        file_id_h = derive_file_id(BANK, path_h)
        file_id_k = derive_file_id(BANK, path_k)
        hash_h = "c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90abcd"
        h_meta = json.loads(json.dumps(CONTRACT_TEMPLATE))
        h_meta.update(
            {
                "file_path": path_h,
                "file_hash": hash_h,
                "chunk_index": 0,
                "total_chunks": 1,
                "edges": [
                    {"target_path": path_k, "relation_type": "cross_reference", "strength": 1.0}
                ],
            }
        )
        _, mid_h1 = _remember_chunk(remember, "m_h_1", "h chunk one", h_meta)

        assert len(_chunk_rows(file_service, FILE_ID_F)) == 2
        assert len(_relation_rows(file_service, file_id_h)) == 1

        # Forget all of F's memory ids.
        forget = _forget_use_case(mnemosyne, hash_index, file_service)
        for mid in actual_ids:
            result = forget.execute({"memory_id": mid, "memory_bank": BANK})
            assert result.is_ok, f"forget {mid} failed: {result.errors}"

        # F fully cleaned up.
        assert _chunk_rows(file_service, FILE_ID_F) == []
        assert _relation_rows(file_service, FILE_ID_F) == []
        assert _relation_rows(file_service, FILE_ID_G) == []

        # H→K relation (between two non-deleted files) is untouched: the row
        # survives in both H's and K's views; both file rows still exist.
        h_relations = _relation_rows(file_service, file_id_h)
        assert len(h_relations) == 1
        assert h_relations[0].source_file_id == file_id_h
        assert h_relations[0].target_file_id == file_id_k

        k_relations = _relation_rows(file_service, file_id_k)
        assert [r.id for r in k_relations] == [h_relations[0].id]

        file_h = _file_row(file_service, file_id_h)
        assert file_h is not None
        assert file_h.status != FileStatus.DELETED
        assert [c.memory_id for c in _chunk_rows(file_service, file_id_h)] == [mid_h1]


# ===================================================================
# Round-trip 5 — remember → fetch dual-hash surface (D15)
# ===================================================================


class TestFetchRoundTripHashes:
    """remember (with chunk_hash in metadata) → fetchFile: chunk entries carry
    chunk_hash from the REAL file_chunks rows; the include_metadata file block
    carries file_hash from the real File row (end-to-end, real SQLite)."""

    def test_fetch_result_carries_hashes_end_to_end(
        self, file_service: FileService, hash_index: HashIndexService
    ) -> None:
        mnemosyne = _mock_mnemosyne()
        remember = _remember_use_case(mnemosyne, hash_index, file_service)

        _, mid1 = _remember_chunk(
            remember, "m_f_1", "content of chunk one", _contract(chunk_index=0, chunk_hash=CHASH_F1)
        )
        _, mid2 = _remember_chunk(
            remember,
            "m_f_2",
            "content of chunk two",
            _contract(chunk_index=1, edges=[], chunk_hash=CHASH_F2),
        )

        # Mnemosyne content lookup by memory id (mocked client only).
        contents = {mid1: "content of chunk one", mid2: "content of chunk two"}
        mnemosyne.get.side_effect = lambda mid: {"content": contents[mid]} if mid in contents else None

        fetch = FetchFileUseCase(
            mnemosyne_client=mnemosyne,
            chunk_repository=file_service.chunk_repository,
            file_repository=file_service.file_repository,
            logger=LoggerMock(),
        )
        result = fetch.execute(
            {"file_id": FILE_ID_F, "memory_bank": BANK, "include_metadata": True}
        )
        assert result.is_ok, f"fetch failed: {result.errors}"
        val = result.value

        # File block — file_hash from the real File row (HASH_V1 from the contract).
        assert val["file"]["file_hash"] == HASH_V1

        # Chunk entries — chunk_hash from the real file_chunks rows, per chunk.
        by_index = {c["chunk_index"]: c for c in val["chunks"]}
        assert by_index[0]["memory_id"] == mid1
        assert by_index[0]["chunk_hash"] == CHASH_F1
        assert by_index[1]["memory_id"] == mid2
        assert by_index[1]["chunk_hash"] == CHASH_F2
