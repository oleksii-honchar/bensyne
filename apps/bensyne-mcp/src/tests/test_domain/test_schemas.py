"""Unit tests for Pydantic validation schemas.

Covers MemorySchema, MemoryBankSchema, and API request/response models.
"""

import pytest
from pydantic import ValidationError
from src.domain.models.memory_model import MemorySchema

from src.domain.models.memory_bank_model import MemoryBankSchema
from src.infrastructure.schemas.api_models import (
    MemoryOperationRequest,
    MemoryOperationResponse,
    MemorySearchRequest,
    MemorySearchResponse,
)


class TestMemorySchemaValidImportance:
    """MemorySchema accepts importance within 0.0-1.0 range."""

    def test_accepts_importance_zero(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
                "importance": 0.0,
            }
        )
        assert schema.importance == 0.0

    def test_accepts_importance_one(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
                "importance": 1.0,
            }
        )
        assert schema.importance == 1.0

    def test_accepts_importance_half(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
                "importance": 0.5,
            }
        )
        assert schema.importance == 0.5

    def test_defaults_importance_to_half(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
            }
        )
        assert schema.importance == 0.5


class TestMemorySchemaRejectsInvalidImportance:
    """MemorySchema rejects importance outside 0.0-1.0 range."""

    def test_rejects_importance_negative(self):
        with pytest.raises(ValidationError):
            MemorySchema.model_validate(
                {
                    "id": "m1",
                    "content": "test",
                    "importance": -0.1,
                }
            )

    def test_rejects_importance_above_one(self):
        with pytest.raises(ValidationError):
            MemorySchema.model_validate(
                {
                    "id": "m1",
                    "content": "test",
                    "importance": 1.1,
                }
            )

    def test_rejects_importance_two(self):
        with pytest.raises(ValidationError):
            MemorySchema.model_validate(
                {
                    "id": "m1",
                    "content": "test",
                    "importance": 2.0,
                }
            )


class TestMemorySchemaValidScope:
    """MemorySchema accepts valid scope values."""

    @pytest.mark.parametrize("scope", ["working", "episodic", "semantic", "suspended"])
    def test_accepts_valid_scope(self, scope):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
                "scope": scope,
            }
        )
        assert schema.scope == scope

    def test_defaults_scope_to_working(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
            }
        )
        assert schema.scope == "working"


class TestMemorySchemaRejectsInvalidScope:
    """MemorySchema rejects scope not in working/episodic/semantic/suspended."""

    @pytest.mark.parametrize("scope", ["invalid", "long_term", "", "WORKING"])
    def test_rejects_invalid_scope(self, scope):
        with pytest.raises(ValidationError):
            MemorySchema.model_validate(
                {
                    "id": "m1",
                    "content": "test",
                    "scope": scope,
                }
            )


class TestMemorySchemaContentValidation:
    """MemorySchema validates content field."""

    def test_rejects_empty_content(self):
        with pytest.raises(ValidationError):
            MemorySchema.model_validate(
                {
                    "id": "m1",
                    "content": "",
                }
            )

    def test_accepts_non_empty_content(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "Hello world",
            }
        )
        assert schema.content == "Hello world"


class TestMemorySchemaDefaults:
    """MemorySchema applies default values correctly."""

    def test_defaults_source_to_conversation(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
            }
        )
        assert schema.source == "conversation"

    def test_defaults_scope_to_working(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
            }
        )
        assert schema.scope == "working"

    def test_defaults_importance_to_half(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
            }
        )
        assert schema.importance == 0.5

    def test_created_at_is_set(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
            }
        )
        assert schema.created_at is not None

    def test_updated_at_defaults_to_none(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
            }
        )
        assert schema.updated_at is None

    def test_veracity_defaults_to_none(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
            }
        )
        assert schema.veracity is None

    def test_metadata_defaults_to_none(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
            }
        )
        assert schema.metadata is None


class TestMemorySchemaVeracityValidation:
    """MemorySchema validates optional veracity field."""

    def test_accepts_veracity_in_range(self):
        schema = MemorySchema.model_validate(
            {
                "id": "m1",
                "content": "test",
                "veracity": 0.75,
            }
        )
        assert schema.veracity == 0.75

    def test_rejects_veracity_above_one(self):
        with pytest.raises(ValidationError):
            MemorySchema.model_validate(
                {
                    "id": "m1",
                    "content": "test",
                    "veracity": 1.5,
                }
            )

    def test_rejects_veracity_negative(self):
        with pytest.raises(ValidationError):
            MemorySchema.model_validate(
                {
                    "id": "m1",
                    "content": "test",
                    "veracity": -0.1,
                }
            )


