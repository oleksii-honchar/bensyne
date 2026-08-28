"""Drift test — the per-agent keyword table in `skills/bensyne/SKILL.md` must
cover every persona bank the project owns.

If a new persona bank is added (e.g. `persona_<new_role>`):
  1. Add a row to the skill-text table (`skills/bensyne/SKILL.md` Phase 1).
  2. Add the corresponding `persona_<new_role>` to `EXPECTED_PERSONA_BANKS`
     in `tests/test_application/test_search_memory_bank_use_case.py`.

This test catches #1 vs #2 drift.

Note: previously this test imported `PER_ROLE_KEYWORDS` from the use case.
The use case no longer hardcodes a per-role keyword table — keywords
derive purely from the bank ``name`` (tokenise on ``_`` / ``-``). So the
authoritative list of personas moved to the use case test module, which
this drift test mirrors as a hardcoded set.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest


_DEFAULT_SKILL_PATH = (
    "/Users/oleksii.honchar/Documents/agent-rules-n-skills/skills/bensyne/SKILL.md"
)


def _skill_path() -> Path:
    override = os.environ.get("BENSYNE_SKILL_PATH")
    return Path(override) if override else Path(_DEFAULT_SKILL_PATH)


# Authoritative set of persona bank names. Mirrors `EXPECTED_PERSONA_BANKS`
# in `tests/test_application/test_search_memory_bank_use_case.py`. If you
# add or remove a persona bank, update BOTH this set AND the test set.
EXPECTED_PERSONA_BANKS: frozenset[str] = frozenset(
    {
        "persona_architect",
        "persona_developer",
        "persona_generalist",
        "persona_icm-operator",
        "persona_researcher",
        "persona_reviewer",
        "persona_session",
        "persona_super-developer",
        "persona_super-worker",
        "persona_vault-keeper",
        "persona_worker",
    }
)


@pytest.fixture(scope="module")
def skill_text() -> str:
    p = _skill_path()
    if not p.exists():
        pytest.skip(f"Bensyne skill not found at {p} — set BENSYNE_SKILL_PATH")
    return p.read_text(encoding="utf-8")


def _parse_skill_table_agents(skill_text: str) -> set[str]:
    """Extract agent names from the per-agent starter-keyword markdown table.

    Looks for rows like ``| `architect` | `...` |`` and returns the set of
    agent names. Skips header/separator rows. Keeps the `generalist` row
    even though its query cell says "(derive from user request — see above)"
    — the row IS in the table per spec C7.1.
    """
    rows: set[str] = set()
    for line in skill_text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 2:
            continue
        agent_cell, query_cell = cells
        # Header / separator rows: skip when the agent cell isn't backticked
        # or the query cell starts with dashes (markdown separator).
        if not agent_cell.startswith("`"):
            continue
        if query_cell.startswith("-"):
            continue
        m = re.match(r"`([^`]+)`", agent_cell)
        if not m:
            continue
        rows.add(m.group(1))
    return rows


class TestPersonaTableSync:
    """Skill-text persona table must cover every persona bank the project owns."""

    def test_skill_table_covers_all_personas(self, skill_text: str) -> None:
        """Every `persona_*` bank in `EXPECTED_PERSONA_BANKS` must have a
        corresponding row in the skill's per-agent starter-keyword table
        (with the `persona_` prefix stripped)."""
        skill_agents = _parse_skill_table_agents(skill_text)
        expected_short_names = {
            name.removeprefix("persona_") for name in EXPECTED_PERSONA_BANKS
        }
        missing = expected_short_names - skill_agents
        assert not missing, (
            f"Persona banks missing from the skill-text table: {sorted(missing)}. "
            f"Add rows to skills/bensyne/SKILL.md Phase 1 starter-keyword table "
            f"(one per persona) and mirror the change in EXPECTED_PERSONA_BANKS "
            f"in tests/test_application/test_search_memory_bank_use_case.py."
        )
