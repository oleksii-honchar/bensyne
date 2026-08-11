"""Unit tests for Memory domain entity."""

from datetime import datetime, timedelta

import pytest

from src.domain.entities.memory import Memory, MemoryNotFoundError
from src.domain.result import ErrorWithDetails, Result


class TestMemoryOfValidData:
    """Memory.of accepts valid data and returns Result.ok."""

    def test_of_returns_ok_with_valid_minimal_data(self):
        result = Memory.of({
            "id": "m1",
            "content": "Remember this",
        })
        assert result.is_ok is True
        memory = result.value
        assert memory.id == "m1"
        assert memory.content == "Remember this"
        assert memory.importance == 0.5
        assert memory.source == "conversation"
        assert memory.scope == "working"
        assert memory.updated_at is None
        assert memory.veracity is None
        assert memory.metadata is None

    def test_of_returns_ok_with_all_fields(self):
        now = datetime.now()
        result = Memory.of({
            "id": "m2",
            "content": "Full memory",
            "importance": 0.8,
            "source": "file",
            "scope": "episodic",
            "created_at": now,
            "updated_at": now,
            "veracity": 0.9,
            "metadata": {"key": "value"},
        })
        assert result.is_ok is True
        memory = result.value
        assert memory.id == "m2"
        assert memory.content == "Full memory"
        assert memory.importance == 0.8
        assert memory.source == "file"
        assert memory.scope == "episodic"
        assert memory.created_at == now
        assert memory.updated_at == now
        assert memory.veracity == 0.9
        assert memory.metadata == {"key": "value"}

    def test_of_sets_created_at_when_not_provided(self):
        result = Memory.of({
            "id": "m3",
            "content": "Auto timestamp",
        })
        assert result.is_ok is True
        memory = result.value
        assert memory.created_at is not None
        assert isinstance(memory.created_at, datetime)

    def test_of_returns_frozen_instance(self):
        result = Memory.of({
            "id": "m4",
            "content": "Frozen",
        })
        assert result.is_ok is True
        memory = result.value
        with pytest.raises(Exception):
            memory.content = "mutated"  # type: ignore


class TestMemoryOfRejectsInvalidData:
    """Memory.of rejects invalid data and returns Result.ko."""

    def test_of_rejects_empty_content(self):
        result = Memory.of({
            "id": "m5",
            "content": "",
        })
        assert result.is_ko is True
        assert result.value is None
        assert len(result.errors) > 0
        assert result.errors[0].error_code == "INVALID_MEMORY"

    def test_of_rejects_importance_above_one(self):
        result = Memory.of({
            "id": "m6",
            "content": "test",
            "importance": 1.5,
        })
        assert result.is_ko is True
        assert result.value is None
        assert result.errors[0].error_code == "INVALID_MEMORY"

    def test_of_rejects_importance_below_zero(self):
        result = Memory.of({
            "id": "m7",
            "content": "test",
            "importance": -0.1,
        })
        assert result.is_ko is True
        assert result.value is None
        assert result.errors[0].error_code == "INVALID_MEMORY"

    def test_of_rejects_invalid_scope(self):
        result = Memory.of({
            "id": "m8",
            "content": "test",
            "scope": "invalid_scope",
        })
        assert result.is_ko is True
        assert result.value is None
        assert result.errors[0].error_code == "INVALID_MEMORY"


class TestMemoryUpdate:
    """Memory.update returns new instance with updated_at changed."""

    def test_update_returns_new_instance_with_updated_at(self):
        now = datetime.now()
        original = Memory.of({
            "id": "m9",
            "content": "Original content",
            "importance": 0.5,
        }).value

        # Wait a tiny bit to ensure updated_at differs
        import time
        time.sleep(0.01)

        update_result = original.update(content="New content")
        assert update_result.is_ok is True
        updated = update_result.value

        # New instance
        assert updated is not original
        # Content changed
        assert updated.content == "New content"
        # Updated_at is set and different from created_at
        assert updated.updated_at is not None
        assert updated.updated_at >= now
        # Other fields preserved
        assert updated.id == original.id
        assert updated.importance == original.importance
        assert updated.source == original.source
        assert updated.scope == original.scope
        assert updated.created_at == original.created_at

    def test_update_with_importance_only(self):
        original = Memory.of({
            "id": "m10",
            "content": "Keep content",
            "importance": 0.3,
        }).value

        update_result = original.update(importance=0.9)
        assert update_result.is_ok is True
        updated = update_result.value
        assert updated.importance == 0.9
        assert updated.content == "Keep content"
        assert updated.updated_at is not None

    def test_update_with_both_content_and_importance(self):
        original = Memory.of({
            "id": "m11",
            "content": "Old",
            "importance": 0.2,
        }).value

        update_result = original.update(content="New", importance=0.7)
        assert update_result.is_ok is True
        updated = update_result.value
        assert updated.content == "New"
        assert updated.importance == 0.7
        assert updated.updated_at is not None

    def test_update_preserves_veracity_and_metadata(self):
        original = Memory.of({
            "id": "m12",
            "content": "test",
            "veracity": 0.8,
            "metadata": {"k": "v"},
        }).value

        update_result = original.update(content="updated")
        assert update_result.is_ok is True
        updated = update_result.value
        assert updated.veracity == 0.8
        assert updated.metadata == {"k": "v"}

    def test_update_rejects_invalid_content(self):
        original = Memory.of({
            "id": "m13",
            "content": "test",
        }).value

        update_result = original.update(content="")
        assert update_result.is_ko is True
        assert update_result.errors[0].error_code == "INVALID_MEMORY"

    def test_update_rejects_invalid_importance(self):
        original = Memory.of({
            "id": "m14",
            "content": "test",
        }).value

        update_result = original.update(importance=2.0)
        assert update_result.is_ko is True
        assert update_result.errors[0].error_code == "INVALID_MEMORY"


class TestMemorySuspend:
    """Memory.suspend rejects already-suspended memory."""

    def test_suspend_changes_scope_to_suspended(self):
        original = Memory.of({
            "id": "m15",
            "content": "test",
            "scope": "working",
        }).value

        suspend_result = original.suspend()
        assert suspend_result.is_ok is True
        suspended = suspend_result.value
        assert suspended.scope == "suspended"
        assert suspended.updated_at is not None
        assert suspended is not original

    def test_suspend_rejects_already_suspended(self):
        original = Memory.of({
            "id": "m16",
            "content": "test",
            "scope": "suspended",
        }).value

        suspend_result = original.suspend()
        assert suspend_result.is_ko is True
        assert suspend_result.errors[0].error_code == "MEMORY_ALREADY_SUSPENDED"
        assert suspend_result.errors[0].details["id"] == "m16"

    def test_suspend_from_episodic_scope(self):
        original = Memory.of({
            "id": "m17",
            "content": "test",
            "scope": "episodic",
        }).value

        suspend_result = original.suspend()
        assert suspend_result.is_ok is True
        suspended = suspend_result.value
        assert suspended.scope == "suspended"


class TestMemoryNotFoundError:
    """MemoryNotFoundError domain exception."""

    def test_is_subclass_of_exception(self):
        assert issubclass(MemoryNotFoundError, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(MemoryNotFoundError):
            raise MemoryNotFoundError("Memory not found")

    def test_carries_message(self):
        try:
            raise MemoryNotFoundError("id=m1")
        except MemoryNotFoundError as e:
            assert "id=m1" in str(e)
