"""Repository contract tests — verify in-memory implementations satisfy the domain repository interfaces
and return Result types for all operations."""

from src.domain.aggregates.memory_bank_aggregate import MemoryBankAggregate
from src.domain.entities.memory import Memory
from src.domain.entities.memory_bank import MemoryBank
from src.domain.interfaces import MemoryBankRepository, MemoryRepository
from src.domain.result import Result

from src.tests.test_domain.domain_test_utils import (
    a_memory,
    a_memory_bank,
    a_memory_bank_aggregate,
    a_memory_bank_repository,
    a_memory_repository,
    InMemoryMemoryRepository,
    InMemoryMemoryBankRepository,
)


class TestMemoryRepositoryContract:
    """In-memory MemoryRepository satisfies the MemoryRepository interface and Result contract."""

    def test_implementation_is_instance_of_interface(self):
        repo = a_memory_repository()
        assert isinstance(repo, MemoryRepository)

    def test_save_returns_result_ok_with_memory(self):
        mem = a_memory(id="m1")
        repo = a_memory_repository()
        result = repo.save(mem)
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "m1"

    def test_find_by_id_returns_result_ok_with_memory(self):
        mem = a_memory(id="m1")
        repo = a_memory_repository()
        repo.save(mem)
        result = repo.find_by_id("m1")
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.id == "m1"

    def test_find_by_id_returns_result_ok_with_none_when_not_found(self):
        repo = a_memory_repository()
        result = repo.find_by_id("nonexistent")
        assert result.is_ok is True
        assert result.value is None

    def test_find_by_bank_returns_result_ok_with_list(self):
        mem1 = a_memory(id="m1", source="bank_a")
        mem2 = a_memory(id="m2", source="bank_b")
        repo = a_memory_repository(data=[mem1, mem2])
        result = repo.find_by_bank("bank_a", limit=10)
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 1
        assert result.value[0].id == "m1"

    def test_find_by_bank_returns_result_ok_with_empty_list(self):
        repo = a_memory_repository()
        result = repo.find_by_bank("nonexistent", limit=10)
        assert result.is_ok is True
        assert result.value == []

    def test_delete_returns_result_ok_with_true_when_found(self):
        mem = a_memory(id="m1")
        repo = a_memory_repository(data=[mem])
        result = repo.delete("m1")
        assert result.is_ok is True
        assert result.value is True

    def test_delete_returns_result_ok_with_false_when_not_found(self):
        repo = a_memory_repository()
        result = repo.delete("nonexistent")
        assert result.is_ok is True
        assert result.value is False

    def test_round_trip_save_then_find_by_id(self):
        """Core round-trip: save a memory, then retrieve it by id."""
        mem = a_memory(id="rt1", content="Round trip content")
        repo = a_memory_repository()
        save_result = repo.save(mem)
        assert save_result.is_ok
        find_result = repo.find_by_id("rt1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.content == "Round trip content"

    def test_list_returns_all_saved_entities(self):
        """find_by_bank with no filter returns all saved entities."""
        mem1 = a_memory(id="m1", source="bank_a")
        mem2 = a_memory(id="m2", source="bank_a")
        repo = a_memory_repository(data=[mem1, mem2])
        result = repo.find_by_bank("bank_a", limit=10)
        assert result.is_ok
        assert result.value is not None
        assert len(result.value) == 2

    def test_save_overwrites_existing(self):
        mem1 = a_memory(id="m1", content="First")
        mem2 = a_memory(id="m1", content="Second")
        repo = a_memory_repository()
        repo.save(mem1)
        save_result = repo.save(mem2)
        assert save_result.is_ok
        find_result = repo.find_by_id("m1")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.content == "Second"


class TestMemoryBankRepositoryContract:
    """In-memory MemoryBankRepository satisfies the MemoryBankRepository interface and Result contract."""

    def test_implementation_is_instance_of_interface(self):
        repo = a_memory_bank_repository()
        assert isinstance(repo, MemoryBankRepository)

    def test_save_returns_result_ok(self):
        agg = a_memory_bank_aggregate()
        repo = a_memory_bank_repository()
        result = repo.save(agg)
        assert result.is_ok is True

    def test_find_by_id_returns_result_ok_with_aggregate(self):
        agg = a_memory_bank_aggregate()
        repo = a_memory_bank_repository()
        repo.save(agg)
        result = repo.find_by_id(agg.bank.name)
        assert result.is_ok is True
        assert result.value is not None
        assert result.value.bank.name == agg.bank.name

    def test_find_by_id_returns_result_ok_with_none_when_not_found(self):
        repo = a_memory_bank_repository()
        result = repo.find_by_id("nonexistent")
        assert result.is_ok is True
        assert result.value is None

    def test_list_returns_result_ok_with_all_saved(self):
        agg1 = a_memory_bank_aggregate()
        agg2 = a_memory_bank_aggregate(bank=a_memory_bank(name="other_bank"))
        repo = a_memory_bank_repository()
        repo.save(agg1)
        repo.save(agg2)
        result = repo.list()
        assert result.is_ok is True
        assert result.value is not None
        assert len(result.value) == 2

    def test_list_returns_result_ok_with_empty_list(self):
        repo = a_memory_bank_repository()
        result = repo.list()
        assert result.is_ok is True
        assert result.value == []

    def test_round_trip_save_then_find_by_id(self):
        """Core round-trip: save an aggregate, then retrieve it by bank name."""
        bank = a_memory_bank(name="rt_bank", description="Round trip bank")
        agg = a_memory_bank_aggregate(bank=bank)
        repo = a_memory_bank_repository()
        save_result = repo.save(agg)
        assert save_result.is_ok
        find_result = repo.find_by_id("rt_bank")
        assert find_result.is_ok
        assert find_result.value is not None
        assert find_result.value.bank.name == "rt_bank"
        assert find_result.value.bank.description == "Round trip bank"

    def test_list_returns_all_saved_entities(self):
        """List returns all saved aggregates."""
        agg1 = a_memory_bank_aggregate(bank=a_memory_bank(name="bank1"))
        agg2 = a_memory_bank_aggregate(bank=a_memory_bank(name="bank2"))
        repo = a_memory_bank_repository()
        repo.save(agg1)
        repo.save(agg2)
        result = repo.list()
        assert result.is_ok
        assert result.value is not None
        assert len(result.value) == 2
        names = {a.bank.name for a in result.value}
        assert names == {"bank1", "bank2"}
