"""Unit tests for domain test utilities and factories."""

from datetime import datetime

from src.domain.memory_bank_aggregate import MemoryBank
from src.domain.memory_entity import Memory
from src.domain.value_objects.file_hash import FileHash

from src.tests.test_domain.domain_test_utils import (
    a_file_hash,
    a_memory,
    a_memory_bank,
    a_memory_bank_aggregate,
    a_memory_bank_repository,
    a_memory_repository,
)


class TestAMemory:
    """a_memory() factory produces valid Memory with defaults and overrides."""

    def test_returns_valid_memory_with_defaults(self):
        memory = a_memory()
        assert isinstance(memory, Memory)
        assert memory.id == "test_memory_id"
        assert memory.content == "Test memory content"
        assert memory.importance == 0.5
        assert memory.source == "conversation"
        assert memory.scope == "working"
        assert memory.created_at is not None
        assert isinstance(memory.created_at, datetime)
        assert memory.updated_at is None
        assert memory.veracity is None
        assert memory.metadata is None

    def test_overrides_id(self):
        memory = a_memory(id="custom_id")
        assert memory.id == "custom_id"

    def test_overrides_content(self):
        memory = a_memory(content="Custom content")
        assert memory.content == "Custom content"

    def test_overrides_importance(self):
        memory = a_memory(importance=0.9)
        assert memory.importance == 0.9

    def test_overrides_source(self):
        memory = a_memory(source="file")
        assert memory.source == "file"

    def test_overrides_scope(self):
        memory = a_memory(scope="episodic")
        assert memory.scope == "episodic"

    def test_overrides_veracity(self):
        memory = a_memory(veracity=0.8)
        assert memory.veracity == 0.8

    def test_overrides_metadata(self):
        meta = {"key": "value"}
        memory = a_memory(metadata=meta)
        assert memory.metadata == meta

    def test_overrides_multiple_fields(self):
        memory = a_memory(id="m1", content="C", importance=0.1, scope="semantic")
        assert memory.id == "m1"
        assert memory.content == "C"
        assert memory.importance == 0.1
        assert memory.scope == "semantic"

    def test_memory_passes_entity_validation(self):
        """Factory output passes Memory.of validation."""
        memory = a_memory()
        # Re-validate through the entity factory
        result = Memory.of({
            "id": memory.id,
            "content": memory.content,
            "importance": memory.importance,
            "source": memory.source,
            "scope": memory.scope,
            "created_at": memory.created_at,
            "updated_at": memory.updated_at,
            "veracity": memory.veracity,
            "metadata": memory.metadata,
        })
        assert result.is_ok is True


class TestAMemoryBank:
    """a_memory_bank() factory produces valid MemoryBank with defaults and overrides."""

    def test_returns_valid_memory_bank_with_defaults(self):
        bank = a_memory_bank()
        assert isinstance(bank, MemoryBank)
        assert bank.name == "test_bank"
        assert bank.description == "A test memory bank"
        assert bank.status == "active"
        assert bank.created_at is not None
        assert isinstance(bank.created_at, datetime)
        assert bank.last_accessed is None
        assert bank.memory_count == 0
        assert bank.memories == []

    def test_overrides_name(self):
        bank = a_memory_bank(name="custom_bank")
        assert bank.name == "custom_bank"

    def test_overrides_description(self):
        bank = a_memory_bank(description="Custom description")
        assert bank.description == "Custom description"

    def test_overrides_status(self):
        bank = a_memory_bank(status="suspended")
        assert bank.status == "suspended"

    def test_overrides_memory_count(self):
        bank = a_memory_bank(memory_count=5)
        assert bank.memory_count == 5

    def test_overrides_memories(self):
        mem1 = a_memory(id="m1")
        bank = a_memory_bank(memories=[mem1])
        assert len(bank.memories) == 1
        assert bank.memories[0].id == "m1"

    def test_overrides_multiple_fields(self):
        bank = a_memory_bank(name="x", description="D", status="registered", memory_count=3)
        assert bank.name == "x"
        assert bank.description == "D"
        assert bank.status == "registered"
        assert bank.memory_count == 3

    def test_bank_passes_entity_validation(self):
        """Factory output passes MemoryBank.of validation."""
        bank = a_memory_bank()
        result = MemoryBank.of(bank.name, bank.description)
        assert result.is_ok is True


class TestAMemoryBank:
    """a_memory_bank_aggregate() factory produces valid MemoryBank with defaults."""

    def test_returns_valid_memory_bank_with_defaults(self):
        agg = a_memory_bank_aggregate()
        assert isinstance(agg, MemoryBank)
        assert agg.status == "active"
        assert isinstance(agg.memories, list)

    def test_overrides_bank(self):
        custom_bank = a_memory_bank(name="custom", status="registered")
        agg = a_memory_bank_aggregate(bank=custom_bank)
        assert agg.name == "custom"
        assert agg.status == "registered"

    def test_overrides_memories(self):
        mem1 = a_memory(id="m1")
        mem2 = a_memory(id="m2")
        agg = a_memory_bank_aggregate(memories=[mem1, mem2])
        assert len(agg.memories) == 2
        assert agg.memories[0].id == "m1"
        assert agg.memories[1].id == "m2"

    def test_aggregate_with_empty_memories(self):
        agg = a_memory_bank_aggregate(memories=[])
        assert agg.memories == []

    def test_aggregate_bank_is_active_by_default(self):
        agg = a_memory_bank_aggregate()
        assert agg.status == "active"


