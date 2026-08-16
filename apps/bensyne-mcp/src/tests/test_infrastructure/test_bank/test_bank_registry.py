"""MemoryBankRegistry unit tests."""

from __future__ import annotations

import pytest

from src.infrastructure.bank.registry import MemoryBankRegistry, DEFAULT_DESCRIPTIONS


class TestDefaultDescriptions:
    """DEFAULT_DESCRIPTIONS includes hardcoded 'default' memory bank."""

    def test_default_descriptions_exists(self) -> None:
        assert DEFAULT_DESCRIPTIONS is not None

    def test_default_descriptions_has_default_bank(self) -> None:
        assert "default" in DEFAULT_DESCRIPTIONS

    def test_default_descriptions_has_correct_description(self) -> None:
        expected = "Default personal memory — general conversation context, preferences, and facts"
        assert DEFAULT_DESCRIPTIONS["default"] == expected


class TestMemoryBankRegistryInit:
    """__init__ copies DEFAULT_DESCRIPTIONS into internal dict."""

    def test_registry_created(self) -> None:
        registry = MemoryBankRegistry()
        assert registry is not None

    def test_init_copies_default_descriptions(self) -> None:
        registry = MemoryBankRegistry()
        assert registry.get("default") == DEFAULT_DESCRIPTIONS["default"]

    def test_init_creates_independent_copy(self) -> None:
        """Internal dict is independent of DEFAULT_DESCRIPTIONS constant."""
        registry = MemoryBankRegistry()
        registry.register("test", "test desc")
        assert "test" not in DEFAULT_DESCRIPTIONS

    def test_init_empty_registry_has_only_defaults(self) -> None:
        registry = MemoryBankRegistry()
        expected_names = set(DEFAULT_DESCRIPTIONS.keys())
        actual_names = {name for name in registry.list_banks()}
        assert actual_names == expected_names


class TestMemoryBankRegistryRegister:
    """register() upserts description (idempotent)."""

    def test_register_new_bank(self) -> None:
        registry = MemoryBankRegistry()
        registry.register("project-alpha", "Project Alpha memories")
        assert registry.get("project-alpha") == "Project Alpha memories"

    def test_register_updates_existing_description(self) -> None:
        registry = MemoryBankRegistry()
        registry.register("ns1", "first")
        registry.register("ns1", "second")
        assert registry.get("ns1") == "second"

    def test_register_overwrites_default_description(self) -> None:
        registry = MemoryBankRegistry()
        original = registry.get("default")
        registry.register("default", "custom default")
        assert registry.get("default") == "custom default"
        assert original != "custom default"

    def test_register_idempotent_same_values(self) -> None:
        """Calling register multiple times with same values is idempotent."""
        registry = MemoryBankRegistry()
        registry.register("ns1", "desc")
        registry.register("ns1", "desc")
        registry.register("ns1", "desc")
        assert registry.get("ns1") == "desc"

    def test_register_multiple_banks(self) -> None:
        registry = MemoryBankRegistry()
        registry.register("ns1", "desc1")
        registry.register("ns2", "desc2")
        registry.register("ns3", "desc3")
        assert registry.get("ns1") == "desc1"
        assert registry.get("ns2") == "desc2"
        assert registry.get("ns3") == "desc3"


class TestMemoryBankRegistryGet:
    """get() returns description or None."""

    def test_get_existing_bank(self) -> None:
        registry = MemoryBankRegistry()
        registry.register("ns1", "test description")
        assert registry.get("ns1") == "test description"

    def test_get_default_bank(self) -> None:
        registry = MemoryBankRegistry()
        assert registry.get("default") is not None
        assert "Default personal memory" in registry.get("default")

    def test_get_nonexistent_bank_returns_none(self) -> None:
        registry = MemoryBankRegistry()
        assert registry.get("nonexistent") is None

    def test_get_empty_string_bank_returns_none(self) -> None:
        registry = MemoryBankRegistry()
        assert registry.get("") is None


class TestMemoryBankRegistryListBanks:
    """list_banks() returns all registered memory bank names."""

    def test_list_returns_defaults(self) -> None:
        registry = MemoryBankRegistry()
        banks = registry.list_banks()
        assert "default" in banks

    def test_list_returns_registered_banks(self) -> None:
        registry = MemoryBankRegistry()
        registry.register("ns1", "desc1")
        registry.register("ns2", "desc2")
        banks = registry.list_banks()
        assert "default" in banks
        assert "ns1" in banks
        assert "ns2" in banks

    def test_list_returns_all_names(self) -> None:
        registry = MemoryBankRegistry()
        count_before = len(registry.list_banks())
        registry.register("new-ns", "new description")
        count_after = len(registry.list_banks())
        assert count_after == count_before + 1
