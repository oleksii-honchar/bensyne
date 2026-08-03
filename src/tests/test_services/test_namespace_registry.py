"""NamespaceRegistry unit tests — TDD for Task 2."""

from __future__ import annotations

import pytest

from src.services.namespace.registry import NamespaceRegistry, DEFAULT_DESCRIPTIONS


class TestDefaultDescriptions:
    """DEFAULT_DESCRIPTIONS includes hardcoded 'default' namespace."""

    def test_default_descriptions_exists(self) -> None:
        assert DEFAULT_DESCRIPTIONS is not None

    def test_default_descriptions_has_default_namespace(self) -> None:
        assert "default" in DEFAULT_DESCRIPTIONS

    def test_default_descriptions_has_correct_description(self) -> None:
        expected = "Default personal memory — general conversation context, preferences, and facts"
        assert DEFAULT_DESCRIPTIONS["default"] == expected


class TestNamespaceRegistryInit:
    """__init__ copies DEFAULT_DESCRIPTIONS into internal dict."""

    def test_registry_created(self) -> None:
        registry = NamespaceRegistry()
        assert registry is not None

    def test_init_copies_default_descriptions(self) -> None:
        registry = NamespaceRegistry()
        assert registry.get("default") == DEFAULT_DESCRIPTIONS["default"]

    def test_init_creates_independent_copy(self) -> None:
        """Internal dict is independent of DEFAULT_DESCRIPTIONS constant."""
        registry = NamespaceRegistry()
        registry.register("test", "test desc")
        assert "test" not in DEFAULT_DESCRIPTIONS

    def test_init_empty_registry_has_only_defaults(self) -> None:
        registry = NamespaceRegistry()
        expected_names = set(DEFAULT_DESCRIPTIONS.keys())
        actual_names = {name for name in registry.list_namespaces()}
        assert actual_names == expected_names


class TestNamespaceRegistryRegister:
    """register() upserts description (idempotent)."""

    def test_register_new_namespace(self) -> None:
        registry = NamespaceRegistry()
        registry.register("project-alpha", "Project Alpha memories")
        assert registry.get("project-alpha") == "Project Alpha memories"

    def test_register_updates_existing_description(self) -> None:
        registry = NamespaceRegistry()
        registry.register("ns1", "first")
        registry.register("ns1", "second")
        assert registry.get("ns1") == "second"

    def test_register_overwrites_default_description(self) -> None:
        registry = NamespaceRegistry()
        original = registry.get("default")
        registry.register("default", "custom default")
        assert registry.get("default") == "custom default"
        assert original != "custom default"

    def test_register_idempotent_same_values(self) -> None:
        """Calling register multiple times with same values is idempotent."""
        registry = NamespaceRegistry()
        registry.register("ns1", "desc")
        registry.register("ns1", "desc")
        registry.register("ns1", "desc")
        assert registry.get("ns1") == "desc"

    def test_register_multiple_namespaces(self) -> None:
        registry = NamespaceRegistry()
        registry.register("ns1", "desc1")
        registry.register("ns2", "desc2")
        registry.register("ns3", "desc3")
        assert registry.get("ns1") == "desc1"
        assert registry.get("ns2") == "desc2"
        assert registry.get("ns3") == "desc3"


class TestNamespaceRegistryGet:
    """get() returns description or None."""

    def test_get_existing_namespace(self) -> None:
        registry = NamespaceRegistry()
        registry.register("ns1", "test description")
        assert registry.get("ns1") == "test description"

    def test_get_default_namespace(self) -> None:
        registry = NamespaceRegistry()
        assert registry.get("default") is not None
        assert "Default personal memory" in registry.get("default")

    def test_get_nonexistent_namespace_returns_none(self) -> None:
        registry = NamespaceRegistry()
        assert registry.get("nonexistent") is None

    def test_get_empty_string_namespace_returns_none(self) -> None:
        registry = NamespaceRegistry()
        assert registry.get("") is None


class TestNamespaceRegistryListNamespaces:
    """list_namespaces() returns all registered namespace names."""

    def test_list_returns_defaults(self) -> None:
        registry = NamespaceRegistry()
        namespaces = registry.list_namespaces()
        assert "default" in namespaces

    def test_list_returns_registered_namespaces(self) -> None:
        registry = NamespaceRegistry()
        registry.register("ns1", "desc1")
        registry.register("ns2", "desc2")
        namespaces = registry.list_namespaces()
        assert "default" in namespaces
        assert "ns1" in namespaces
        assert "ns2" in namespaces

    def test_list_returns_all_names(self) -> None:
        registry = NamespaceRegistry()
        count_before = len(registry.list_namespaces())
        registry.register("new-ns", "new description")
        count_after = len(registry.list_namespaces())
        assert count_after == count_before + 1