class TestAFileHash:
    """a_file_hash() factory produces valid FileHash with defaults and overrides."""

    def test_returns_valid_file_hash_with_defaults(self):
        fh = a_file_hash()
        assert isinstance(fh, FileHash)
        assert fh.hash_value == "a" * 64

    def test_overrides_hash_value(self):
        custom_hash = "b" * 64
        fh = a_file_hash(hash_value=custom_hash)
        assert fh.hash_value == custom_hash

    def test_file_hash_passes_validation(self):
        """Factory output passes FileHash.of validation."""
        fh = a_file_hash()
        result = FileHash.of(fh.hash_value)
        assert result.is_ok is True


class TestAMemoryRepository:
    """a_memory_repository() provides in-memory repository with save/find."""

    def test_returns_empty_by_default(self):
        repo = a_memory_repository()
        result = repo.find_by_id("nonexistent")
        assert result.is_ok is True
        assert result.value is None

    def test_save_and_find_by_id(self):
        mem = a_memory(id="m1")
        repo = a_memory_repository()
        repo.save(mem)
        result = repo.find_by_id("m1")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "m1"
        assert result.value.content == mem.content

    def test_find_by_id_returns_none_for_missing(self):
        mem = a_memory(id="m1")
        repo = a_memory_repository()
        repo.save(mem)
        result = repo.find_by_id("m2")
        assert result.is_ok is True
        assert result.value is None

    def test_delete_removes_memory(self):
        mem = a_memory(id="m1")
        repo = a_memory_repository()
        repo.save(mem)
        del_result = repo.delete("m1")
        assert del_result.is_ok is True
        assert del_result.value is True
        find_result = repo.find_by_id("m1")
        assert find_result.value is None

    def test_delete_returns_false_for_missing(self):
        repo = a_memory_repository()
        del_result = repo.delete("nonexistent")
        assert del_result.is_ok is True
        assert del_result.value is False

    def test_save_overwrites_existing(self):
        mem1 = a_memory(id="m1", content="First")
        mem2 = a_memory(id="m1", content="Second")
        repo = a_memory_repository()
        repo.save(mem1)
        repo.save(mem2)
        result = repo.find_by_id("m1")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.content == "Second"

    def test_init_with_data(self):
        mem = a_memory(id="m1")
        repo = a_memory_repository(data=[mem])
        result = repo.find_by_id("m1")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "m1"

    def test_find_by_bank_name(self):
        mem1 = a_memory(id="m1", source="bank_a")
        mem2 = a_memory(id="m2", source="bank_b")
        repo = a_memory_repository(data=[mem1, mem2])
        result = repo.find_by_bank("bank_a")
        assert result.is_ok is True
        assert len(result.value) == 1
        assert result.value[0].id == "m1"

    def test_find_by_bank_returns_empty_when_no_match(self):
        repo = a_memory_repository()
        result = repo.find_by_bank("nonexistent")
        assert result.is_ok is True
        assert result.value == []


class TestAMemoryBankRepository:
    """a_memory_bank_repository() provides in-memory repository with save/find."""

    def test_returns_none_by_default(self):
        repo = a_memory_bank_repository()
        result = repo.find_by_id("nonexistent")
        assert result.is_ok is True
        assert result.value is None

    def test_save_and_find_by_id(self):
        agg = a_memory_bank_aggregate()
        repo = a_memory_bank_repository()
        repo.save(agg)
        result = repo.find_by_id(agg.name)
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.name == agg.name

    def test_delete_removes_aggregate(self):
        agg = a_memory_bank_aggregate()
        repo = a_memory_bank_repository()
        repo.save(agg)
        deleted = repo.delete(agg.name)
        assert deleted is True
        result = repo.find_by_id(agg.name)
        assert result.value is None

    def test_delete_returns_false_for_missing(self):
        repo = a_memory_bank_repository()
        deleted = repo.delete("nonexistent")
        assert deleted is False

    def test_list_returns_all_saved(self):
        agg1 = a_memory_bank_aggregate()
        agg2 = a_memory_bank_aggregate(bank=a_memory_bank(name="other_bank"))
        repo = a_memory_bank_repository()
        repo.save(agg1)
        repo.save(agg2)
        result = repo.list()
        assert result.is_ok is True
        assert len(result.value) == 2

    def test_init_with_data(self):
        agg = a_memory_bank_aggregate()
        repo = a_memory_bank_repository(data=[agg])
        result = repo.find_by_id(agg.name)
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.name == agg.name
