"""FileRelationRepository interface contract tests.

Verifies that the FileRelationRepository abstract interface defines the correct
method signatures and that an in-memory implementation satisfies the
Result pattern for all operations.
"""

from datetime import datetime
from typing import List, Optional

import pytest

from src.domain.entities.file_relation import Direction, FileRelation, RelationType
from src.domain.interfaces import FileRelationRepository
from src.domain.result import Result

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _a_relation(
    id: str = "r1",
    source_file_id: str = "f1",
    target_file_id: str = "f2",
    relation_type: RelationType = RelationType.PARENT_CHILD,
    strength: float = 1.0,
    direction: Direction = Direction.UNIDIRECTIONAL,
    description: Optional[str] = None,
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
    })
    assert result.is_ok, f"Failed to create test relation: {result.errors}"
    return result.value

# ---------------------------------------------------------------------------
# Tests against the abstract interface (no implementation required)
# ---------------------------------------------------------------------------

class TestFileRelationRepositoryInterface:
    """FileRelationRepository defines the correct abstract interface."""

    def test_file_relation_repository_is_abstract(self):
        # Instantiation should fail because it's abstract
        with pytest.raises(TypeError):
            FileRelationRepository()  # type: ignore

    def test_file_relation_repository_has_save_relation_method(self):
        assert hasattr(FileRelationRepository, "save_relation")
        assert callable(getattr(FileRelationRepository, "save_relation"))

    def test_file_relation_repository_has_get_relation_by_id_method(self):
        assert hasattr(FileRelationRepository, "get_relation_by_id")
        assert callable(getattr(FileRelationRepository, "get_relation_by_id"))

    def test_file_relation_repository_has_get_relations_by_file_id_method(self):
        assert hasattr(FileRelationRepository, "get_relations_by_file_id")
        assert callable(getattr(FileRelationRepository, "get_relations_by_file_id"))

    def test_file_relation_repository_has_get_relations_by_type_method(self):
        assert hasattr(FileRelationRepository, "get_relations_by_type")
        assert callable(getattr(FileRelationRepository, "get_relations_by_type"))

    def test_file_relation_repository_has_delete_relation_method(self):
        assert hasattr(FileRelationRepository, "delete_relation")
        assert callable(getattr(FileRelationRepository, "delete_relation"))

    def test_save_relation_is_abstract(self):
        method = getattr(FileRelationRepository, "save_relation")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_get_relation_by_id_is_abstract(self):
        method = getattr(FileRelationRepository, "get_relation_by_id")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_get_relations_by_file_id_is_abstract(self):
        method = getattr(FileRelationRepository, "get_relations_by_file_id")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_get_relations_by_type_is_abstract(self):
        method = getattr(FileRelationRepository, "get_relations_by_type")
        assert getattr(method, "__isabstractmethod__", False) is True

    def test_delete_relation_is_abstract(self):
        method = getattr(FileRelationRepository, "delete_relation")
        assert getattr(method, "__isabstractmethod__", False) is True

# ---------------------------------------------------------------------------
# In-memory implementation for contract verification
# ---------------------------------------------------------------------------

class InMemoryFileRelationRepository(FileRelationRepository):
    """Minimal in-memory FileRelationRepository for contract testing."""

    def __init__(self, data: Optional[List[FileRelation]] = None) -> None:
        self._store: dict[str, FileRelation] = {}
        if data:
            for r in data:
                self._store[r.id] = r

    def save_relation(self, relation: FileRelation) -> Result[FileRelation]:
        self._store[relation.id] = relation
        return Result.ok(relation)

    def get_relation_by_id(self, relation_id: str) -> Result[Optional[FileRelation]]:
        return Result.ok(self._store.get(relation_id))

    def get_relations_by_file_id(self, file_id: str) -> Result[List[FileRelation]]:
        relations = [
            r for r in self._store.values()
            if r.source_file_id == file_id or r.target_file_id == file_id
        ]
        return Result.ok(relations)

    def get_relations_by_type(self, relation_type: RelationType) -> Result[List[FileRelation]]:
        relations = [
            r for r in self._store.values()
            if r.relation_type == relation_type
        ]
        return Result.ok(relations)

    def delete_relation(self, relation_id: str) -> Result[bool]:
        if relation_id in self._store:
            del self._store[relation_id]
            return Result.ok(True)
        return Result.ok(False)

def a_relation_repository(data: Optional[List[FileRelation]] = None) -> InMemoryFileRelationRepository:
    return InMemoryFileRelationRepository(data)

# ---------------------------------------------------------------------------
# Contract tests against in-memory implementation
# ---------------------------------------------------------------------------

