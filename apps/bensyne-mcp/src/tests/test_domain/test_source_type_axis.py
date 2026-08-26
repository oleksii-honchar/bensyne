"""Source-type axis lock (spec §6.6, gate 11 — bensyne half).

The canonical value set is declared once and mirrored verbatim by
(a) the domain ``SourceType`` enum and (b) the effective final file
metadata schema CHECK constraint (the files DDL as defined by the last
migration that touches the files table). This module is the bensyne-side
cross-lock:

- the enum has EXACTLY the 5 canonical members (1:1 gate, spec §14.11);
- the enum value set == the effective final CHECK value set (any drift
  between domain enum and live DDL fails here);
- the bootstrap DDL (D28) CHECK remains frozen at D29's original 4-value
  set, byte-identical (the post-bootstrap migration carries the
  ``agent-persona`` extension).

``agent-persona`` extends the axis via the D29 package pattern (ADR-2) as
the producer of agent decision-tree node files.

Old→new collapse (D29 / spec §6.6): ``agent_session`` → ``agent-sessions``;
``file_system`` → ``vault`` (generic/default source — the knowledge vault);
``git`` / ``database`` / ``external`` / ``remote`` → ``unknown`` (not real
sources; degrade-never-reject fallback marker).
"""

from __future__ import annotations

import re
import sqlite3

from src.domain.models.file_model import SourceType
from src.infrastructure.storage.sqlite.file_metadata_migrations import MIGRATIONS

# Canonical source-type value set — the single source of truth mirror.
# D29's four producers + ``agent-persona`` (ADR-2 package extension).
SOURCE_TYPE_CANONICAL_VALUES = {"obsidian", "agent-sessions", "vault", "unknown", "agent-persona"}
SOURCE_TYPE_CANONICAL_NAMES = {"OBSIDIAN", "AGENT_SESSIONS", "VAULT", "UNKNOWN", "AGENT_PERSONA"}

# D29's original set, frozen verbatim into the bootstrap DDL (D28).
D29_CANONICAL_VALUES = {"obsidian", "agent-sessions", "vault", "unknown"}

# The pre-D29 location-based 7-value set (spec §6.6 ruling: none of the six
# non-unknown values is a real source type).
LEGACY_VALUES = {"agent_session", "file_system", "git", "database", "external", "remote"}

# The files DDL CHECK (D28/D29, spec §6.5 item 2):
# ``source_type TEXT NOT NULL CHECK (source_type IN (...))``
_SOURCE_TYPE_CHECK_RE = re.compile(
    r"CHECK\s*\(\s*source_type\s+IN\s*\(([^)]*)\)\s*\)"
)


def _check_values_from_files_ddl(files_ddl: str) -> set[str]:
    """Extract the source_type CHECK value list from a files table DDL."""
    match = _SOURCE_TYPE_CHECK_RE.search(files_ddl)
    assert match is not None, "files DDL lost the source_type CHECK constraint"
    return set(re.findall(r"'([^']+)'", match.group(1)))


def _frozen_check_values() -> set[str]:
    """Extract the source_type CHECK value list from the frozen bootstrap DDL."""
    bootstrap = MIGRATIONS[0]
    assert bootstrap.version == 1, "bootstrap migration must be version 1"
    return _check_values_from_files_ddl(bootstrap.up_sql)


def _effective_final_check_values() -> set[str]:
    """Extract the source_type CHECK value set from the effective final schema.

    Applies every migration to a throwaway in-memory DB and reads the live
    ``files`` DDL from ``sqlite_master`` — the schema as the runner would
    materialize it on a real bank at startup.
    """
    conn = sqlite3.connect(":memory:")
    try:
        for migration in MIGRATIONS:
            conn.executescript(migration.up_sql)
        row = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='files'").fetchone()
        assert row is not None, "files table missing from the effective schema"
        return _check_values_from_files_ddl(row[0])
    finally:
        conn.close()


class TestSourceTypeEnumShape:
    """1:1 gate (spec §14.11): the enum is EXACTLY the 5 canonical values."""

    def test_enum_has_exactly_five_source_type_values(self) -> None:
        assert {m.value for m in SourceType} == SOURCE_TYPE_CANONICAL_VALUES

    def test_enum_has_exactly_five_source_type_member_names(self) -> None:
        assert {m.name for m in SourceType} == SOURCE_TYPE_CANONICAL_NAMES

    def test_no_legacy_member_survives(self) -> None:
        assert not (LEGACY_VALUES & {m.value for m in SourceType})

    def test_agent_persona_member_exposed(self) -> None:
        assert SourceType.AGENT_PERSONA.value == "agent-persona"


class TestEnumMatchesEffectiveFinalCheck:
    """Domain enum value set == effective final CHECK value set.

    The live CHECK (as materialized by the migration runner) must equal the
    domain enum — either side changing alone fails the suite.
    """

    def test_enum_value_set_equals_effective_final_check_value_set(self) -> None:
        assert {m.value for m in SourceType} == _effective_final_check_values()

    def test_effective_final_check_is_the_canonical_set(self) -> None:
        # Guard against both sides drifting together away from the spec.
        assert _effective_final_check_values() == SOURCE_TYPE_CANONICAL_VALUES


class TestBootstrapCheckRemainsFrozen:
    """The bootstrap DDL CHECK stays verbatim at D29's original 4-value set.

    The ``agent-persona`` extension rides in a post-bootstrap migration; the
    bootstrap itself is never rewritten (D28 convention).
    """

    def test_bootstrap_check_is_the_d29_set(self) -> None:
        assert _frozen_check_values() == D29_CANONICAL_VALUES