class TestMemoryBankSchemaValidName:
    """MemoryBankSchema accepts valid names."""

    def test_accepts_alphanumeric_name(self):
        schema = MemoryBankSchema.model_validate(
            {
                "name": "mybank123",
                "description": "A test bank",
            }
        )
        assert schema.name == "mybank123"

    def test_accepts_name_with_underscores(self):
        schema = MemoryBankSchema.model_validate(
            {
                "name": "my_bank_name",
                "description": "A test bank",
            }
        )
        assert schema.name == "my_bank_name"

    def test_accepts_single_char_name(self):
        schema = MemoryBankSchema.model_validate(
            {
                "name": "a",
                "description": "A test bank",
            }
        )
        assert schema.name == "a"

    def test_accepts_name_with_numbers(self):
        schema = MemoryBankSchema.model_validate(
            {
                "name": "bank2",
                "description": "A test bank",
            }
        )
        assert schema.name == "bank2"

    def test_accepts_long_name_up_to_100(self):
        long_name = "a" * 100
        schema = MemoryBankSchema.model_validate(
            {
                "name": long_name,
                "description": "A test bank",
            }
        )
        assert schema.name == long_name


class TestMemoryBankSchemaRejectsInvalidName:
    """MemoryBankSchema rejects names with special characters or invalid format."""

    @pytest.mark.parametrize(
        "name",
        [
            "my-bank",  # hyphen
            "my bank",  # space
            "my@bank",  # special char
            "my.bank",  # dot
            "my/bank",  # slash
            "my!bank",  # exclamation
        ],
    )
    def test_rejects_name_with_special_characters(self, name):
        with pytest.raises(ValidationError):
            MemoryBankSchema.model_validate(
                {
                    "name": name,
                    "description": "A test bank",
                }
            )

    def test_rejects_empty_name(self):
        with pytest.raises(ValidationError):
            MemoryBankSchema.model_validate(
                {
                    "name": "",
                    "description": "A test bank",
                }
            )

    def test_rejects_name_over_100_chars(self):
        long_name = "a" * 101
        with pytest.raises(ValidationError):
            MemoryBankSchema.model_validate(
                {
                    "name": long_name,
                    "description": "A test bank",
                }
            )


class TestMemoryBankSchemaDefaults:
    """MemoryBankSchema applies default values correctly."""

    def test_defaults_status_to_registered(self):
        schema = MemoryBankSchema.model_validate(
            {
                "name": "mybank",
                "description": "A test bank",
            }
        )
        assert schema.status == "registered"

    def test_rejects_empty_description(self):
        with pytest.raises(ValidationError):
            MemoryBankSchema.model_validate(
                {
                    "name": "mybank",
                    "description": "",
                }
            )


class TestMemoryOperationRequest:
    """MemoryOperationRequest serialization and deserialization."""

    def test_create_with_all_fields(self):
        req = MemoryOperationRequest(
            content="Remember this",
            importance=0.8,
            source="file",
            scope="episodic",
            memory_bank="my_bank",
            metadata={"key": "value"},
        )
        assert req.content == "Remember this"
        assert req.importance == 0.8
        assert req.source == "file"
        assert req.scope == "episodic"
        assert req.memory_bank == "my_bank"
        assert req.metadata == {"key": "value"}

    def test_create_with_defaults(self):
        req = MemoryOperationRequest(content="test")
        assert req.content == "test"
        assert req.importance == 0.5
        assert req.source == "conversation"
        assert req.scope == "working"
        assert req.memory_bank == "default"
        assert req.metadata is None

    def test_serialize_to_dict(self):
        req = MemoryOperationRequest(
            content="test",
            importance=0.7,
            memory_bank="my_bank",
        )
        data = req.model_dump()
        assert data["content"] == "test"
        assert data["importance"] == 0.7
        assert data["memory_bank"] == "my_bank"

    def test_deserialize_from_dict(self):
        data = {
            "content": "test",
            "importance": 0.6,
            "source": "api",
            "scope": "semantic",
            "memory_bank": "test_bank",
        }
        req = MemoryOperationRequest.model_validate(data)
        assert req.content == "test"
        assert req.importance == 0.6
        assert req.source == "api"
        assert req.scope == "semantic"
        assert req.memory_bank == "test_bank"

    def test_serialize_deserialize_roundtrip(self):
        original = MemoryOperationRequest(
            content="roundtrip test",
            importance=0.9,
            source="test",
            scope="episodic",
            memory_bank="rt_bank",
            metadata={"x": 1},
        )
        data = original.model_dump()
        restored = MemoryOperationRequest.model_validate(data)
        assert restored.content == original.content
        assert restored.importance == original.importance
        assert restored.source == original.source
        assert restored.scope == original.scope
        assert restored.memory_bank == original.memory_bank
        assert restored.metadata == original.metadata