class TestFileRelationRepositoryContract:
    """In-memory FileRelationRepository satisfies the Result contract for all operations."""

    def test_implementation_is_instance_of_file_relation_repository(self):
        repo = a_relation_repository()
        assert isinstance(repo, FileRelationRepository)

    # --- save_relation ---

    def test_save_relation_returns_result_ok_with_relation(self):
        relation = _a_relation(id="s1")
        repo = a_relation_repository()
        result = repo.save_relation(relation)
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "s1"

    def test_save_relation_overwrites_existing(self):
        rel1 = _a_relation(id="s2", strength=0.5)
        rel2 = _a_relation(id="s2", strength=0.9)
        repo = a_relation_repository()
        repo.save_relation(rel1)
        result = repo.save_relation(rel2)
        assert result.is_ok is True
        assert result.value.strength == 0.9
        find_result = repo.get_relation_by_id("s2")
        assert find_result.is_ok is True
        assert find_result.value is not None
        assert find_result.value.strength == 0.9

    # --- get_relation_by_id ---

    def test_get_relation_by_id_returns_result_ok_with_relation(self):
        relation = _a_relation(id="g1")
        repo = a_relation_repository(data=[relation])
        result = repo.get_relation_by_id("g1")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "g1"

    def test_get_relation_by_id_returns_none_when_not_found(self):
        repo = a_relation_repository()
        result = repo.get_relation_by_id("nonexistent")
        assert result.is_ok is True
        assert result.value is None

    # --- get_relations_by_file_id ---

    def test_get_relations_by_file_id_returns_relations_where_source(self):
        r1 = _a_relation(id="f1r1", source_file_id="f1", target_file_id="f2")
        r2 = _a_relation(id="f1r2", source_file_id="f1", target_file_id="f3")
        r3 = _a_relation(id="f2r1", source_file_id="f2", target_file_id="f4")
        repo = a_relation_repository(data=[r1, r2, r3])
        result = repo.get_relations_by_file_id("f1")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 2
        ids = {r.id for r in result.value}
        assert ids == {"f1r1", "f1r2"}

    def test_get_relations_by_file_id_returns_relations_where_target(self):
        r1 = _a_relation(id="f2r1", source_file_id="f2", target_file_id="f1")
        r2 = _a_relation(id="f3r1", source_file_id="f3", target_file_id="f1")
        r3 = _a_relation(id="f4r1", source_file_id="f4", target_file_id="f5")
        repo = a_relation_repository(data=[r1, r2, r3])
        result = repo.get_relations_by_file_id("f1")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 2
        ids = {r.id for r in result.value}
        assert ids == {"f2r1", "f3r1"}

    def test_get_relations_by_file_id_returns_relations_where_either(self):
        r1 = _a_relation(id="src", source_file_id="f1", target_file_id="f2")
        r2 = _a_relation(id="tgt", source_file_id="f2", target_file_id="f1")
        repo = a_relation_repository(data=[r1, r2])
        result = repo.get_relations_by_file_id("f1")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 2

    def test_get_relations_by_file_id_returns_empty_when_no_relations(self):
        r1 = _a_relation(id="f2r1", source_file_id="f2", target_file_id="f3")
        repo = a_relation_repository(data=[r1])
        result = repo.get_relations_by_file_id("nonexistent")
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 0

    # --- get_relations_by_type ---

    def test_get_relations_by_type_returns_matching_relations(self):
        r1 = _a_relation(id="t1", relation_type=RelationType.PARENT_CHILD)
        r2 = _a_relation(id="t2", relation_type=RelationType.PARENT_CHILD)
        r3 = _a_relation(id="t3", relation_type=RelationType.SIBLING)
        repo = a_relation_repository(data=[r1, r2, r3])
        result = repo.get_relations_by_type(RelationType.PARENT_CHILD)
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 2
        ids = {r.id for r in result.value}
        assert ids == {"t1", "t2"}

    def test_get_relations_by_type_returns_empty_when_no_matches(self):
        r1 = _a_relation(id="t1", relation_type=RelationType.PARENT_CHILD)
        repo = a_relation_repository(data=[r1])
        result = repo.get_relations_by_type(RelationType.BACKLINK)
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 0

    # --- delete_relation ---

    def test_delete_relation_returns_true_when_found(self):
        relation = _a_relation(id="d1")
        repo = a_relation_repository(data=[relation])
        result = repo.delete_relation("d1")
        assert result.is_ok is True
        assert result.value is True

    def test_delete_relation_returns_false_when_not_found(self):
        repo = a_relation_repository()
        result = repo.delete_relation("nonexistent")
        assert result.is_ok is True
        assert result.value is False

    def test_delete_relation_removes_from_store(self):
        relation = _a_relation(id="d2")
        repo = a_relation_repository(data=[relation])
        repo.delete_relation("d2")
        find_result = repo.get_relation_by_id("d2")
        assert find_result.is_ok is True
        assert find_result.value is None

    # --- round-trip ---

    def test_round_trip_save_and_get_by_id(self):
        relation = _a_relation(id="rt1", source_file_id="f1", target_file_id="f2")
        repo = a_relation_repository()
        save_result = repo.save_relation(relation)
        assert save_result.is_ok
        find_result = repo.get_relation_by_id("rt1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.source_file_id == "f1"
        assert find_result.value.target_file_id == "f2"

    def test_round_trip_save_and_get_by_file_id(self):
        relation = _a_relation(id="rt2", source_file_id="f1", target_file_id="f2")
        repo = a_relation_repository()
        repo.save_relation(relation)
        find_result = repo.get_relations_by_file_id("f1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert len(find_result.value) == 1
        assert find_result.value[0].id == "rt2"

    def test_round_trip_save_and_get_by_type(self):
        relation = _a_relation(id="rt3", relation_type=RelationType.SIBLING)
        repo = a_relation_repository()
        repo.save_relation(relation)
        find_result = repo.get_relations_by_type(RelationType.SIBLING)
        assert find_result.is_ok
        assert find_result.value is not None
        assert len(find_result.value) == 1
        assert find_result.value[0].id == "rt3"
