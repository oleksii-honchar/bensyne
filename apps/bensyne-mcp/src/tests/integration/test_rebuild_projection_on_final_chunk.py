"""Integration test: rebuild_projection deferred to final chunk.

Verifies that when a file with multiple chunks is re-ingested, rebuild_projection
is only called on the final chunk, preserving edges across chunks.

Bug: rebuild was triggered on every chunk after the first, deleting all file
relations before the final chunk was processed.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
from src.application.use_cases.expand_file_relations_use_case import ExpandFileRelationsUseCase
from src.infrastructure.mcp.hash_index_service import HashIndexService
from src.infrastructure.mnemosyne.mnemosyne_client import MnemosyneClient
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_relation_repository import FileRelationRepository
from src.infrastructure.storage.sqlite.file_repository import FileRepository
from src.application.services.file_service import FileService
from src.utils.structured_logging import LoggerMock

BANK = "agent-persona_rebuild_final_chunk_test"


@pytest.fixture
def mnemosyne(tmp_path: Path) -> Generator[MnemosyneClient, None, None]:
    client = MnemosyneClient(memory_bank=BANK, data_dir=str(tmp_path / "data"))
    yield client


@pytest.fixture
def manager(tmp_path: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    mgr = FileMetadataConnectionManager(bank_dir=tmp_path / "file_metadata" / BANK)
    yield mgr
    mgr.close()


@pytest.fixture
def chunk_repository(manager: FileMetadataConnectionManager) -> FileChunkRepository:
    return FileChunkRepository(manager)


@pytest.fixture
def file_repository(manager: FileMetadataConnectionManager) -> FileRepository:
    return FileRepository(manager)


@pytest.fixture
def relation_repository(manager: FileMetadataConnectionManager) -> FileRelationRepository:
    return FileRelationRepository(manager)


@pytest.fixture
def hash_service(tmp_path: Path) -> HashIndexService:
    return HashIndexService(memory_bank=BANK, db_path=tmp_path / "hash_index.db")


@pytest.fixture
def file_service(
    file_repository: FileRepository,
    chunk_repository: FileChunkRepository,
    relation_repository: FileRelationRepository,
) -> FileService:
    return FileService(
        file_repository=file_repository,
        chunk_repository=chunk_repository,
        relation_repository=relation_repository,
        logger=LoggerMock(),
    )


@pytest.fixture
def remember_use_case(
    mnemosyne: MnemosyneClient,
    hash_service: HashIndexService,
    file_service: FileService,
) -> RememberMemoryUseCase:
    return RememberMemoryUseCase(
        memory_repository=mnemosyne,
        hash_index_service=hash_service,
        file_service=file_service,
        logger=LoggerMock(),
    )


@pytest.fixture
def expand_use_case(
    mnemosyne: MnemosyneClient,
    file_service: FileService,
    relation_repository: FileRelationRepository,
) -> ExpandFileRelationsUseCase:
    return ExpandFileRelationsUseCase(
        mnemosyne_client=mnemosyne,
        file_service=file_service,
        relation_repository=relation_repository,
        logger=LoggerMock(),
    )


def _file_hash(content: str) -> str:
    """Compute the file hash used by the ingest pipeline."""
    return hashlib.sha256(content.encode()).hexdigest()


def _chunk_hash(content: str) -> str:
    """Compute a chunk hash."""
    return hashlib.sha256(content.encode()).hexdigest()


def _ingest_chunk(
    use_case: RememberMemoryUseCase,
    file_path: Path,
    chunk_index: int,
    total_chunks: int,
    content: str,
    file_hash: str,
    node_id: str,
    target_path: Path | None = None,
) -> dict:
    """Ingest a single chunk of a file."""
    return use_case.execute({
        "content": content,
        "source": "test",
        "importance": 0.9,
        "metadata": {
            "chunk_hash": _chunk_hash(content),
            "filePath": str(file_path),
            "sourceType": "agent-persona",
            "file_hash": file_hash,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
            "extra": {
                "persona.node_id": node_id,
                "persona.title": f"Node {node_id}",
                "persona.entry": "false",
                "persona.conditions": json.dumps(["test condition"]),
                "persona.veto": json.dumps([]),
            },
            "edges": [
                {
                    "target_path": str(target_path),
                    "relation_type": "decision_next",
                    "description": json.dumps({"when": "test condition"}),
                }
            ] if target_path else [],
        },
    })


def _ingest_full_file(
    use_case: RememberMemoryUseCase,
    file_path: Path,
    node_id: str,
    target_path: Path | None = None,
) -> dict:
    """Ingest a complete single-chunk file."""
    content = f"Content for {node_id}"
    result = use_case.execute({
        "content": content,
        "source": "test",
        "importance": 0.9,
        "metadata": {
            "chunk_hash": _chunk_hash(content),
            "filePath": str(file_path),
            "sourceType": "agent-persona",
            "file_hash": _file_hash(content),
            "extra": {
                "persona.node_id": node_id,
                "persona.title": f"Node {node_id}",
                "persona.entry": "false",
                "persona.conditions": json.dumps(["test condition"]),
                "persona.veto": json.dumps([]),
            },
            "edges": [
                {
                    "target_path": str(target_path),
                    "relation_type": "decision_next",
                    "description": json.dumps({"when": "test condition"}),
                }
            ] if target_path else [],
        },
    })
    return result


class TestRebuildProjectionOnFinalChunk:
    """Edges preserved during multi-chunk re-ingestion when rebuild deferred to final chunk."""

    def test_edges_preserved_after_multi_chunk_reingestion(
        self,
        remember_use_case: RememberMemoryUseCase,
        expand_use_case: ExpandFileRelationsUseCase,
        file_service: FileService,
        tmp_path: Path,
    ):
        """Re-ingesting a multi-chunk file preserves edges after the final chunk."""
        # Create files on disk (required by the ingest pipeline)
        parent_dir = tmp_path / "tree"
        parent_dir.mkdir(parents=True)
        hub_file = parent_dir / "100-hub.md"
        hub_file.write_text("---\ntitle: Hub\n---\nHub content")
        child_file = parent_dir / "110-child.md"
        child_file.write_text("---\ntitle: Child\n---\nChild content")

        # First ingestion: ingest all chunks (simulate re-ingestion of changed file)
        file_content = "Original hub content"
        file_hash = _file_hash(file_content)

        # Ingest chunk 0/1 (final chunk for single-chunk file)
        result = _ingest_chunk(
            remember_use_case,
            hub_file,
            chunk_index=0,
            total_chunks=1,
            content=file_content,
            file_hash=file_hash,
            node_id="100-hub",
            target_path=child_file,
        )
        assert result.is_ok
        file_id = result.value["file_materialization"]["file_id"]

        # Verify edge was created
        expand = expand_use_case.execute({"file_id": file_id})
        assert expand.is_ok
        assert len(expand.value["related_files"]) == 1

        # Now re-ingest the file with updated content (new hash)
        new_content = "Updated hub content"
        new_file_hash = _file_hash(new_content)

        # Single-chunk file: chunk_index=0, total_chunks=1, so chunk_index == total_chunks-1
        result2 = _ingest_chunk(
            remember_use_case,
            hub_file,
            chunk_index=0,
            total_chunks=1,
            content=new_content,
            file_hash=new_file_hash,
            node_id="100-hub",
            target_path=child_file,
        )
        assert result2.is_ok

        # Edge should be preserved after re-ingestion
        expand2 = expand_use_case.execute({"file_id": file_id})
        assert expand2.is_ok
        assert len(expand2.value["related_files"]) == 1

    def test_edges_preserved_for_two_chunk_file(
        self,
        remember_use_case: RememberMemoryUseCase,
        expand_use_case: ExpandFileRelationsUseCase,
        file_service: FileService,
        tmp_path: Path,
    ):
        """Two-chunk file: rebuild only on chunk 1 (final), not chunk 0."""
        parent_dir = tmp_path / "tree"
        parent_dir.mkdir(parents=True)
        hub_file = parent_dir / "100-hub.md"
        hub_file.write_text("---\ntitle: Hub\n---\nHub")
        child_file = parent_dir / "110-child.md"
        child_file.write_text("---\ntitle: Child\n---\nChild")

        # First ingestion: 2 chunks
        file_hash = _file_hash("original two-chunk content")

        # Chunk 0 — not final, no rebuild
        r0 = _ingest_chunk(
            remember_use_case, hub_file, chunk_index=0, total_chunks=2,
            content="first chunk", file_hash=file_hash, node_id="100-hub-0",
        )
        assert r0.is_ok

        # Chunk 1 — final, rebuild happens, edge created
        r1 = _ingest_chunk(
            remember_use_case, hub_file, chunk_index=1, total_chunks=2,
            content="second chunk with edge", file_hash=file_hash, node_id="100-hub-1",
            target_path=child_file,
        )
        assert r1.is_ok
        file_id = r1.value["file_materialization"]["file_id"]

        # Verify edge was created
        expand = expand_use_case.execute({"file_id": file_id})
        assert expand.is_ok
        assert len(expand.value["related_files"]) == 1

        # Re-ingest with new content (different hash)
        new_file_hash = _file_hash("updated two-chunk content")

        # Chunk 0 — not final, rebuild should NOT happen (edge still there from before)
        r0b = _ingest_chunk(
            remember_use_case, hub_file, chunk_index=0, total_chunks=2,
            content="first chunk updated", file_hash=new_file_hash, node_id="100-hub-0",
        )
        assert r0b.is_ok

        # At this point, with the bug, rebuild would have happened and deleted the edge.
        # After the fix, the edge should still be there.
        expand_b = expand_use_case.execute({"file_id": file_id})
        assert expand_b.is_ok
        assert len(expand_b.value["related_files"]) == 1

        # Chunk 1 — final, rebuild happens, edge re-created
        r1b = _ingest_chunk(
            remember_use_case, hub_file, chunk_index=1, total_chunks=2,
            content="second chunk updated", file_hash=new_file_hash, node_id="100-hub-1",
            target_path=child_file,
        )
        assert r1b.is_ok

        # Edge should be preserved
        expand_final = expand_use_case.execute({"file_id": file_id})
        assert expand_final.is_ok
        assert len(expand_final.value["related_files"]) == 1

    def test_single_chunk_file_rebuild_triggered(
        self,
        remember_use_case: RememberMemoryUseCase,
        expand_use_case: ExpandFileRelationsUseCase,
        file_service: FileService,
        tmp_path: Path,
    ):
        """Single-chunk file: chunk_index=0 == total_chunks-1, rebuild triggered immediately."""
        parent_dir = tmp_path / "tree"
        parent_dir.mkdir(parents=True)
        hub_file = parent_dir / "100-hub.md"
        hub_file.write_text("---\ntitle: Hub\n---\nHub")
        child_file = parent_dir / "110-child.md"
        child_file.write_text("---\ntitle: Child\n---\nChild")

        # First ingestion
        result = _ingest_chunk(
            remember_use_case, hub_file, chunk_index=0, total_chunks=1,
            content="original", file_hash=_file_hash("original"), node_id="100-hub",
            target_path=child_file,
        )
        assert result.is_ok
        file_id = result.value["file_materialization"]["file_id"]

        # Verify edge
        expand = expand_use_case.execute({"file_id": file_id})
        assert expand.is_ok
        assert len(expand.value["related_files"]) == 1

        # Re-ingest with different content (new hash)
        result2 = _ingest_chunk(
            remember_use_case, hub_file, chunk_index=0, total_chunks=1,
            content="updated", file_hash=_file_hash("updated"), node_id="100-hub",
            target_path=child_file,
        )
        assert result2.is_ok

        # Edge should be preserved after rebuild
        expand2 = expand_use_case.execute({"file_id": file_id})
        assert expand2.is_ok
        assert len(expand2.value["related_files"]) == 1

    def test_file_shrinks_stale_chunks_pruned(
        self,
        remember_use_case: RememberMemoryUseCase,
        expand_use_case: ExpandFileRelationsUseCase,
        file_service: FileService,
        tmp_path: Path,
    ):
        """File with fewer chunks: stale chunks pruned, edges preserved."""
        parent_dir = tmp_path / "tree"
        parent_dir.mkdir(parents=True)
        hub_file = parent_dir / "100-hub.md"
        hub_file.write_text("---\ntitle: Hub\n---\nHub")
        child_file = parent_dir / "110-child.md"
        child_file.write_text("---\ntitle: Child\n---\nChild")

        # First: ingest 3 chunks
        file_hash = _file_hash("three chunks")
        for i in range(3):
            r = _ingest_chunk(
                remember_use_case, hub_file, chunk_index=i, total_chunks=3,
                content=f"chunk {i}", file_hash=file_hash, node_id=f"100-hub-{i}",
                target_path=child_file if i == 2 else None,
            )
            assert r.is_ok
        file_id = r.value["file_materialization"]["file_id"]

        # Verify edge
        expand = expand_use_case.execute({"file_id": file_id})
        assert expand.is_ok
        assert len(expand.value["related_files"]) == 1

        # Verify 3 chunks exist
        chunks_result = file_service.chunk_repository.get_chunks_by_file_id(file_id)
        assert chunks_result.is_ok
        assert len(chunks_result.value) == 3

        # Now re-ingest with 1 chunk (file shrinks)
        new_hash = _file_hash("one chunk")
        r_new = _ingest_chunk(
            remember_use_case, hub_file, chunk_index=0, total_chunks=1,
            content="only chunk", file_hash=new_hash, node_id="100-hub-0",
            target_path=child_file,
        )
        assert r_new.is_ok

        # Old chunks should be pruned, edge should still be there
        chunks_after_result = file_service.chunk_repository.get_chunks_by_file_id(file_id)
        assert chunks_after_result.is_ok
        assert len(chunks_after_result.value) == 1

        expand_after = expand_use_case.execute({"file_id": file_id})
        assert expand_after.is_ok
        assert len(expand_after.value["related_files"]) == 1
