"""D29 source-type axis lock (spec §6.6, gate 11 — bensyne half).

The canonical value set is declared once in contract v1 and mirrored verbatim
by (a) the domain ``SourceType`` enum, (b) the frozen bootstrap DDL CHECK
constraint (D28), and (c) racochu's ``SOURCE_TYPES`` const (Task 17). This
module is the bensyne-side cross-lock:

- the enum has EXACTLY the 4 D29 members (1:1 gate, spec §14.11);
- the enum value set == the frozen DDL CHECK value set (any drift between
  domain enum and bootstrap DDL fails here).

Old→new collapse (D29 / spec §6.6): ``agent_session`` → ``agent-sessions``;
``file_system`` → ``vault`` (generic/default source — the knowledge vault);
``git`` / ``database`` / ``external`` / ``remote`` → ``unknown`` (not real
sources; degrade-never-reject fallback marker).
"""

from __future__ import annotations

import re

from src.domain.models.file_model import SourceType
from src.infrastructure.storage.sqlite.file_metadata_migrations import MIGRATIONS

# D29 canonical value set (spec §6.6) — the single source of truth mirror.
D29_CANONICAL_VALUES = {"obsidian", "agent-sessions", "vault", "unknown"}
D29_CANONICAL_NAMES = {"OBSIDIAN", "AGENT_SESSIONS", "VAULT", "UNKNOWN"}

# The pre-D29 location-based 7-value set (spec §6.6 ruling: none of the six
# non-unknown values is a real source type).
LEGACY_VALUES = {"agent_session", "file_system", "git", "database", "external", "remote"}

# The frozen bootstrap DDL CHECK (D28, spec §6.5 item 2):
# ``source_type TEXT NOT NULL CHECK (source_type IN (...))``
_SOURCE_TYPE_CHECK_RE = re.compile(
    r"CHECK\s*\(\s*source_type\s+IN\s*\(([^)]*)\)\s*\)"
)


def _frozen_check_values() -> set[str]:
    """Extract the source_type CHECK value list from the frozen bootstrap DDL."""
    bootstrap = MIGRATIONS[0]
    assert bootstrap.version == 1, "bootstrap migration must be version 1"
    match = _SOURCE_TYPE_CHECK_RE.search(bootstrap.up_sql)
    assert match is not None, "bootstrap DDL lost the source_type CHECK constraint"
    return set(re.findall(r"'([^']+)'", match.group(1)))


class TestSourceTypeEnumShape:
    """1:1 gate (spec §14.11): the enum is EXACTLY the 4 D29 values."""

    def test_enum_has_exactly_four_d29_values(self) -> None:
        assert {m.value for m in SourceType} == D29_CANONICAL_VALUES

    def test_enum_has_exactly_four_d29_member_names(self) -> None:
        assert {m.name for m in SourceType} == D29_CANONICAL_NAMES

    def test_no_legacy_member_survives(self) -> None:
        assert not (LEGACY_VALUES & {m.value for m in SourceType})


class TestEnumMatchesFrozenCheck:
    """Domain enum value set == frozen bootstrap DDL CHECK value set.

    The CHECK was frozen with D29's set in Task 15 (D28); this test is the
    drift lock between the domain enum (Task 16) and the frozen DDL —
    either side changing alone fails the suite.
    """

    def test_enum_value_set_equals_frozen_check_value_set(self) -> None:
        assert {m.value for m in SourceType} == _frozen_check_values()

    def test_frozen_check_is_the_d29_set(self) -> None:
        # Guard against both sides drifting together away from the spec.
        assert _frozen_check_values() == D29_CANONICAL_VALUES
