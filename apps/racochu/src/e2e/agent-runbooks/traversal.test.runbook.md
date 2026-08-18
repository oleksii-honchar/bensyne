> Shared conventions (prerequisites, MCP-only, file_id discovery, debounce, fixtures, cleanup): see the racochu-agentic-testing skill (SKILL.md §Runbook Conventions).

# Agent e2e test

## Traversal scenario

### Test Objective

Verify `expandFileRelations` for (A) Obsidian wikilink (`backlink`) edges — **regression gate for the D34 wikilink path fix**; (B) agent-session companion edges; (C) error handling.

## Part A — wikilinks (bank `tmp-obsidian`)

### Fixtures

```bash
cat > tmp/obsidian/rb-trav-hub.md <<'EOF'
# Traversal Hub

RB_TRAV_HUB. Links to [[rb-trav-note-a]] and [[rb-trav-note-b]].
EOF

cat > tmp/obsidian/rb-trav-note-a.md <<'EOF'
# Note A

RB_TRAV_NOTE_A. Alpha note body.
EOF

cat > tmp/obsidian/rb-trav-note-b.md <<'EOF'
# Note B

RB_TRAV_NOTE_B. Beta note body.
EOF
```

Wait ≥3s for debounce + chunking + ingestion (the hub may be processed in any order — edges resolve by path regardless of target ingestion order).

### Test Steps

#### Part A, Step 1: Discover hub file_id

- Call `searchFiles("RB_TRAV_HUB", memory_bank="tmp-obsidian", limit=5)`
- `hub_id` = `file.id` of the file-backed group.
- **PASS:** `hub_id` non-empty.

#### Part A, Step 2: Discover note file_ids

- Call `searchFiles("RB_TRAV_NOTE_A", memory_bank="tmp-obsidian", limit=5)` → `note_a_id` (file-backed group's `file.id`).
- Call `searchFiles("RB_TRAV_NOTE_B", memory_bank="tmp-obsidian", limit=5)` → `note_b_id` (same method).
- **PASS:** both `note_a_id` and `note_b_id` non-empty.

#### Part A, Step 3: Expand hub wikilink relations (acceptance gate for D34)

- Call `expandFileRelations(hub_id, memory_bank="tmp-obsidian", relation_types=["backlink"])`
- **PASS:** `source_file.id == hub_id`; `related_files` has **exactly 2** entries; their `file.id` set == {`note_a_id`, `note_b_id`}; each related entry has non-empty `content` and `chunks_count >= 1`.
- **FAIL signature (pre-fix bug):** `related_files == []` — wikilink edges emitted as relative paths, target file_ids never matched. **This step is the live acceptance gate for the D34 wikilink path fix.**

#### Part A, Step 4: One-way check

- Call `expandFileRelations(note_a_id, memory_bank="tmp-obsidian", relation_types=["backlink"])`
- **PASS:** `related_files == []` (no backlink edge originates from note-a — wikilinks are one-way: hub → linked note).

## Part B — agent-session companions (bank `tmp-agent-sessions`)

**Order is required** — companion detection reads `session.md` from disk when processing companions: write `session.md` **first**, wait ≥3s, **then** write the companion fixtures.

**Note on edge direction:** companion edges emit **from** the companion files (`parent_child` → `session.md`, `sibling` → other companions); `session.md` itself emits no companion edges. That is why traversal assertions expand from `findings.md`, not the root (spec §3.2 relation-types note).

### Fixtures

Root: `tmp/agent-sessions/rb-trav-session/`

**First:** `session.md`

```bash
mkdir -p tmp/agent-sessions/rb-trav-session/findings tmp/agent-sessions/rb-trav-session/materials

cat > tmp/agent-sessions/rb-trav-session/session.md <<'EOF'
---
sessionId: ses-rb-traversal-test
createdAt: "2026-08-18T00:00:00Z"
status: active
phase: research
---

# Traversal Session

RB_TRAV_SESSION unique token. Session root content.
EOF
```

Wait ≥3s, then write the companion fixtures:

```bash
cat > tmp/agent-sessions/rb-trav-session/findings/findings.md <<'EOF'
# Findings

RB_TRAV_FINDINGS. Companion findings content.
EOF

cat > tmp/agent-sessions/rb-trav-session/materials/unified-chunk-contract.md <<'EOF'
# Unified Chunk Contract

RB_TRAV_MATERIALS. Companion materials content.
EOF
```

Wait ≥3s.

### Test Steps

#### Part B, Step 1: Discover findings/session/materials file_ids

- Call `searchFiles("RB_TRAV_FINDINGS", memory_bank="tmp-agent-sessions", limit=5)` → `findings_id` (file-backed group's `file.id`).
- **PASS:** `findings_id` non-empty.
- Also discover `session_id_file` via `searchFiles("RB_TRAV_SESSION", memory_bank="tmp-agent-sessions", limit=5)` and `materials_id` via `searchFiles("RB_TRAV_MATERIALS", memory_bank="tmp-agent-sessions", limit=5)` (same method — file-backed group's `file.id`).

#### Part B, Step 2: Expand findings companion relations

- Call `expandFileRelations(findings_id, memory_bank="tmp-agent-sessions")`
- **PASS:** `source_file.id == findings_id`; `related_files` contains an entry whose `file.id == session_id_file` (relation `parent_child`) and one whose `file.id == materials_id` (relation `sibling`); each has non-empty `content`.

#### Part B, Step 3: Reciprocity

- Call `expandFileRelations(materials_id, memory_bank="tmp-agent-sessions")`
- **PASS:** `related_files` contains entries with `file.id` == `session_id_file` and `findings_id`.

## Part C — error case

### Test Steps

#### Part C, Step 1: Unknown file_id

- Call `expandFileRelations("file_does_not_exist_rbx", memory_bank="tmp-vault")`
- **PASS:** error result with code `FILE_NOT_FOUND`.

## Cleanup

- Delete the 3 Obsidian fixtures:
  - `tmp/obsidian/rb-trav-hub.md`
  - `tmp/obsidian/rb-trav-note-a.md`
  - `tmp/obsidian/rb-trav-note-b.md`
- Delete the agent-session fixture tree: `rm -rf tmp/agent-sessions/rb-trav-session`
- Verify with `ls tmp/obsidian/ tmp/agent-sessions/` that the fixtures are gone.
