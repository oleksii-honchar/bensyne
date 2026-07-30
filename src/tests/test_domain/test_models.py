"""Tests for domain models and exceptions."""

from datetime import datetime, timezone

import pytest

from src.domain.models import NamespaceInfo, InstanceInfo, ToolResponse
from src.domain.exceptions import NamespaceError, InstanceError, ValidationError


class TestNamespaceInfo:
    """Tests for NamespaceInfo dataclass."""

    def test_create_namespace_info_with_all_fields(self):
        """NamespaceInfo can be created with all fields."""
        now = datetime.now(timezone.utc).isoformat()
        info = NamespaceInfo(
            name="obsidian-vault",
            bank="obsidian-vault",
            status="active",
            memory_count=42,
            created_at=now,
            last_accessed=now,
        )

        assert info.name == "obsidian-vault"
        assert info.bank == "obsidian-vault"
        assert info.status == "active"
        assert info.memory_count == 42
        assert info.created_at == now
        assert info.last_accessed == now

    def test_create_default_namespace_info(self):
        """NamespaceInfo can be created with default namespace values."""
        info = NamespaceInfo(
            name="default",
            bank="default",
            status="active",
            memory_count=0,
            created_at="2026-07-30T12:00:00+00:00",
            last_accessed="2026-07-30T12:00:00+00:00",
        )

        assert info.name == "default"
        assert info.bank == "default"
        assert info.status == "active"
        assert info.memory_count == 0

    def test_namespace_info_evicted_status(self):
        """NamespaceInfo can represent an evicted namespace."""
        info = NamespaceInfo(
            name="temp-ns",
            bank="temp-ns",
            status="evicted",
            memory_count=100,
            created_at="2026-07-30T10:00:00+00:00",
            last_accessed="2026-07-30T11:00:00+00:00",
        )

        assert info.status == "evicted"
        assert info.memory_count == 100

    def test_namespace_info_serialization(self):
        """NamespaceInfo can be serialized to dict."""
        info = NamespaceInfo(
            name="test-ns",
            bank="test-ns",
            status="active",
            memory_count=10,
            created_at="2026-07-30T12:00:00+00:00",
            last_accessed="2026-07-30T12:30:00+00:00",
        )

        data = info.to_dict()

        assert data == {
            "name": "test-ns",
            "bank": "test-ns",
            "status": "active",
            "memory_count": 10,
            "created_at": "2026-07-30T12:00:00+00:00",
            "last_accessed": "2026-07-30T12:30:00+00:00",
        }


class TestInstanceInfo:
    """Tests for InstanceInfo dataclass."""

    def test_create_instance_info(self):
        """InstanceInfo can be created with all fields."""
        created_at = 1722326400.0
        last_accessed = 1722326700.0

        info = InstanceInfo(
            namespace="obsidian-vault",
            db_path="/data/mnemosyne/data/banks/obsidian-vault/mnemosyne.db",
            status="active",
            created_at=created_at,
            last_accessed=last_accessed,
        )

        assert info.namespace == "obsidian-vault"
        assert info.db_path == "/data/mnemosyne/data/banks/obsidian-vault/mnemosyne.db"
        assert info.status == "active"
        assert info.created_at == created_at
        assert info.last_accessed == last_accessed

    def test_create_default_instance_info(self):
        """InstanceInfo can be created for default namespace."""
        info = InstanceInfo(
            namespace="default",
            db_path="/data/mnemosyne/data/mnemosyne.db",
            status="active",
            created_at=1722326400.0,
            last_accessed=1722326400.0,
        )

        assert info.namespace == "default"
        assert info.db_path == "/data/mnemosyne/data/mnemosyne.db"

    def test_instance_info_serialization(self):
        """InstanceInfo can be serialized to dict."""
        info = InstanceInfo(
            namespace="test",
            db_path="/data/mnemosyne/data/banks/test/mnemosyne.db",
            status="active",
            created_at=1722326400.0,
            last_accessed=1722326500.0,
        )

        data = info.to_dict()

        assert data == {
            "namespace": "test",
            "db_path": "/data/mnemosyne/data/banks/test/mnemosyne.db",
            "status": "active",
            "created_at": 1722326400.0,
            "last_accessed": 1722326500.0,
        }


