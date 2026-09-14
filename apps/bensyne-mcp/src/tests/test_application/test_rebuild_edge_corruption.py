"""Validation test for decision-node edge corruption on re-ingestion.

Reproduces the root cause: when a file is re-ingested with multiple chunks,
rebuild_projection is called on every chunk (not just the final chunk),
which deletes edges created by earlier chunks. After all chunks are
ingested, the file has no edges — decision nodes appear as terminal.

Expected behavior after fix: rebuild_projection should only fire on the
final chunk (chunk_index == total_chunks - 1).
"""

import hashlib
import json
from pathlib import Path

import pytest

from src.application.services.file_service import FileService, derive_file_id
from src.domain.models.file_context_model import parse_file_context
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_relation_repository import FileRelationRepository
from src.infrastructure.storage.sqlite.file_repository import FileRepository
from src.utils.structured_logging import LoggerMock

FIXTURES_DIR = Path(__file__).resolve().parents[2] / "test_domain" / "fixtures"
BANK = "test_rebuild_edge"


@pytest.fixture
def manager(tmp_path: Path):
    mgr = FileMetadataConnectionManager(bank_dir=tmp_path / BANK)
    yield mgr
    mgr.close()


@pytest.fixture
def service(manager: FileMetadataConnectionManager):
    return FileService(
        file_repository=FileRepository(manager),
        chunk_repository=FileChunkRepository(manager),
        relation_repository=FileRelationRepository(manager),
        logger=LoggerMock(),
    )


def _build_chunk_context(
    file_path: str,
    chunk_index: int,
    total_chunks: int,
    file_hash: str,
    edges: list[dict] | None = None,
    memory_id: str | None = None,
) -> dict:
    """Build a unified chunk contract v1 payload for a specific chunk."""
    return {
        "contract_version": 1,
        "file_path": file_path,
        "chunk_index": chunk_index,
        "total_chunks": total_chunks,
        "file_hash": file_hash,
        "chunk_hash": hashlib.sha256(f"chunk_{chunk_index}_{file_hash}".encode()).hexdigest(),
        "source_type": "agent-sessions",
        "file_role": "docs",
        "language": "markdown",
        "section_header": f"## Section {chunk_index}",
        "start_line": chunk_index * 10 + 1,
        "end_line": (chunk_index + 1) * 10,
        "edges": edges or [],
        "tags": ["test"],
        "extra": {},
    }


def test_rebuild_on_every_chunk_corrupts_edges(service: FileService):
    """Reproduces the bug: rebuild on every chunk deletes edges before final chunk.

    Scenario:
    1. First ingestion: 3 chunks, chunk 0 has an edge to /target.md
    2. Re-ingestion: same file, different hash, 3 chunks
       - Chunk 0 arrives with edge → edge created
       - Chunk 1 arrives → rebuild fires → edge deleted
       - Chunk 2 arrives → rebuild fires → no edges (correct, but edge already lost)
    3. Result: file has no edges despite chunk 0 declaring one
    """
    file_path = "/test/repro-edge-corruption.md"
    original_hash = hashlib.sha256("original content".encode()).hexdigest()
    new_hash = hashlib.sha256("new content".encode()).hexdigest()

    # Step 1: Initial ingestion with 3 chunks, edge on chunk 0
    chunk0_edges = [
        {
            "target_path": "/test/target.md",
            "relation_type": "decision_next",
            "strength": 1,
            "description": "decision edge",
        }
    ]
    for i in range(3):
        edges = chunk0_edges if i == 0 else []
        ctx = parse_file_context(_build_chunk_context(file_path, i, 3, original_hash, edges))
        result = service.materialize_file_context(BANK, ctx, f"orig_chunk_{i}")
        assert result.is_ok, f"initial chunk {i} failed: {result.errors}"

    # Verify edge exists after initial ingestion
    file_id = derive_file_id(BANK, file_path)
    relations = service.get_relations_by_file_id(file_id)
    assert relations.is_ok
    outbound = [r for r in relations.value if r.source_file_id == file_id]
    assert len(outbound) == 1, f"expected 1 edge after initial ingestion, got {len(outbound)}"

    # Step 2: Re-ingest with new hash (simulates re-ingestion after content change)
    for i in range(3):
        edges = chunk0_edges if i == 0 else []
        ctx = parse_file_context(_build_chunk_context(file_path, i, 3, new_hash, edges))
        result = service.materialize_file_context(BANK, ctx, f"re_chunk_{i}")
        assert result.is_ok, f"re-ingest chunk {i} failed: {result.errors}"

    # Step 3: Check edges after re-ingestion — BUG: edges are lost
    relations = service.get_relations_by_file_id(file_id)
    assert relations.is_ok
    outbound = [r for r in relations.value if r.source_file_id == file_id]

    # BUG: rebuild fired on chunk 1 and 2, deleting the edge created by chunk 0
    # Expected (after fix): 1 edge
    # Actual (bug): 0 edges
    print(f"Edges after re-ingestion: {len(outbound)} (expected 1)")

    # This assertion will FAIL with the bug, PASS after the fix
    assert len(outbound) == 1, (
        "BUG REPRODUCED: Edges were lost during re-ingestion. "
        "rebuild_projection was called on non-final chunks, deleting edges. "
        "Fix: only call rebuild on the final chunk (chunk_index == total_chunks - 1)."
    )


def test_single_chunk_file_still_rebuilds(service: FileService):
    """Regression: single-chunk files must still trigger rebuild (unchanged behavior)."""
    file_path = "/test/single-chunk.md"
    original_hash = hashlib.sha256("original single".encode()).hexdigest()
    new_hash = hashlib.sha256("new single".encode()).hexdigest()

    edges = [
        {"target_path": "/test/target2.md", "relation_type": "backlink", "strength": 1}
    ]

    # Initial
    ctx = parse_file_context(_build_chunk_context(file_path, 0, 1, original_hash, edges))
    result = service.materialize_file_context(BANK, ctx, "single_orig")
    assert result.is_ok

    file_id = derive_file_id(BANK, file_path)
    relations = service.get_relations_by_file_id(file_id)
    outbound = [r for r in relations.value if r.source_file_id == file_id]
    assert len(outbound) == 1

    # Re-ingest with new hash — should rebuild (single chunk IS the final chunk)
    ctx = parse_file_context(_build_chunk_context(file_path, 0, 1, new_hash, []))
    result = service.materialize_file_context(BANK, ctx, "single_new")
    assert result.is_ok
    assert result.value["rebuilt"] is True  # rebuild must fire

    relations = service.get_relations_by_file_id(file_id)
    outbound = [r for r in relations.value if r.source_file_id == file_id]
    assert len(outbound) == 0  # edge was removed by rebuild (no new edges)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
