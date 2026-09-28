"""Integration test: file_chunks index integrity during re-ingest.

Verifies that when a multi-chunk file is re-ingested, the exclude set
passed to delete_chunks_by_file_id contains ALL live memory IDs for the
file, not just the final chunk's. This ensures file-backed memories remain
classified as node memories (not occasional) after re-ingestion.

Bug scenario:
1. File with 3 chunks is ingested (memories M1, M2, M3, all file-backed)
2. File is updated and re-ingested (new memories M4, M5, M6)
3. On final chunk (M6), rebuild_projection is called with exclude set {M6}
4. delete_chunks_by_file_id deletes rows for M1, M2, M3, M4, M5
5. Only M6 remains file-backed — M4 and M5 become "occasional" (BUG)

Expected: exclude set should be {M4, M5, M6} (all live memories for the file)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Generator

import pytest

from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
from src.application.use_cases.expand_file_relations_use_case import ExpandFileRelationsUseCase
from src.application.use_cases.get_persona_status_use_case import GetPersonaStatusUseCase
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

BANK = "agent-persona_reingest_chunk_integrity_test"


def _file_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def _chunk_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


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
def get_status_use_case(
    mnemosyne: MnemosyneClient,
    chunk_repository: FileChunkRepository,
) -> GetPersonaStatusUseCase:
    return GetPersonaStatusUseCase(
        mnemosyne_client=mnemosyne,
        file_chunk_repository=chunk_repository,
        logger=LoggerMock(),
        materialization_threshold=10,
    )


def _ingest_chunk(
    use_case: RememberMemoryUseCase,
    file_path: Path,
    chunk_index: int,
    total_chunks: int,
    content: str,
    file_hash: str,
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
                "persona.node_id": f"node-{chunk_index}",
                "persona.title": f"Node {chunk_index}",
                "persona.entry": "false",
                "persona.conditions": json.dumps(["condition"]),
                "persona.veto": json.dumps([]),
            },
            "edges": [],
        },
    })


class TestReingestChunkIndexIntegrity:
    """All file-backed memories retain their file_chunks row after re-ingest."""

    def test_chunk_rows_preserved_after_reingest(
        self,
        remember_use_case: RememberMemoryUseCase,
        chunk_repository: FileChunkRepository,
        get_status_use_case: GetPersonaStatusUseCase,
        file_service: FileService,
        tmp_path: Path,
    ):
        """Multi-chunk re-ingest preserves all file_chunks rows for new memories."""
        file_path = tmp_path / "multi-chunk.md"
        file_path.write_text("Original content")

        # First ingestion: 3 chunks
        original_content = "Original multi-chunk content"
        original_hash = _file_hash(original_content)

        memory_ids_first = []
        for i in range(3):
            chunk_content = f"Chunk {i} original"
            result = _ingest_chunk(
                remember_use_case,
                file_path,
                chunk_index=i,
                total_chunks=3,
                content=chunk_content,
                file_hash=original_hash,
            )
            assert result.is_ok, f"Chunk {i} ingest failed: {result.errors}"
            memory_ids_first.append(result.value["memory_id"])

        # Verify all 3 chunks are file-backed after first ingest
        status_before = get_status_use_case.execute({"memory_bank": BANK})
        assert status_before.is_ok, f"Status before failed: {status_before.errors}"
        # All 3 memories should be node memories (file-backed)
        assert status_before.value["node_memories"] >= 3, (
            f"Expected at least 3 node memories after first ingest, got "
            f"{status_before.value['node_memories']}"
        )

        # Second ingestion (re-ingest): same file, new content (new hash)
        new_content = "Updated multi-chunk content"
        new_hash = _file_hash(new_content)

        memory_ids_second = []
        for i in range(3):
            chunk_content = f"Chunk {i} updated"
            result = _ingest_chunk(
                remember_use_case,
                file_path,
                chunk_index=i,
                total_chunks=3,
                content=chunk_content,
                file_hash=new_hash,
            )
            assert result.is_ok, f"Re-ingest chunk {i} failed: {result.errors}"
            memory_ids_second.append(result.value["memory_id"])

        # After re-ingest, all new memories should still be file-backed
        status_after = get_status_use_case.execute({"memory_bank": BANK})
        assert status_after.is_ok, f"Status after failed: {status_after.errors}"

        # Debug: print status values
        print(f"Status before: node={status_before.value['node_memories']}, total={status_before.value['total']}")
        print(f"Status after: node={status_after.value['node_memories']}, total={status_after.value['total']}")

        # The 3 new memories should all be node memories (file-backed)
        # If only the final chunk's file_chunks row survived, we'd see only 1
        assert status_after.value["node_memories"] >= 3, (
            f"Expected at least 3 node memories after re-ingest, got "
            f"{status_after.value['node_memories']}. "
            f"Only the final chunk's file_chunks row may have survived."
        )

        # Verify file_chunks rows exist for each of the new memory IDs
        for i, mid in enumerate(memory_ids_second):
            chunks = chunk_repository.get_chunks_by_memory_id(mid)
            assert chunks.is_ok, f"Chunk lookup for {mid} failed: {chunks.errors}"
            print(f"Memory {mid[:8]}... (chunk {i}): {len(chunks.value)} chunk rows")
            assert len(chunks.value) >= 1, (
                f"Memory {mid} (re-ingest chunk {i}) lost its file_chunks row "
                f"during re-ingestion. Only the final chunk's row survived."
            )

    def test_node_counts_stable_after_reingest(
        self,
        remember_use_case: RememberMemoryUseCase,
        get_status_use_case: GetPersonaStatusUseCase,
        chunk_repository: FileChunkRepository,
        tmp_path: Path,
    ):
        """Persona status node count remains stable across re-ingest operations."""
        file_path = tmp_path / "stable-node-counts.md"
        file_path.write_text("Original content")

        content_v1 = "Version 1 content"
        hash_v1 = _file_hash(content_v1)

        result1 = _ingest_chunk(
            remember_use_case, file_path, 0, 1, content_v1, hash_v1
        )
        assert result1.is_ok

        status_v1 = get_status_use_case.execute({"memory_bank": BANK})
        assert status_v1.is_ok
        node_count_v1 = status_v1.value["node_memories"]
        assert node_count_v1 >= 1

        # Re-ingest with new content (triggers rebuild_projection on final chunk)
        content_v2 = "Version 2 content"
        hash_v2 = _file_hash(content_v2)

        result2 = _ingest_chunk(
            remember_use_case, file_path, 0, 1, content_v2, hash_v2
        )
        assert result2.is_ok

        status_v2 = get_status_use_case.execute({"memory_bank": BANK})
        assert status_v2.is_ok
        node_count_v2 = status_v2.value["node_memories"]

        # Node count should not decrease after re-ingest
        assert node_count_v2 >= node_count_v1, (
            f"Node count decreased after re-ingest: {node_count_v1} -> {node_count_v2}"
        )

        # Verify the new memory has a file_chunks row
        chunks = chunk_repository.get_chunks_by_memory_id(result2.value["memory_id"])
        assert chunks.is_ok
        assert len(chunks.value) >= 1, (
            "New memory lost its file_chunks row during re-ingest"
        )

    def test_rebuild_projection_keeps_all_live_chunks(
        self,
        remember_use_case: RememberMemoryUseCase,
        chunk_repository: FileChunkRepository,
        get_status_use_case: GetPersonaStatusUseCase,
        tmp_path: Path,
    ):
        """rebuild_projection during re-ingest keeps all live chunk rows.

        Regression test for: when rebuild_projection is called during re-ingest
        of a multi-chunk file, it should keep ALL current chunks, not just the
        final chunk being processed.
        """
        file_path = tmp_path / "rebuild-keeps-live-chunks.md"
        file_path.write_text("Original content")

        # First ingestion: 3 chunks (all use same file hash)
        content_v1 = "Original content v1"
        hash_v1 = _file_hash(content_v1)

        first_chunk_ids = []
        for i in range(3):
            chunk_content = f"Chunk {i} v1"
            result = _ingest_chunk(
                remember_use_case, file_path, i, 3, chunk_content, hash_v1
            )
            assert result.is_ok, f"First ingest chunk {i} failed"
            first_chunk_ids.append(result.value["memory_id"])

        # Second ingestion (re-ingest): same file, new content (new hash)
        # This will trigger rebuild_projection on the final chunk
        content_v2 = "Updated content v2"
        hash_v2 = _file_hash(content_v2)

        second_chunk_ids = []
        for i in range(3):
            chunk_content = f"Chunk {i} v2"
            result = _ingest_chunk(
                remember_use_case, file_path, i, 3, chunk_content, hash_v2
            )
            assert result.is_ok, f"Re-ingest chunk {i} failed"
            second_chunk_ids.append(result.value["memory_id"])

        # After re-ingest, all NEW memory IDs should have file_chunks rows
        # If rebuild_projection only kept the final chunk, chunks 0 and 1
        # would have lost their rows.
        for i, mid in enumerate(second_chunk_ids):
            chunks = chunk_repository.get_chunks_by_memory_id(mid)
            assert chunks.is_ok
            assert len(chunks.value) >= 1, (
                f"Memory {mid[:8]}... (re-ingest chunk {i}) lost its file_chunks row. "
                f"rebuild_projection may have only kept the final chunk's row."
            )

        # OLD chunk rows should have been pruned by rebuild_projection on chunk 0.
        # They are now "occasional" memories (not file-backed). This is correct —
        # only the newest version of each chunk should be file-backed.
        for mid in first_chunk_ids:
            chunks = chunk_repository.get_chunks_by_memory_id(mid)
            assert chunks.is_ok
            assert len(chunks.value) == 0, (
                f"Old memory {mid[:8]}... should have been pruned by rebuild_projection."
            )
