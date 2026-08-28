"""Drift test — `skills/bensyne/SKILL.md` must teach search-first, not list-first.

The skill previously taught "call listMemoryBanks first to discover banks".
That wording has been replaced with `searchMemoryBank` (preferred) /
`listMemoryBanks` (diagnostic). This test fails CI if the old
`listMemoryBanks first` cue reappears in any skill text — and asserts the
new `searchMemoryBank` cue is present.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest


# Canonical skill path per the project layout. Override via env var if a
# local checkout puts the skill at a different location.
_DEFAULT_SKILL_PATH = (
    "/Users/oleksii.honchar/Documents/agent-rules-n-skills/skills/bensyne/SKILL.md"
)


def _skill_path() -> Path:
    override = os.environ.get("BENSYNE_SKILL_PATH")
    return Path(override) if override else Path(_DEFAULT_SKILL_PATH)


# Phrases that mark the OLD "list first" framing — must NOT appear.
FORBIDDEN_PHRASES = (
    "listMemoryBanks first",
    "listMemoryBanks called first",
    "Call listMemoryBanks() — no parameters",
    "ALWAYS first - before any recall",
    "Run listMemoryBanks first to confirm",
)

# Phrases that must appear (search-first framing).
REQUIRED_PHRASES = (
    "searchMemoryBank",
    "listMemoryBanks",
)


@pytest.fixture(scope="module")
def skill_text() -> str:
    p = _skill_path()
    if not p.exists():
        pytest.skip(f"Bensyne skill not found at {p} — set BENSYNE_SKILL_PATH")
    return p.read_text(encoding="utf-8")


class TestSkillTextDrift:
    """Old list-first wording is forbidden; search-first wording is required."""

    @pytest.mark.parametrize("phrase", FORBIDDEN_PHRASES)
    def test_forbidden_phrase_absent(self, skill_text: str, phrase: str) -> None:
        assert phrase not in skill_text, (
            f"Skill text contains forbidden list-first phrase: {phrase!r}. "
            f"Replace with searchMemoryBank (preferred) or listMemoryBanks (diagnostic)."
        )

    def test_search_memory_bank_is_mentioned(self, skill_text: str) -> None:
        """searchMemoryBank must appear in the skill — that's the new primary."""
        assert "searchMemoryBank" in skill_text, (
            "Skill text must reference searchMemoryBank — it is the new primary "
            "discovery primitive."
        )

    def test_per_agent_starter_keyword_table_present(self, skill_text: str) -> None:
        """Phase 1 of the skill must include the 11-row per-agent starter-keyword
        table (architect, developer, ..., worker)."""
        expected_rows = (
            "architect",
            "developer",
            "icm-operator",
            "researcher",
            "reviewer",
            "session",
            "super-developer",
            "super-worker",
            "vault-keeper",
            "worker",
        )
        for agent in expected_rows:
            # Each row should appear in the skill in pipe-table form: `| `agent` |`
            row_pattern = rf"\|\s*`?{re.escape(agent)}`?\s*\|"
            assert re.search(row_pattern, skill_text), (
                f"Skill text must contain a table row for agent {agent!r}"
            )

    def test_generalist_caveat_present(self, skill_text: str) -> None:
        """The `generalist` row's caveat must guide agents to derive the query
        from the user's first request — not invent a fixed query."""
        assert "generalist" in skill_text, "Skill must reference generalist"
        # The derive-from-request cue should appear near generalist.
        idx = skill_text.index("generalist")
        window = skill_text[idx : idx + 600]
        assert "derive" in window.lower(), (
            "Skill must tell generalist agents to derive the searchMemoryBank "
            "query from the user's first request."
        )
