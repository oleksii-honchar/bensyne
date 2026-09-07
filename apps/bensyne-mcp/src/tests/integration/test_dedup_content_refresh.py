"""Integration test for ADR-11 content-sync fix.

Verifies that when a file is re-ingested with the same chunk hash and the
existing memory has empty/stale content, the dedup logic refreshes the
content from the new input.
"""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from typing import Generator

import pytest

from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
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

BANK = "agent-persona_dedup_content_refresh_test"


@pytest.fixture
def mnemosyne(tmp_path: Path) -> Generator[MnemosyneClient, None, None]:
    """Real mnemosyne broker for this bank."""
    client = MnemosyneClient(memory_bank=BANK, data_dir=str(tmp_path / "data"))
    yield client


@pytest.fixture
def manager(tmp_path: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    """Real file metadata DB for this bank."""
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
    return HashIndexService(
        memory_bank=BANK,
        db_path=tmp_path / "hash_index.db",
    )


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
def use_case(
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


def _file_chunk_params(content: str, chunk_hash: str, file_path: Path) -> dict:
    """Build rememberMemory params for a file chunk."""
    now = datetime.now().isoformat()
    return {
        "content": content,
        "source": "test",
        "importance": 0.9,
        "metadata": {
            "chunk_hash": chunk_hash,
            "filePath": str(file_path),
            "sourceType": "file",
            "persona.node_id": "test-01",
            "persona.title": "Test Node",
        },
    }


class TestDedupContentRefresh:
    """ADR-11 content-sync fix: empty memory content refreshed on re-ingestion."""

    def test_reingest_refreshes_empty_content(self, use_case: RememberMemoryUseCase, mnemosyne: MnemosyneClient, tmp_path: Path):
        """When memory content is empty, re-ingestion refreshes it."""
        test_file = tmp_path / "test_node.md"
        test_file.write_text("---\ntitle: Test Node\n---\nTest body content")
        chunk_hash = "abc123def456"

        # First ingestion
        result1 = use_case.execute(_file_chunk_params("Test body content", chunk_hash, test_file))
        assert result1.is_ok
        assert result1.value["status"] == "stored"
        memory_id = result1.value["memory_id"]

        # Verify content was stored
        mem = mnemosyne.get(memory_id)
        assert mem is not None
        assert mem.get("content") == "Test body content"

        # Simulate the bug: memory content becomes empty
        update_result = mnemosyne.update(memory_id, content="")
        assert update_result.is_ok

        # Verify content is now empty
        mem = mnemosyne.get(memory_id)
        assert mem is not None
        assert mem.get("content") == ""

        # Re-ingest same file (same hash) — ADR-11 fix should refresh content
        result2 = use_case.execute(_file_chunk_params("Test body content", chunk_hash, test_file))
        assert result2.is_ok
        assert result2.value["status"] == "deduplicated"
        assert result2.value["memory_id"] == memory_id

        # Content should be refreshed from new input
        mem = mnemosyne.get(memory_id)
        assert mem is not None
        assert mem.get("content") == "Test body content"

    def test_reingest_with_updated_content_refreshes(self, use_case: RememberMemoryUseCase, mnemosyne: MnemosyneClient, tmp_path: Path):
        """Re-ingesting with updated content refreshes the memory."""
        test_file = tmp_path / "test_node.md"
        test_file.write_text("---\ntitle: Test Node\n---\nOriginal content")
        chunk_hash = "xyz789"

        # First ingestion
        result1 = use_case.execute(_file_chunk_params("Original content", chunk_hash, test_file))
        assert result1.is_ok
        memory_id = result1.value["memory_id"]

        # Verify original content
        mem = mnemosyne.get(memory_id)
        assert mem.get("content") == "Original content"

        # File updated — re-ingest with same hash but new content
        test_file.write_text("---\ntitle: Test Node\n---\nUpdated content")
        result2 = use_case.execute(_file_chunk_params("Updated content", chunk_hash, test_file))
        assert result2.is_ok
        assert result2.value["status"] == "deduplicated"
        assert result2.value["memory_id"] == memory_id

        # Content should be updated
        mem = mnemosyne.get(memory_id)
        assert mem.get("content") == "Updated content"

    def test_nonempty_memory_not_redundantly_updated(self, use_case: RememberMemoryUseCase, mnemosyne: MnemosyneClient, tmp_path: Path):
        """If memory already has correct content, no redundant update."""
        test_file = tmp_path / "test_node.md"
        test_file.write_text("---\ntitle: Test Node\n---\nExisting content")
        chunk_hash = "samehash"

        # First ingestion
        result1 = use_case.execute(_file_chunk_params("Existing content", chunk_hash, test_file))
        assert result1.is_ok
        memory_id = result1.value["memory_id"]

        # Re-ingest same content — should be deduped without update
        result2 = use_case.execute(_file_chunk_params("Existing content", chunk_hash, test_file))
        assert result2.is_ok
        assert result2.value["status"] == "deduplicated"
        assert result2.value["memory_id"] == memory_id

        # Content should be unchanged
        mem = mnemosyne.get(memory_id)
        assert mem.get("content") == "Existing content"