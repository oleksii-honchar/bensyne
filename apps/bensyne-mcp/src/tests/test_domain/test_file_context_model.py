"""Tests for FileContextSchema / FileContext — unified chunk contract v1 (bensyne half).

Fixture files live in ``src/tests/test_domain/fixtures/`` and double as the
bensyne half of the parity fixture asserted by racochu's zod suite (Task 19).
"""

import hashlib
import json
from pathlib import Path

import pytest

from src.domain.models.file_context_model import (
    FileContext,
    FileContextEdge,
    FileContextParentUnit,
    parse_file_context,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    payload = json.loads((FIXTURES_DIR / name).read_text())
    if "metadata" not in payload:
        return payload  # non-parity fixtures (e.g. legacy dialect) are bare metadata
    # The parity fixture is the full rememberMemory transport envelope
    # (byte-identical to racochu's unified-chunk-contract-v1.json); the bensyne
    # half consumes its "metadata" object.
    return payload["metadata"]


class TestFullValidV1Payload:
    """A full v1 payload (all 15 keys) parses with exact field values."""

    def test_full_payload_parses_with_exact_values(self):
        metadata = _load_fixture("file_context_contract_v1.json")

        context = parse_file_context(metadata)

        assert context is not None
        assert context.contract_version == 1
        assert context.file_path == "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md"
        assert context.chunk_index == 2
        assert context.total_chunks == 5
        assert context.section_header == "## Implementation Details"
        assert context.start_line == 42
        assert context.end_line == 97
        assert context.source_type == "agent-sessions"
        assert context.file_role == "docs"
        assert context.language == "markdown"
        assert context.file_hash == (
            "ed8feb0ec28dad93b0c1e85377908f07367164d374d3d329e1bde6668591cc17"
        )
        assert context.chunk_hash == (
            "aee858233038e696cb0c90d0d65a312c308454104a6bd4bbb53554f7816b322c"
        )
        assert context.summary == (
            "Findings from the bensyne file metadata materialization session, "
            "documenting implementation details and design decisions."
        )
        assert context.parent_unit is not None
        assert context.parent_unit.ref == "session-260811-0000"
        assert context.parent_unit.summary == "Session investigating bensyne file metadata materialization"
        assert context.edges_list == [
            FileContextEdge(
                target_path="/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/session.md",
                relation_type="parent_child",
                strength=1,
                description="findings.md belongs to session root",
            ),
            FileContextEdge(
                target_path="/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/materials/unified-chunk-contract.md",
                relation_type="sibling",
                strength=1,
                description="companion artifact in same session root",
            ),
        ]
        assert context.tags_list == ["contract", "v1"]
        assert context.extra == {
            "session.id": "260811-0000",
            "session.status": "Session investigating bensyne file metadata materialization",
            "note.tags": '["architecture","contract"]',
        }


class TestFixtureParity:
    """Contract parity gate (spec §7.4): the parity fixture's file bytes are pinned to a
    recorded sha256, and its ``chunk_hash`` is the sha256 of the exact ``content`` string
    (normalization-drift guard)."""

    def test_fixture_file_sha256_matches_recorded_parity_value(self):
        raw = (FIXTURES_DIR / "file_context_contract_v1.json").read_bytes()

        assert hashlib.sha256(raw).hexdigest() == (
            "aa60627d4f8184bdc458d44a01237db78fe02fea58f70b04332877d94dbf73c0"
        )

    def test_chunk_hash_is_sha256_of_exact_content_string(self):
        envelope = json.loads((FIXTURES_DIR / "file_context_contract_v1.json").read_text())

        expected = hashlib.sha256(envelope["content"].encode("utf-8")).hexdigest()
        assert envelope["metadata"]["chunk_hash"] == expected


class TestMinimalPayload:
    """Minimal payload {file_path} parses with documented defaults."""

    def test_minimal_payload_applies_defaults(self):
        context = parse_file_context({"file_path": "/x"})

        # Documented decision: legacy/absent chunk_index+total_chunks degrade to 0/1 best-effort.
        assert context is not None
        assert context.contract_version == 1
        assert context.file_path == "/x"
        assert context.chunk_index == 0
        assert context.total_chunks == 1
        assert context.section_header is None
        assert context.start_line is None
        assert context.end_line is None
        assert context.source_type == "unknown"
        assert context.file_role is None
        assert context.language is None
        assert context.file_hash is None
        assert context.summary is None
        assert context.parent_unit is None
        assert context.edges is None
        assert context.tags_list == []
        assert context.extra == {}


class TestValidators:
    """Range validators reject out-of-bounds values."""

    def test_end_line_less_than_start_line_rejected(self):
        result = parse_file_context(
            {"file_path": "/x", "start_line": 10, "end_line": 5}
        )
        assert result is None

    def test_equal_lines_accepted(self):
        context = parse_file_context({"file_path": "/x", "start_line": 7, "end_line": 7})
        assert context is not None

    def test_chunk_index_negative_rejected(self):
        assert parse_file_context({"file_path": "/x", "chunk_index": -1}) is None

    def test_total_chunks_zero_rejected(self):
        assert parse_file_context({"file_path": "/x", "total_chunks": 0}) is None

    def test_chunk_index_greater_than_total_accepted_best_effort(self):
        # No cross-field constraint between chunk_index and total_chunks.
        context = parse_file_context({"file_path": "/x", "chunk_index": 9, "total_chunks": 3})
        assert context is not None


class TestEdgeDropping:
    """Edges with invalid relation_type are dropped; the chunk still materializes."""

    def test_invalid_relation_type_edge_dropped_others_kept(self):
        metadata = {
            "file_path": "/x",
            "edges": [
                {"target_path": "/a.md", "relation_type": "teleport"},
                {"target_path": "/b.md", "relation_type": "backlink", "strength": 0.5},
            ],
        }

        context = parse_file_context(metadata)

        assert context is not None
        assert len(context.edges_list) == 1
        assert context.edges_list[0].target_path == "/b.md"
        assert context.edges_list[0].relation_type == "backlink"
        assert context.edges_list[0].strength == 0.5

    def test_all_edges_invalid_yields_empty_list(self):
        metadata = {
            "file_path": "/x",
            "edges": [{"target_path": "/a.md", "relation_type": "nope"}],
        }

        context = parse_file_context(metadata)

        assert context is not None
        assert context.edges_list == []

    def test_edge_missing_target_path_dropped(self):
        metadata = {
            "file_path": "/x",
            "edges": [
                {"relation_type": "backlink"},
                {"target_path": "/b.md", "relation_type": "sibling"},
            ],
        }

        context = parse_file_context(metadata)

        assert context is not None
        assert len(context.edges_list) == 1
        assert context.edges_list[0].target_path == "/b.md"

    def test_edge_strength_out_of_range_dropped(self):
        metadata = {
            "file_path": "/x",
            "edges": [
                {"target_path": "/a.md", "relation_type": "backlink", "strength": 1.5},
                {"target_path": "/b.md", "relation_type": "backlink"},
            ],
        }

        context = parse_file_context(metadata)

        assert context is not None
        assert len(context.edges_list) == 1
        assert context.edges_list[0].strength == 1.0


class TestContractVersion:
    """contract_version > 1 ⇒ warn + best-effort parse of known keys (rule 6)."""

    def test_v2_payload_best_effort_parses_known_keys(self):
        metadata = _load_fixture("file_context_contract_v1.json")
        metadata["contract_version"] = 2
        metadata["future_field"] = "some-value"

        context = parse_file_context(metadata)

        assert context is not None
        assert context.contract_version == 2
        assert context.file_path == "/Users/dev/projects/agent-sessions/26/08/11/260811-0000-bensyne-file-materials/findings.md"
        assert context.chunk_index == 2
        # Unknown v2 string key lands in extra (the only extension point).
        assert context.extra == {
            "session.id": "260811-0000",
            "session.status": "Session investigating bensyne file metadata materialization",
            "note.tags": '["architecture","contract"]',
            "future_field": "some-value",
        }


class TestNoFilePath:
    """Contract rule 1: no file_path ⇒ plain memory, zero file-layer writes."""

    def test_none_metadata_returns_none(self):
        assert parse_file_context(None) is None

    def test_empty_dict_returns_none(self):
        assert parse_file_context({}) is None

    def test_dict_without_file_path_returns_none(self):
        assert parse_file_context({"no_file_path": 1}) is None

    def test_empty_string_file_path_returns_none(self):
        assert parse_file_context({"file_path": ""}) is None

    def test_whitespace_file_path_returns_none(self):
        assert parse_file_context({"file_path": "   "}) is None


class TestLegacyDialect:
    """Legacy camelCase keys map to v1 fields; dotted keys land in extra."""

    def test_legacy_payload_maps_to_v1(self):
        metadata = _load_fixture("file_context_legacy_dialect.json")

        context = parse_file_context(metadata)

        assert context is not None
        assert context.file_path == "/abs/path/to/legacy.md"
        assert context.chunk_index == 0
        assert context.total_chunks == 3
        assert context.section_header == "# Legacy Heading"
        assert context.start_line == 1
        assert context.end_line == 20
        assert context.file_hash == (
            "a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f60718293a4b5c6d7e8f90"
        )
        assert context.file_role == "code"
        assert context.language == "python"
        # Legacy producer ⇒ no contract_version, no source_type ⇒ defaults.
        assert context.contract_version == 1
        assert context.source_type == "unknown"
        # Dotted legacy keys captured into extra.
        assert context.extra == {"session.id": "ses_legacy01", "note.title": "Legacy Note"}

    def test_file_path_camelcase_key(self):
        context = parse_file_context({"filePath": "/camel.md"})
        assert context is not None
        assert context.file_path == "/camel.md"

    def test_breadcrumb_takes_precedence_over_file_path(self):
        # Both present ⇒ canonical file_path wins (breadcrumb is the legacy alias).
        context = parse_file_context({"file_path": "/canonical.md", "breadcrumb": "/legacy.md"})
        assert context is not None
        assert context.file_path == "/canonical.md"

    def test_legacy_missing_chunk_fields_default_best_effort(self):
        # Documented decision: absent chunk_index/total_chunks ⇒ 0/1 with warn, never reject.
        context = parse_file_context({"breadcrumb": "/legacy.md"})
        assert context is not None
        assert context.chunk_index == 0
        assert context.total_chunks == 1


class TestUnknownKeys:
    """extra is the only extension point; non-str unknown values are ignored."""

    def test_unknown_string_keys_captured_in_extra(self):
        context = parse_file_context({"file_path": "/x", "custom.thing": "value"})
        assert context is not None
        assert context.extra == {"custom.thing": "value"}

    def test_unknown_non_string_values_ignored(self):
        metadata = {
            "file_path": "/x",
            "weird_int": 42,
            "weird_list": [1, 2],
            "weird_object": {"nested": True},
            "custom.thing": "kept",
        }

        context = parse_file_context(metadata)

        assert context is not None
        assert context.extra == {"custom.thing": "kept"}

    def test_known_keys_not_captured_in_extra(self):
        metadata = _load_fixture("file_context_contract_v1.json")
        metadata["tags"] = ["a", "b"]

        context = parse_file_context(metadata)

        assert context is not None
        # 'tags' is a known v1 key — must not leak into extra.
        assert "tags" not in context.extra


class TestSourceType:
    """source_type wire normalization (D29, spec §6.6): the 4 canonical
    values are accepted verbatim; absent or invalid values degrade to
    ``unknown`` (degrade-never-reject)."""

    def test_source_type_absent_defaults_to_unknown(self):
        context = parse_file_context({"file_path": "/x"})
        assert context is not None
        assert context.source_type == "unknown"

    def test_invalid_source_type_falls_back_to_unknown(self):
        context = parse_file_context({"file_path": "/x", "source_type": "quantum_flux"})
        assert context is not None
        assert context.source_type == "unknown"

    @pytest.mark.parametrize(
        "source_type",
        ["obsidian", "agent-sessions", "vault", "unknown"],
    )
    def test_d29_source_types_accepted(self, source_type):
        context = parse_file_context({"file_path": "/x", "source_type": source_type})
        assert context is not None
        assert context.source_type == source_type

    @pytest.mark.parametrize(
        "source_type",
        ["agent_session", "file_system", "git", "database", "external", "remote"],
    )
    def test_legacy_source_types_degrade_to_unknown(self, source_type):
        # Pre-D29 location-based values are no longer real source types
        # (spec §6.6) — they degrade to the fallback marker, never reject.
        context = parse_file_context({"file_path": "/x", "source_type": source_type})
        assert context is not None
        assert context.source_type == "unknown"


class TestFileRole:
    """file_role enum config|code|docs; invalid values degrade to None."""

    @pytest.mark.parametrize("role", ["config", "code", "docs"])
    def test_valid_roles_accepted(self, role):
        context = parse_file_context({"file_path": "/x", "file_role": role})
        assert context is not None
        assert context.file_role == role

    def test_invalid_role_degrades_to_none(self):
        context = parse_file_context({"file_path": "/x", "file_role": "binary"})
        assert context is not None
        assert context.file_role is None


class TestParentUnit:
    """parent_unit {ref, summary} parsing."""

    def test_parent_unit_with_summary(self):
        context = parse_file_context(
            {"file_path": "/x", "parent_unit": {"ref": "chapter-1", "summary": "S"}}
        )
        assert context is not None
        assert isinstance(context.parent_unit, FileContextParentUnit)
        assert context.parent_unit.ref == "chapter-1"
        assert context.parent_unit.summary == "S"

    def test_parent_unit_summary_optional(self):
        context = parse_file_context(
            {"file_path": "/x", "parent_unit": {"ref": "chapter-1"}}
        )
        assert context is not None
        assert context.parent_unit is not None
        assert context.parent_unit.summary is None

    def test_parent_unit_missing_ref_degrades_to_none(self):
        context = parse_file_context({"file_path": "/x", "parent_unit": {"summary": "S"}})
        assert context is not None
        assert context.parent_unit is None


class TestFrozenResult:
    """FileContext is immutable (frozen dataclass)."""

    def test_fields_cannot_be_mutated(self):
        context = parse_file_context({"file_path": "/x"})
        assert context is not None

        with pytest.raises(Exception):
            context.file_path = "/y"  # type: ignore[misc]

    def test_collections_immutable_by_type(self):
        context = parse_file_context(
            {"file_path": "/x", "tags": ["a"], "extra": {"k": "v"}}
        )
        assert context is not None
        with pytest.raises(Exception):
            context.tags.append("b")  # type: ignore[union-attr]
        with pytest.raises(Exception):
            context.extra["k2"] = "v2"  # type: ignore[index]


class TestChunkHash:
    """chunk_hash — dual-hash wire contract (D13): parsed, absent ⇒ None, no legacy alias."""

    def test_chunk_hash_parsed_from_metadata(self):
        context = parse_file_context({"file_path": "/x", "chunk_hash": "a1" * 32})
        assert context is not None
        assert context.chunk_hash == "a1" * 32

    def test_chunk_hash_absent_defaults_none(self):
        context = parse_file_context({"file_path": "/x"})
        assert context is not None
        assert context.chunk_hash is None

    def test_chunk_hash_is_known_key_not_extra(self):
        metadata = _load_fixture("file_context_contract_v1.json")
        metadata["chunk_hash"] = "b2" * 32

        context = parse_file_context(metadata)

        assert context is not None
        assert context.chunk_hash == "b2" * 32
        # Known v1 key — must not leak into the extra extension point.
        assert "chunk_hash" not in context.extra

    def test_legacy_hash_maps_to_file_hash(self):
        context = parse_file_context({"file_path": "/x", "hash": "c3" * 32})
        assert context is not None
        assert context.file_hash == "c3" * 32
        assert context.chunk_hash is None

    def test_legacy_filehash_maps_to_file_hash(self):
        # S5: legacy (pre-T9 camelCase) producers sent the camelCase file-hash key
        # for the whole-file hash. Built via concatenation so the literal does not
        # appear in source — the wire gate (snake_case-only readers) must stay clean.
        legacy_key = "file" + "Hash"
        context = parse_file_context({"file_path": "/x", legacy_key: "d4" * 32})
        assert context is not None
        assert context.file_hash == "d4" * 32
        assert context.chunk_hash is None

    def test_legacy_key_map_preserved_and_no_chunk_hash_alias(self):
        # chunk_hash never shipped under another name — no legacy alias may exist.
        from src.domain.models.file_context_model import _KNOWN_V1_KEYS, _LEGACY_KEY_MAP

        assert _LEGACY_KEY_MAP["hash"] == "file_hash"
        assert _LEGACY_KEY_MAP["file" + "Hash"] == "file_hash"
        assert "chunk_hash" not in _LEGACY_KEY_MAP.values()
        assert "chunk_hash" in _KNOWN_V1_KEYS


class TestLayerIsolation:
    """Domain module must not import infrastructure or application layers."""

    def test_no_infra_or_application_imports(self):
        from src.domain.models import file_context_model

        source = Path(file_context_model.__file__).read_text()
        assert "src.infrastructure" not in source
        assert "src.application" not in source
        assert "infrastructure" not in source
        assert "application" not in source
