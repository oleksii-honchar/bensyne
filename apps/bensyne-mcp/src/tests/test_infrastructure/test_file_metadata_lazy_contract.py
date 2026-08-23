"""Lazy file_metadata.db contract — repo-level read guards + write materialization.

Option A contract (ad-hoc round): constructing a FileMetadataConnectionManager /
bundle performs NO filesystem writes. The DB file materializes only when file
metadata is actually WRITTEN (save_file / save_chunk / save_relation / deletes).
READ paths (get_file_by_id, get_chunks_by_file_id, get_relations_by_file_id,
search, list, fetch) on a bank WITHOUT file metadata return graceful empty
results and must NOT leave a file_metadata.db behind.

These tests pin the repo-level behaviour:
- reads on an absent db → empty Result.ok (None / []) with NO db/dir created
- writes on an absent db → db + dir materialize, then reads work
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from src.domain.file_chunk_entity import ContentType, FileChunk
from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.file_relation_entity import FileRelation, RelationType
from src.infrastructure.storage.sqlite.file_chunk_repository import FileChunkRepository
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_relation_repository import FileRelationRepository
from src.infrastructure.storage.sqlite.file_repository import FileRepository

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _a_file(id: str = "f1", path: str = "/tmp/test.txt") -> File:
    result = File.of(
        {
            "id": id,
            "path": path,
            "source_type": SourceType.UNKNOWN,
            "hash": None,
            "file_type": None,
            "size": None,
            "language": None,
            "aggregated_keywords": [],
            "aggregated_tags": [],
            "status": FileStatus.PENDING,
            "total_chunks": 0,
            "average_importance": 0.5,
            "metadata": {},
            "created_at": datetime.now(),
        }
    )
    assert result.is_ok, f"Failed to create test file: {result.errors}"
    return result.value


def _a_chunk(file_id: str, memory_id: str, chunk_index: int = 0) -> FileChunk:
    result = FileChunk.of(
        {
            "id": f"fc_{file_id}_{memory_id}",
            "file_id": file_id,
            "memory_id": memory_id,
            "chunk_index": chunk_index,
            "start_line": 0,
            "end_line": 10,
            "content_type": ContentType.TEXT,
            "is_partial": False,
            "section_header": None,
            "parent_unit_ref": None,
            "parent_unit_summary": None,
            "content_hash": None,
        }
    )
    assert result.is_ok, f"Failed to create test chunk: {result.errors}"
    return result.value


def _a_relation(source_file_id: str, target_file_id: str) -> FileRelation:
    result = FileRelation.of(
        {
            "id": f"fr_{source_file_id}_{target_file_id}",
            "source_file_id": source_file_id,
            "target_file_id": target_file_id,
            "relation_type": RelationType.PARENT_CHILD,
            "strength": 1.0,
            "description": None,
        }
    )
    assert result.is_ok, f"Failed to create test relation: {result.errors}"
    return result.value


# ---------------------------------------------------------------------------
# Reads never materialize the DB
# ---------------------------------------------------------------------------


class TestReadsDoNotMaterialize:
    """Read-only repo ops on a bank without file metadata return empty results
    and create neither the bank dir nor file_metadata.db."""

    def test_file_repo_reads_create_nothing_and_return_empty(self, tmp_path: Path) -> None:
        bank_dir = tmp_path / "bank"
        mgr = FileMetadataConnectionManager(bank_dir=bank_dir)
        repo = FileRepository(mgr)
        try:
            by_id = repo.get_file_by_id("nope")
            assert by_id.is_ok and by_id.value is None

            by_path = repo.get_file_by_path("/tmp/nope.txt")
            assert by_path.is_ok and by_path.value is None

            listed = repo.list_files()
            assert listed.is_ok and listed.value == []

            searched = repo.search_files_by_query("anything")
            assert searched.is_ok and searched.value == []

            assert not bank_dir.exists()
            assert not mgr.db_path.exists()
        finally:
            mgr.close()

    def test_chunk_repo_reads_create_nothing_and_return_empty(self, tmp_path: Path) -> None:
        bank_dir = tmp_path / "bank"
        mgr = FileMetadataConnectionManager(bank_dir=bank_dir)
        repo = FileChunkRepository(mgr)
        try:
            by_id = repo.get_chunk_by_id("fc_x")
            assert by_id.is_ok and by_id.value is None

            by_file = repo.get_chunks_by_file_id("file_x")
            assert by_file.is_ok and by_file.value == []

            by_memory = repo.get_chunk_by_memory_id("mem_x")
            assert by_memory.is_ok and by_memory.value is None

            by_memories = repo.get_chunks_by_memory_id("mem_x")
            assert by_memories.is_ok and by_memories.value == []

            assert not bank_dir.exists()
            assert not mgr.db_path.exists()
        finally:
            mgr.close()

    def test_relation_repo_reads_create_nothing_and_return_empty(self, tmp_path: Path) -> None:
        bank_dir = tmp_path / "bank"
        mgr = FileMetadataConnectionManager(bank_dir=bank_dir)
        repo = FileRelationRepository(mgr)
        try:
            by_id = repo.get_relation_by_id("fr_x")
            assert by_id.is_ok and by_id.value is None

            by_file = repo.get_relations_by_file_id("file_x")
            assert by_file.is_ok and by_file.value == []

            by_type = repo.get_relations_by_type(RelationType.PARENT_CHILD)
            assert by_type.is_ok and by_type.value == []

            pair = repo.get_by_pair("file_a", "file_b", RelationType.PARENT_CHILD)
            assert pair.is_ok and pair.value is None

            assert not bank_dir.exists()
            assert not mgr.db_path.exists()
        finally:
            mgr.close()

    def test_delete_ops_on_absent_db_do_not_materialize(self, tmp_path: Path) -> None:
        """Deletes with nothing to delete are no-ops and must not create the db."""
        bank_dir = tmp_path / "bank"
        mgr = FileMetadataConnectionManager(bank_dir=bank_dir)
        file_repo = FileRepository(mgr)
        chunk_repo = FileChunkRepository(mgr)
        relation_repo = FileRelationRepository(mgr)
        try:
            assert file_repo.delete_file("nope").is_ok
            assert chunk_repo.delete_chunk("nope").is_ok
            assert chunk_repo.delete_chunks_by_file_id("nope", set()).is_ok
            assert relation_repo.delete_relation("nope").is_ok
            assert relation_repo.delete_relations_by_file_id("nope").is_ok

            assert not bank_dir.exists()
            assert not mgr.db_path.exists()
        finally:
            mgr.close()


# ---------------------------------------------------------------------------
# Writes materialize the DB
# ---------------------------------------------------------------------------


class TestWritesMaterialize:
    """Write-triggered ops create the bank dir + file_metadata.db, then reads work."""

    def test_save_file_materializes_db_and_round_trips(self, tmp_path: Path) -> None:
        bank_dir = tmp_path / "bank"
        mgr = FileMetadataConnectionManager(bank_dir=bank_dir)
        repo = FileRepository(mgr)
        try:
            assert not mgr.db_path.exists()

            file = _a_file(id="w1", path="/tmp/roundtrip.txt")
            save = repo.save_file(file)
            assert save.is_ok

            assert bank_dir.exists()
            assert mgr.db_path.exists()

            got = repo.get_file_by_id("w1")
            assert got.is_ok and got.value is not None
            assert got.value.path == "/tmp/roundtrip.txt"
        finally:
            mgr.close()

    def test_save_chunk_and_relation_materialize_db(self, tmp_path: Path) -> None:
        bank_dir = tmp_path / "bank"
        mgr = FileMetadataConnectionManager(bank_dir=bank_dir)
        file_repo = FileRepository(mgr)
        chunk_repo = FileChunkRepository(mgr)
        relation_repo = FileRelationRepository(mgr)
        try:
            assert not mgr.db_path.exists()

            assert file_repo.save_file(_a_file(id="a", path="/tmp/a.md")).is_ok
            assert file_repo.save_file(_a_file(id="b", path="/tmp/b.md")).is_ok
            assert chunk_repo.save_chunk(_a_chunk("a", "mem1")).is_ok
            assert relation_repo.save_relation(_a_relation("a", "b")).is_ok

            assert mgr.db_path.exists()

            chunks = chunk_repo.get_chunks_by_file_id("a")
            assert chunks.is_ok and len(chunks.value) == 1
            relations = relation_repo.get_relations_by_file_id("a")
            assert relations.is_ok and len(relations.value) == 1
        finally:
            mgr.close()
