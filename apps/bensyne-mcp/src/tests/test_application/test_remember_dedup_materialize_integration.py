"""Integration: dedup-hit STILL materializes — cross-file identical-chunk case (S3).

D14 re-keys the dedup index to ``chunk_hash`` and makes a dedup HIT run the same
materialization step as the stored path, with the EXISTING memory id. This is the
fix for S3 (cross-file identical-chunk projection loss): an identical chunk
remembered under a SECOND file must still get a FileChunk row linking the shared
memory to that second file — otherwise recall/searchFiles for the second file
would lose the projection.

All against a REAL per-bank SQLite database (FileMetadataConnectionManager) +
REAL HashIndexService with ONLY the mnemosyne client mocked — same pattern as
``test_file_roundtrip_integration.py``. No logger assertions; every assertion is
on row counts, entity values, or response shapes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Generator

import pytest
from unittest.mock import MagicMock

from src.application.services.file_service import FileService, derive_file_id
from src.application.use_cases.remember_memory_use_case import RememberMemoryUseCase
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

BANK = "dedup_bank"
PATH_A = "/vault/notes/a.md"
PATH_B = "/vault/notes/b.md"

# Identical chunk content ⇒ identical chunk_hash across the two files (S3).
CHUNK_HASH = "f0e1d2c3b4a5968778695a4b3c2d1e0f9a8b7c6d5e4f3a2b1c0d9e8f7a6b5c4d"

FILE_ID_A = derive_file_id(BANK, PATH_A)
FILE_ID_B = derive_file_id(BANK, PATH_B)


def _contract(file_path: str, chunk_hash: str) -> dict:
    """Minimal contract v1 payload for one chunk of ``file_path`` carrying ``chunk_hash``."""
    return {
        "contract_version": 1,
        "file_path": file_path,
        "chunk_index": 0,
        "total_chunks": 1,
        "chunk_hash": chunk_hash,
    }


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


def _chunk_rows(file_service: FileService, file_id: str) -> list:
    result = file_service.get_chunks_by_file_id(file_id)
    assert result.is_ok
    return result.value  # type: ignore[return-value]


def _file_row(file_service: FileService, file_id: str):
    result = file_service.get_file_by_id(file_id)
    assert result.is_ok
    return result.value  # may be None


# ===================================================================
# S3 — cross-file identical chunk: dedup-hit still materializes
# ===================================================================


class TestDedupHitStillMaterializesCrossFile:
    """Remember the SAME chunk_hash under two different files ⇒ the second file
    gets a FileChunk row linking the SHARED memory (dedup hit materializes)."""

    def test_second_file_gets_chunk_row_for_shared_memory(
        self, file_service: FileService, hash_index: HashIndexService
    ) -> None:
        mnemosyne = _mock_mnemosyne()
        remember = _remember_use_case(mnemosyne, hash_index, file_service)

        # 1. Remember the chunk under file A — dedup MISS ⇒ stored + materialized.
        resp_a = remember.execute(
            {
                "memory_bank": BANK,
                "content": "identical chunk text",
                "metadata": json.loads(json.dumps(_contract(PATH_A, CHUNK_HASH))),
            }
        )
        assert resp_a.is_ok, f"remember A failed: {resp_a.errors}"
        value_a = resp_a.value
        assert value_a["status"] == "stored"  # type: ignore[index]
        shared_memory_id = value_a["memory_id"]  # type: ignore[index]
        assert value_a["file_materialization"]["status"] == "ok"  # type: ignore[index]

        # File A has its chunk row linked to the (newly saved) memory.
        chunks_a = _chunk_rows(file_service, FILE_ID_A)
        assert [c.memory_id for c in chunks_a] == [shared_memory_id]

        # 2. Remember the SAME chunk_hash under file B — dedup HIT (no new memory).
        resp_b = remember.execute(
            {
                "memory_bank": BANK,
                "content": "identical chunk text",
                "metadata": json.loads(json.dumps(_contract(PATH_B, CHUNK_HASH))),
            }
        )
        assert resp_b.is_ok, f"remember B failed: {resp_b.errors}"
        value_b = resp_b.value
        # Dedup HIT response shape: existing id + memory_bank.
        assert value_b["status"] == "deduplicated"  # type: ignore[index]
        assert value_b["memory_id"] == shared_memory_id  # type: ignore[index]
        assert value_b["memory_bank"] == BANK  # type: ignore[index]
        # Materialization ran on the hit path too.
        assert value_b["file_materialization"]["status"] == "ok"  # type: ignore[index]

        # S3 FIX: file B has a FileChunk row linking the SHARED memory — the
        # projection is not lost for the second file with an identical chunk.
        chunks_b = _chunk_rows(file_service, FILE_ID_B)
        assert [c.memory_id for c in chunks_b] == [shared_memory_id]

        # Only ONE mnemosyne memory was ever saved (the dedup hit did not save).
        assert mnemosyne.save.call_count == 1

        # Both file rows exist and are materialized.
        assert _file_row(file_service, FILE_ID_A) is not None
        assert _file_row(file_service, FILE_ID_B) is not None

    def test_dedup_miss_still_indexes_and_materializes(
        self, file_service: FileService, hash_index: HashIndexService
    ) -> None:
        """Dedup MISS path preserved: save → store(chunk_hash, saved_id) → materialize."""
        mnemosyne = _mock_mnemosyne()
        remember = _remember_use_case(mnemosyne, hash_index, file_service)

        resp = remember.execute(
            {
                "memory_bank": BANK,
                "content": "unique chunk text",
                "metadata": json.loads(json.dumps(_contract(PATH_A, CHUNK_HASH))),
            }
        )
        assert resp.is_ok
        value = resp.value
        assert value["status"] == "stored"  # type: ignore[index]
        saved_id = value["memory_id"]  # type: ignore[index]

        # Hash index now maps the chunk_hash → the saved memory id.
        lookup = hash_index.lookup(CHUNK_HASH)
        assert lookup.is_ok
        assert lookup.value == saved_id

        # Materialization produced a chunk row for file A.
        assert [c.memory_id for c in _chunk_rows(file_service, FILE_ID_A)] == [saved_id]