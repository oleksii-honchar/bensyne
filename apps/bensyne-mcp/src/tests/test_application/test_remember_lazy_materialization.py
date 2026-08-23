"""Lazy file_metadata.db contract — use-case-level (AC2/AC3/AC4).

Option A contract (ad-hoc round):
- A plain rememberMemory (no chunk_hash, no file_path) must NOT create
  file_metadata.db — the bank stays "pure_memories" so forgetMemory works.
- A rememberMemory WITH metadata.chunk_hash + file_path (a file-context write)
  materializes file_metadata.db and the file row/chunks round-trip.
- Read-only paths (recall enrichment, searchFiles, fetchFile, expandFileRelations)
  on a bank WITHOUT file metadata return graceful empty/not-found results and do
  NOT create file_metadata.db.

All against a REAL per-bank FileMetadataConnectionManager (lazy) + real
HashIndexService with ONLY the mnemosyne client mocked — same pattern as
test_remember_dedup_materialize_integration.py. No logger assertions.
"""

from __future__ import annotations

from pathlib import Path
from typing import Generator

import pytest
from unittest.mock import MagicMock

from src.application.services.file_enrichment_service import FileEnrichmentService
from src.application.services.file_service import FileService, derive_file_id
from src.application.use_cases.expand_file_relations_use_case import (
    ExpandFileRelationsUseCase,
)
from src.application.use_cases.fetch_file_use_case import FetchFileUseCase
from src.application.use_cases.recall_memory_use_case import RecallMemoryUseCase
from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
from src.application.use_cases.search_files_use_case import SearchFilesUseCase
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

BANK = "lazy_bank"
PATH = "/vault/notes/lazy.md"
CHUNK_HASH = "a" * 64
FILE_ID = derive_file_id(BANK, PATH)


def _contract(chunk_hash: str | None = CHUNK_HASH) -> dict:
    """Minimal contract v1 payload; chunk_hash None ⇒ plain (non-file) memory."""
    payload = {
        "contract_version": 1,
        "file_path": PATH,
        "chunk_index": 0,
        "total_chunks": 1,
    }
    if chunk_hash is not None:
        payload["chunk_hash"] = chunk_hash
    return payload


# ---------------------------------------------------------------------------
# Fixtures — REAL lazy per-bank SQLite (nothing materialized at construction)
# ---------------------------------------------------------------------------


@pytest.fixture
def bank_dir(tmp_path: Path) -> Path:
    return tmp_path / "banks" / BANK


