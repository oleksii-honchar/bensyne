"""FileRelationRepository tests — SQLite-backed FileRelationRepository implementation.

Tests all repository operations using an in-memory SQLite database via
FileMetadataConnectionManager.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Generator, List, Optional

import pytest

from src.domain.file_entity import File, FileStatus, SourceType
from src.domain.file_relation_entity import Direction, FileRelation, RelationType
from src.utils.result import Result
from src.infrastructure.storage.sqlite.file_metadata_connection import (
    FileMetadataConnectionManager,
)
from src.infrastructure.storage.sqlite.file_repository import FileRepository

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def tmp_bank_dir(tmp_path: Path) -> Path:
    """Return a temporary directory simulating a memory bank's data dir."""
    return tmp_path / "test_bank"


@pytest.fixture
def manager(tmp_bank_dir: Path) -> Generator[FileMetadataConnectionManager, None, None]:
    """Create a FileMetadataConnectionManager backed by a temporary directory."""
    mgr = FileMetadataConnectionManager(bank_dir=tmp_bank_dir)
    yield mgr
    mgr.close()


@pytest.fixture
def repo(manager: FileMetadataConnectionManager) -> Generator[FileRelationRepository, None, None]:
    """Create a FileRelationRepository backed by a temporary database."""
    from src.infrastructure.storage.sqlite.file_relation_repository import FileRelationRepository
    r = FileRelationRepository(manager)
    yield r


@pytest.fixture
def file_repo(manager: FileMetadataConnectionManager) -> FileRepository:
    """Create a FileRepository for seeding files (FK constraints)."""
    return FileRepository(manager)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _a_file(
    id: str = "f1",
    path: str = "/tmp/test.txt",
    source_type: SourceType = SourceType.FILE_SYSTEM,
    status: FileStatus = FileStatus.PENDING,
    created_at: Optional[datetime] = None,
) -> File:
    """Create a valid File instance with sensible defaults."""
    result = File.of({
        "id": id,
        "path": path,
        "source_type": source_type,
        "status": status,
        "created_at": created_at or datetime.now(),
    })
    assert result.is_ok, f"Failed to create test file: {result.errors}"
    return result.value


def _seed_file(file_repo: FileRepository, file_id: str = "f1") -> File:
    """Save a file to satisfy FK constraints for file_relations tests."""
    f = _a_file(id=file_id)
    result = file_repo.save_file(f)
    assert result.is_ok, f"Failed to seed file: {result.errors}"
    return result.value


def _a_relation(
    id: str = "r1",
    source_file_id: str = "f1",
    target_file_id: str = "f2",
    relation_type: RelationType = RelationType.PARENT_CHILD,
    strength: float = 1.0,
    direction: Direction = Direction.UNIDIRECTIONAL,
    description: Optional[str] = None,
    created_at: Optional[datetime] = None,
) -> FileRelation:
    """Create a valid FileRelation instance with sensible defaults."""
    result = FileRelation.of({
        "id": id,
        "source_file_id": source_file_id,
        "target_file_id": target_file_id,
        "relation_type": relation_type,
        "strength": strength,
        "direction": direction,
        "description": description,
        "created_at": created_at or datetime.now(),
    })
    assert result.is_ok, f"Failed to create test relation: {result.errors}"
    return result.value

# ---------------------------------------------------------------------------
# save_relation
# ---------------------------------------------------------------------------