class TestMemoryOperationResponse:
    """MemoryOperationResponse serialization and deserialization."""

    def test_create_success_response(self):
        resp = MemoryOperationResponse(
            status="stored",
            memory_id="mem_123",
            memory_bank="my_bank",
        )
        assert resp.status == "stored"
        assert resp.memory_id == "mem_123"
        assert resp.memory_bank == "my_bank"
        assert resp.error is None

    def test_create_error_response(self):
        resp = MemoryOperationResponse(
            status="error",
            memory_bank="my_bank",
            error="Something went wrong",
        )
        assert resp.status == "error"
        assert resp.error == "Something went wrong"
        assert resp.memory_id is None

    def test_defaults_memory_bank(self):
        resp = MemoryOperationResponse(status="ok")
        assert resp.memory_bank == "default"

    def test_serialize_to_dict(self):
        resp = MemoryOperationResponse(
            status="stored",
            memory_id="mem_42",
            memory_bank="bank1",
        )
        data = resp.model_dump()
        assert data["status"] == "stored"
        assert data["memory_id"] == "mem_42"
        assert data["memory_bank"] == "bank1"

    def test_deserialize_from_dict(self):
        data = {
            "status": "stored",
            "memory_id": "mem_99",
            "memory_bank": "bank2",
        }
        resp = MemoryOperationResponse.model_validate(data)
        assert resp.status == "stored"
        assert resp.memory_id == "mem_99"
        assert resp.memory_bank == "bank2"

    def test_serialize_deserialize_roundtrip(self):
        original = MemoryOperationResponse(
            status="stored",
            memory_id="mem_rt",
            memory_bank="rt_bank",
        )
        data = original.model_dump()
        restored = MemoryOperationResponse.model_validate(data)
        assert restored.status == original.status
        assert restored.memory_id == original.memory_id
        assert restored.memory_bank == original.memory_bank
        assert restored.error == original.error


class TestMemorySearchRequest:
    """MemorySearchRequest serialization and deserialization."""

    def test_create_with_all_fields(self):
        req = MemorySearchRequest(
            query="remember this",
            limit=10,
            memory_bank="my_bank",
        )
        assert req.query == "remember this"
        assert req.limit == 10
        assert req.memory_bank == "my_bank"

    def test_defaults_limit_and_bank(self):
        req = MemorySearchRequest(query="test")
        assert req.query == "test"
        assert req.limit == 5
        assert req.memory_bank == "default"

    def test_serialize_to_dict(self):
        req = MemorySearchRequest(query="search", limit=20, memory_bank="bank1")
        data = req.model_dump()
        assert data["query"] == "search"
        assert data["limit"] == 20
        assert data["memory_bank"] == "bank1"

    def test_deserialize_from_dict(self):
        data = {"query": "find me", "limit": 3, "memory_bank": "bank3"}
        req = MemorySearchRequest.model_validate(data)
        assert req.query == "find me"
        assert req.limit == 3
        assert req.memory_bank == "bank3"

    def test_serialize_deserialize_roundtrip(self):
        original = MemorySearchRequest(
            query="roundtrip",
            limit=15,
            memory_bank="rt_bank",
        )
        data = original.model_dump()
        restored = MemorySearchRequest.model_validate(data)
        assert restored.query == original.query
        assert restored.limit == original.limit
        assert restored.memory_bank == original.memory_bank


class TestMemorySearchResponse:
    """MemorySearchResponse serialization and deserialization."""

    def test_create_with_results(self):
        results = [{"id": "m1", "content": "result one"}]
        resp = MemorySearchResponse(
            results=results,
            memory_bank="my_bank",
            total_count=1,
        )
        assert resp.results == results
        assert resp.memory_bank == "my_bank"
        assert resp.total_count == 1

    def test_defaults_total_count(self):
        resp = MemorySearchResponse(
            results=[],
            memory_bank="bank1",
        )
        assert resp.total_count == 0

    def test_serialize_to_dict(self):
        resp = MemorySearchResponse(
            results=[{"id": "m1"}],
            memory_bank="bank1",
            total_count=1,
        )
        data = resp.model_dump()
        assert data["results"] == [{"id": "m1"}]
        assert data["memory_bank"] == "bank1"
        assert data["total_count"] == 1

    def test_deserialize_from_dict(self):
        data = {
            "results": [{"id": "m2", "content": "found"}],
            "memory_bank": "bank2",
            "total_count": 1,
        }
        resp = MemorySearchResponse.model_validate(data)
        assert resp.results == [{"id": "m2", "content": "found"}]
        assert resp.memory_bank == "bank2"
        assert resp.total_count == 1

    def test_serialize_deserialize_roundtrip(self):
        original = MemorySearchResponse(
            results=[{"id": "m_rt", "content": "rt result"}],
            memory_bank="rt_bank",
            total_count=1,
        )
        data = original.model_dump()
        restored = MemorySearchResponse.model_validate(data)
        assert restored.results == original.results
        assert restored.memory_bank == original.memory_bank
        assert restored.total_count == original.total_count