class TestToolResponse:
    """Tests for ToolResponse dataclass."""

    def test_tool_response_ok_status(self):
        """ToolResponse can represent a successful operation."""
        response = ToolResponse(
            status="ok",
            data={"result": "success"},
            namespace="default",
        )

        assert response.status == "ok"
        assert response.data == {"result": "success"}
        assert response.namespace == "default"
        assert response.error is None

    def test_tool_response_stored_status(self):
        """ToolResponse can represent a stored memory."""
        response = ToolResponse(
            status="stored",
            data={"memory_id": "abc123"},
            namespace="obsidian-vault",
        )

        assert response.status == "stored"
        assert response.data["memory_id"] == "abc123"
        assert response.namespace == "obsidian-vault"

    def test_tool_response_error_status(self):
        """ToolResponse can represent an error."""
        response = ToolResponse(
            status="error",
            namespace="test-ns",
            error="Namespace not found",
        )

        assert response.status == "error"
        assert response.error == "Namespace not found"
        assert response.data is None

    def test_tool_response_no_data(self):
        """ToolResponse can have no data payload."""
        response = ToolResponse(
            status="ok",
            namespace="default",
        )

        assert response.data is None

    def test_tool_response_serialization(self):
        """ToolResponse can be serialized to dict."""
        response = ToolResponse(
            status="stored",
            data={"memory_id": "xyz789"},
            namespace="test-ns",
        )

        data = response.to_dict()

        assert data == {
            "status": "stored",
            "data": {"memory_id": "xyz789"},
            "namespace": "test-ns",
            "error": None,
        }


class TestNamespaceError:
    """Tests for NamespaceError exception."""

    def test_namespace_error_with_message(self):
        """NamespaceError raises with expected message."""
        with pytest.raises(NamespaceError) as exc_info:
            raise NamespaceError("Namespace 'invalid-ns' not found")

        assert str(exc_info.value) == "Namespace 'invalid-ns' not found"

    def test_namespace_error_is_domain_error(self):
        """NamespaceError is a subclass of Exception."""
        assert issubclass(NamespaceError, Exception)

    def test_namespace_error_not_found_variant(self):
        """NamespaceError can represent not-found scenarios."""
        with pytest.raises(NamespaceError, match="not found"):
            raise NamespaceError("Namespace 'missing' not found")

    def test_namespace_error_invalid_name_variant(self):
        """NamespaceError can represent invalid name scenarios."""
        with pytest.raises(NamespaceError, match="Invalid"):
            raise NamespaceError("Invalid namespace name: 'ns with spaces'")


class TestInstanceError:
    """Tests for InstanceError exception."""

    def test_instance_error_with_message(self):
        """InstanceError raises with expected message."""
        with pytest.raises(InstanceError) as exc_info:
            raise InstanceError("Failed to create instance for namespace 'test'")

        assert str(exc_info.value) == "Failed to create instance for namespace 'test'"

    def test_instance_error_is_domain_error(self):
        """InstanceError is a subclass of Exception."""
        assert issubclass(InstanceError, Exception)

    def test_instance_error_creation_failure_variant(self):
        """InstanceError can represent creation failures."""
        with pytest.raises(InstanceError, match="create"):
            raise InstanceError("Failed to create instance: database locked")

    def test_instance_error_management_failure_variant(self):
        """InstanceError can represent management failures."""
        with pytest.raises(InstanceError, match="evict"):
            raise InstanceError("Failed to evict instance 'old-ns': connection in use")


class TestValidationError:
    """Tests for ValidationError exception."""

    def test_validation_error_with_message(self):
        """ValidationError raises with expected message."""
        with pytest.raises(ValidationError) as exc_info:
            raise ValidationError("Missing required field: 'content'")

        assert str(exc_info.value) == "Missing required field: 'content'"

    def test_validation_error_is_domain_error(self):
        """ValidationError is a subclass of Exception."""
        assert issubclass(ValidationError, Exception)

    def test_validation_error_bad_namespace_name(self):
        """ValidationError can represent bad namespace names."""
        with pytest.raises(ValidationError, match="namespace"):
            raise ValidationError("Invalid namespace name: must be alphanumeric with hyphens")

    def test_validation_error_missing_required_fields(self):
        """ValidationError can represent missing required fields."""
        with pytest.raises(ValidationError, match="required"):
            raise ValidationError("Missing required fields: 'content', 'source'")

    def test_validation_error_empty_content(self):
        """ValidationError can represent empty content."""
        with pytest.raises(ValidationError, match="empty"):
            raise ValidationError("Content cannot be empty")