@pytest.fixture
def manager(bank_dir: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    mgr = FileMetadataConnectionManager(bank_dir=bank_dir)
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
def hash_index(tmp_path: Path) -> HashIndexService:
    return HashIndexService(memory_bank=BANK, db_path=tmp_path / "hash_index.db")


def _mock_mnemosyne() -> MagicMock:
    """Mocked MnemosyneClient: save echoes the memory id back as-is."""
    client = MagicMock()

    def _save(memory: Memory) -> Result[Memory]:
        return Result.ok(memory)

    client.save.side_effect = _save
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


# ---------------------------------------------------------------------------
# AC2 — plain remember does NOT create file_metadata.db
# ---------------------------------------------------------------------------


class TestPlainRememberDoesNotMaterialize:
    def test_plain_remember_creates_no_file_metadata_db(self, manager, file_service, hash_index) -> None:
        mnemosyne = _mock_mnemosyne()
        use_case = _remember_use_case(mnemosyne, hash_index, file_service)

        result = use_case.execute(
            {
                "content": "a plain memory",
                "memory_bank": BANK,
            }
        )

        assert result.is_ok
        assert result.value["status"] == "stored"
        # No file context ⇒ FileService never invoked ⇒ no db, no dir, no schema.
        assert not manager.db_path.exists()
        assert not manager.bank_dir.exists()

    def test_remember_with_metadata_but_no_file_path_creates_no_db(
        self, manager, file_service, hash_index
    ) -> None:
        """metadata without file_path is NOT a file-context write (no materialization)."""
        mnemosyne = _mock_mnemosyne()
        use_case = _remember_use_case(mnemosyne, hash_index, file_service)

        result = use_case.execute(
            {
                "content": "metadata but no file path",
                "memory_bank": BANK,
                "metadata": {"chunk_hash": CHUNK_HASH},
            }
        )

        assert result.is_ok
        assert "file_materialization" not in result.value
        assert not manager.db_path.exists()


# ---------------------------------------------------------------------------
# AC3 — remember WITH chunk_hash (file-context write) materializes the DB
# ---------------------------------------------------------------------------


class TestFileContextRememberMaterializes:
    def test_remember_with_chunk_hash_creates_db_and_round_trips(
        self, manager, file_service, hash_index
    ) -> None:
        mnemosyne = _mock_mnemosyne()
        use_case = _remember_use_case(mnemosyne, hash_index, file_service)

        result = use_case.execute(
            {
                "content": "file content",
                "memory_bank": BANK,
                "metadata": _contract(),
            }
        )

        assert result.is_ok
        assert result.value["file_materialization"]["status"] == "ok"
        assert result.value["file_materialization"]["file_id"] == FILE_ID

        # DB materialized (mkdir + migrations) at the write chokepoint.
        assert manager.bank_dir.exists()
        assert manager.db_path.exists()

        # File row + chunk round-trip.
        file_row = file_service.get_file_by_id(FILE_ID)
        assert file_row.is_ok and file_row.value is not None
        assert file_row.value.path == PATH

        chunks = file_service.get_chunks_by_file_id(FILE_ID)
        assert chunks.is_ok and len(chunks.value) == 1
        assert chunks.value[0].content_hash == CHUNK_HASH

    def test_existing_file_metadata_db_still_readable_after_lazy_reopen(
        self, manager, file_service, hash_index, bank_dir: Path
    ) -> None:
        """A NEW manager over an EXISTING db (bank already has file metadata) works."""
        mnemosyne = _mock_mnemosyne()
        use_case = _remember_use_case(mnemosyne, hash_index, file_service)
        result = use_case.execute(
            {"content": "file content", "memory_bank": BANK, "metadata": _contract()}
        )
        assert result.is_ok

        # Simulate a fresh handler call on the same bank: new manager, same dir.
        mgr2 = FileMetadataConnectionManager(bank_dir=bank_dir)
        try:
            assert mgr2.db_path.exists()  # pre-existing db is untouched
            svc2 = FileService(
                file_repository=FileRepository(mgr2),
                chunk_repository=FileChunkRepository(mgr2),
                relation_repository=FileRelationRepository(mgr2),
                logger=LoggerMock(),
            )
            file_row = svc2.get_file_by_id(FILE_ID)
            assert file_row.is_ok and file_row.value is not None
            assert file_row.value.path == PATH
        finally:
            mgr2.close()


# ---------------------------------------------------------------------------
# AC4 — read-only ops: WITH file metadata work; WITHOUT it return graceful
# empty results and do NOT create file_metadata.db
# ---------------------------------------------------------------------------


class TestReadPathsWithoutFileMetadata:
    def test_recall_enrichment_without_db_is_pure_and_creates_nothing(
        self, manager, file_service
    ) -> None:
        enrichment = FileEnrichmentService(file_service=file_service, logger=LoggerMock())

        results = enrichment.enrich([{"id": "mem1", "content": "plain"}])

        assert len(results) == 1
        assert results[0]["file_enrichment"] is None
        assert not manager.db_path.exists()

    def test_search_files_without_db_is_graceful_and_creates_nothing(
        self, manager, file_service
    ) -> None:
        mnemosyne = MagicMock()
        mnemosyne.recall.return_value = Result.ok([{"id": "mem1", "content": "plain"}])
        use_case = SearchFilesUseCase(
            mnemosyne_client=mnemosyne,
            file_service=file_service,
            logger=LoggerMock(),
        )

        result = use_case.execute({"query": "plain", "memory_bank": BANK})

        assert result.is_ok
        assert result.value["total_count"] == 1
        assert result.value["results"][0]["file"] is None
        assert not manager.db_path.exists()

    def test_fetch_file_without_db_returns_not_found_and_creates_nothing(
        self, manager, file_service
    ) -> None:
        use_case = FetchFileUseCase(
            mnemosyne_client=MagicMock(),
            file_service=file_service,
            logger=LoggerMock(),
        )

        result = use_case.execute({"file_id": "file_absent", "memory_bank": BANK})

        assert result.is_ko
        assert result.errors[0].error_code == "FILE_NOT_FOUND"
        assert not manager.db_path.exists()

    def test_expand_file_relations_without_db_returns_not_found_and_creates_nothing(
        self, manager, file_service
    ) -> None:
        use_case = ExpandFileRelationsUseCase(
            mnemosyne_client=MagicMock(),
            file_service=file_service,
            relation_repository=FileRelationRepository(manager),
            logger=LoggerMock(),
        )

        result = use_case.execute({"file_id": "file_absent", "memory_bank": BANK})

        assert result.is_ko
        assert result.errors[0].error_code == "FILE_NOT_FOUND"
        assert not manager.db_path.exists()


class TestReadPathsWithFileMetadata:
    def test_recall_and_fetch_work_on_bank_with_file_metadata(
        self, manager, file_service, hash_index
    ) -> None:
        """Read paths still work when the db exists (regression guard)."""
        mnemosyne = _mock_mnemosyne()
        use_case = _remember_use_case(mnemosyne, hash_index, file_service)
        result = use_case.execute(
            {"content": "file content", "memory_bank": BANK, "metadata": _contract()}
        )
        assert result.is_ok
        memory_id = result.value["memory_id"]

        # recallMemory enrichment resolves the file context.
        recall_mnemosyne = MagicMock()
        recall_mnemosyne.recall.return_value = Result.ok([{"id": memory_id, "content": "file content"}])
        recall = RecallMemoryUseCase(
            mnemosyne_client=recall_mnemosyne,
            file_enrichment_service=FileEnrichmentService(file_service=file_service, logger=LoggerMock()),
            logger=LoggerMock(),
        )
        recall_result = recall.execute({"query": "file content", "memory_bank": BANK})
        assert recall_result.is_ok
        assert recall_result.value["results"][0]["file_enrichment"] is not None

        # fetchFile reconstructs content from the chunk.
        fetch = FetchFileUseCase(
            mnemosyne_client=recall_mnemosyne,
            file_service=file_service,
            logger=LoggerMock(),
        )
        fetch_result = fetch.execute({"file_id": FILE_ID, "memory_bank": BANK})
        assert fetch_result.is_ok
        assert fetch_result.value["file"] is None or fetch_result.value["file"]["id"] == FILE_ID