class TestSaveRelation:
    """FileRelationRepository.save_relation operations."""

    def test_save_relation_returns_result_ok_with_relation(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        relation = _a_relation(id="sr1")
        result = repo.save_relation(relation)
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "sr1"

    def test_save_relation_persists_to_database(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        relation = _a_relation(id="sr2", strength=0.75)
        save_result = repo.save_relation(relation)
        assert save_result.is_ok

        find_result = repo.get_relation_by_id("sr2")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.strength == 0.75

    def test_save_relation_overwrites_existing(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        rel1 = _a_relation(id="sr3", strength=0.5)
        rel2 = _a_relation(id="sr3", strength=0.9)
        repo.save_relation(rel1)
        result = repo.save_relation(rel2)
        assert result.is_ok is True
        assert result.value.strength == 0.9

        find_result = repo.get_relation_by_id("sr3")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.strength == 0.9

    def test_save_relation_stores_all_fields(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        relation = _a_relation(
            id="sr4",
            source_file_id="f1",
            target_file_id="f2",
            relation_type=RelationType.SIBLING,
            strength=0.85,
            direction=Direction.BIDIRECTIONAL,
            description="Sibling files",
        )
        save_result = repo.save_relation(relation)
        assert save_result.is_ok

        find_result = repo.get_relation_by_id("sr4")
        assert find_result.is_ok
        assert find_result.value is not None
        r = find_result.value
        assert r.source_file_id == "f1"
        assert r.target_file_id == "f2"
        assert r.relation_type == RelationType.SIBLING
        assert r.strength == 0.85
        assert r.direction == Direction.BIDIRECTIONAL
        assert r.description == "Sibling files"

    def test_save_relation_with_none_description(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        relation = _a_relation(id="sr5", description=None)
        save_result = repo.save_relation(relation)
        assert save_result.is_ok

        find_result = repo.get_relation_by_id("sr5")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.description is None

# ---------------------------------------------------------------------------
# get_relation_by_id
# ---------------------------------------------------------------------------

class TestGetRelationById:
    """FileRelationRepository.get_relation_by_id operations."""

    def test_get_relation_by_id_returns_relation(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        relation = _a_relation(id="gr1", source_file_id="f1", target_file_id="f2")
        repo.save_relation(relation)
        result = repo.get_relation_by_id("gr1")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "gr1"
        assert result.value.source_file_id == "f1"
        assert result.value.target_file_id == "f2"

    def test_get_relation_by_id_returns_none_when_not_found(self, repo: FileRelationRepository) -> None:
        result = repo.get_relation_by_id("nonexistent")
        assert result.is_ok is True
        assert result.value is None

# ---------------------------------------------------------------------------
# get_relations_by_file_id
# ---------------------------------------------------------------------------

class TestGetRelationsByFileId:
    """FileRelationRepository.get_relations_by_file_id operations."""

    def test_get_relations_by_file_id_returns_relations_where_source(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        _seed_file(file_repo, "f3")
        r1 = _a_relation(id="fr1", source_file_id="f1", target_file_id="f2")
        r2 = _a_relation(id="fr2", source_file_id="f1", target_file_id="f3")
        r3 = _a_relation(id="fr3", source_file_id="f2", target_file_id="f4")
        repo.save_relation(r1)
        repo.save_relation(r2)
        repo.save_relation(r3)

        result = repo.get_relations_by_file_id("f1")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 2
        ids = {r.id for r in result.value}
        assert ids == {"fr1", "fr2"}

    def test_get_relations_by_file_id_returns_relations_where_target(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        _seed_file(file_repo, "f3")
        _seed_file(file_repo, "f4")
        r1 = _a_relation(id="fr4", source_file_id="f2", target_file_id="f1")
        r2 = _a_relation(id="fr5", source_file_id="f3", target_file_id="f1")
        r3 = _a_relation(id="fr6", source_file_id="f4", target_file_id="f5")
        repo.save_relation(r1)
        repo.save_relation(r2)
        repo.save_relation(r3)

        result = repo.get_relations_by_file_id("f1")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 2
        ids = {r.id for r in result.value}
        assert ids == {"fr4", "fr5"}

    def test_get_relations_by_file_id_returns_relations_where_either(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        r1 = _a_relation(id="fr7", source_file_id="f1", target_file_id="f2")
        r2 = _a_relation(id="fr8", source_file_id="f2", target_file_id="f1")
        repo.save_relation(r1)
        repo.save_relation(r2)

        result = repo.get_relations_by_file_id("f1")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 2

    def test_get_relations_by_file_id_returns_empty_when_no_relations(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f2")
        _seed_file(file_repo, "f3")
        r1 = _a_relation(id="fr9", source_file_id="f2", target_file_id="f3")
        repo.save_relation(r1)

        result = repo.get_relations_by_file_id("nonexistent")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 0

# ---------------------------------------------------------------------------
# get_relations_by_type
# ---------------------------------------------------------------------------

class TestGetRelationsByType:
    """FileRelationRepository.get_relations_by_type operations."""

    def test_get_relations_by_type_returns_matching_relations(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        _seed_file(file_repo, "f3")
        r1 = _a_relation(id="tt1", source_file_id="f1", target_file_id="f2", relation_type=RelationType.PARENT_CHILD)
        r2 = _a_relation(id="tt2", source_file_id="f1", target_file_id="f3", relation_type=RelationType.PARENT_CHILD)
        r3 = _a_relation(id="tt3", source_file_id="f2", target_file_id="f3", relation_type=RelationType.SIBLING)
        repo.save_relation(r1)
        repo.save_relation(r2)
        repo.save_relation(r3)

        result = repo.get_relations_by_type(RelationType.PARENT_CHILD)
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 2
        ids = {r.id for r in result.value}
        assert ids == {"tt1", "tt2"}

    def test_get_relations_by_type_returns_empty_when_no_matches(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        r1 = _a_relation(id="tt4", source_file_id="f1", target_file_id="f2", relation_type=RelationType.PARENT_CHILD)
        repo.save_relation(r1)

        result = repo.get_relations_by_type(RelationType.BACKLINK)
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 0

# ---------------------------------------------------------------------------
# delete_relation
# ---------------------------------------------------------------------------

class TestDeleteRelation:
    """FileRelationRepository.delete_relation operations."""

    def test_delete_relation_returns_true_when_found(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        relation = _a_relation(id="dr1")
        repo.save_relation(relation)
        result = repo.delete_relation("dr1")
        assert result.is_ok is True
        assert result.value is True

    def test_delete_relation_returns_false_when_not_found(self, repo: FileRelationRepository) -> None:
        result = repo.delete_relation("nonexistent")
        assert result.is_ok is True
        assert result.value is False

    def test_delete_relation_removes_from_store(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        relation = _a_relation(id="dr2")
        repo.save_relation(relation)
        repo.delete_relation("dr2")
        find_result = repo.get_relation_by_id("dr2")
        assert find_result.is_ok is True
        assert find_result.value is None

# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

class TestRoundTrip:
    """End-to-end round-trip tests for FileRelationRepository."""

    def test_round_trip_save_and_get_by_id(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        relation = _a_relation(id="rt1", source_file_id="f1", target_file_id="f2")
        save_result = repo.save_relation(relation)
        assert save_result.is_ok
        find_result = repo.get_relation_by_id("rt1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.source_file_id == "f1"
        assert find_result.value.target_file_id == "f2"

    def test_round_trip_save_and_get_by_file_id(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        relation = _a_relation(id="rt2", source_file_id="f1", target_file_id="f2")
        repo.save_relation(relation)
        find_result = repo.get_relations_by_file_id("f1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert len(find_result.value) == 1
        assert find_result.value[0].id == "rt2"

    def test_round_trip_save_and_get_by_type(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        relation = _a_relation(id="rt3", relation_type=RelationType.SIBLING)
        repo.save_relation(relation)
        find_result = repo.get_relations_by_type(RelationType.SIBLING)
        assert find_result.is_ok
        assert find_result.value is not None
        assert len(find_result.value) == 1
        assert find_result.value[0].id == "rt3"

    def test_round_trip_save_update_and_get(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        relation = _a_relation(id="rt4", strength=0.5)
        repo.save_relation(relation)

        updated_result = relation.update_strength(0.9)
        assert updated_result.is_ok
        repo.save_relation(updated_result.value)

        find_result = repo.get_relation_by_id("rt4")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.strength == 0.9

    def test_round_trip_save_delete_and_verify(self, repo: FileRelationRepository, file_repo: FileRepository) -> None:
        _seed_file(file_repo, "f1")
        _seed_file(file_repo, "f2")
        relation = _a_relation(id="rt5", source_file_id="f1", target_file_id="f2")
        repo.save_relation(relation)

        # Verify it exists
        find_result = repo.get_relation_by_id("rt5")
        assert find_result.is_ok
        assert find_result.value is not None

        # Delete it
        delete_result = repo.delete_relation("rt5")
        assert delete_result.is_ok
        assert delete_result.value is True

        # Verify it's gone
        after_delete = repo.get_relation_by_id("rt5")
        assert after_delete.is_ok
        assert after_delete.value is None

        # Verify it's gone from file_id query too
        after_file = repo.get_relations_by_file_id("f1")
        assert after_file.is_ok
        assert after_file.value is not None
        assert len(after_file.value) == 0
