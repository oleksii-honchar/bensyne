"""Tests for the FileProps caller-facing structural TypedDict (D23, spec §5).

FileProps is structural typing for callers — zero runtime cost. The single
runtime validation source is the Pydantic ``FileSchema``. This test pins the
exact key set: the 13 updatable FileSchema fields, and NONE of the
identity / lifecycle / system-managed fields.
"""

from __future__ import annotations

from src.domain.models.file_props import FileProps

# The 13 updatable FileSchema fields (spec §5 / D23).
EXPECTED_KEYS = {
    "path",
    "source_type",
    "file_role",
    "hash",
    "file_type",
    "size",
    "language",
    "aggregated_keywords",
    "aggregated_tags",
    "summary",
    "total_chunks",
    "average_importance",
    "metadata",
}

# Deliberately NOT props (D23 / spec §5):
#   id — identity; status — method-driven lifecycle; created_at/updated_at — system.
FORBIDDEN_KEYS = {"id", "status", "created_at", "updated_at"}


class TestFilePropsKeySet:
    """FileProps mirrors exactly the updatable FileSchema fields."""

    def test_file_props_contains_exactly_the_thirteen_updatable_keys(self) -> None:
        assert set(FileProps.__annotations__) == EXPECTED_KEYS

    def test_file_props_excludes_identity_lifecycle_and_timestamp_keys(self) -> None:
        assert FORBIDDEN_KEYS.isdisjoint(FileProps.__annotations__)
        # id / status / created_at / updated_at must never appear.
        for key in FORBIDDEN_KEYS:
            assert key not in FileProps.__annotations__

    def test_file_props_is_total_false_partial_typed_dict(self) -> None:
        # total=False: every key is optional, none required.
        assert FileProps.__required_keys__ == frozenset()
        assert FileProps.__optional_keys__ == frozenset(EXPECTED_KEYS)
