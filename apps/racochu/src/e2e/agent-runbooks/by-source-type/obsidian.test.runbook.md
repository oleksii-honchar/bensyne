# Agent e2e test

Test manually all the bensyne and racochu functionality — use mcp tools, do not try to call server via curl.

**MCP enforcement:** Use only Bensyne MCP tools available via `meta_search` / `meta_use` (e.g., `recallMemory`, `listMemoryBanks`). **Never curl the MCP server.**

Fixtures go to `tmp/obsidian/` (obsidian sourceType).

**Bank scoping is MANDATORY (D39):** Every bank-scoped MCP call must specify `memory_bank="tmp-obsidian"` — the `tmp-obsidian` source id from `dev.yaml`. This applies to `searchFiles`, `recallMemory`, `expandFileRelations`, `fetchFile`, `getMemoryStats`, `registerMemoryBank`, `forgetMemory`, `updateMemory`, `sleep`. `listMemoryBanks` is the only exception: it takes no `memory_bank` (it lists all banks) and is used here only to confirm `tmp-obsidian` exists. Never omit, never mix.

> **Wikilink edge contract (D34 / D40):** The obsidian chunker resolves each body wikilink `[[Target]]` to a **`backlink`** edge whose `target_path` is `<watchRoot>/<Target>.md` (strength 1). An edge **resolves** (appears in `expandFileRelations` `related_files` with real content) only when the target note file actually exists and was ingested. Unresolvable targets remain best-effort `PENDING` stubs (D4) — they are **wikilink metadata**, not guaranteed resolved files. Wikilinks are **one-way** (hub → linked note); a linked note with no wikilinks of its own yields no outgoing `backlink` edges.

## Obsidian Frontmatter + Wikilink Scenario

### Test Objective

Verify end-to-end Obsidian frontmatter preservation and wikilink graph feature in racochu:
1. Are **all** frontmatter keys preserved (generic properties + typed `base` field)?
2. Are wikilink metadata (`note.wikilinks`) extracted and attached to chunks?
3. Are **resolved `backlink` edges** discoverable via `expandFileRelations` from the hub note?
4. Are enriched chunks searchable by generic properties and wikilinks?

### Prerequisites

- racochu running with `sourceType: obsidian` on the `tmp-obsidian` watch source
- bensyne-dev MCP tools available
- `tmp/obsidian/` directory writable

### Test Steps

#### Step 1: Check Current State

- Call `listMemoryBanks` (lists all banks; no bank param) → confirm `tmp-obsidian` appears.
- Call `getMemoryStats(memory_bank="tmp-obsidian")` to see the current memory count.
- Call `recallMemory("RB_OBS_HUB", memory_bank="tmp-obsidian", limit=5)` → expect 0 results (clean start).
- **PASS:** `tmp-obsidian` bank present; `RB_OBS_HUB` recall returns 0 rows.

#### Step 2: Create the hub note with full frontmatter + wikilinks

Create the hub note at `tmp/obsidian/obsidian-test-note.md` (relative to racochu root). Its wikilinks point to `Note A` / `Note B` / `Note C` / `Note D` / `Note E`:

```bash
cat > tmp/obsidian/obsidian-test-note.md <<'EOF'
---
aliases:
  - Test Note Aliases
tags:
  - obsidian
  - test
created: 2026-08-08
modified: 2026-08-08
notion-id: test-uuid-12345
base: "[[Test Database.base]]"
Kind: note
Project: test-project
custom-array-field:
  - item1
  - item2
custom-number: 42
---
# Test Obsidian Note

RB_OBS_HUB. This note tests the full frontmatter + wikilink pipeline.

## Links Section

See [[Note A]] for basic links and [[Note B|Note B Alias]] for aliased links.
Also check [[Note C#Section Header]] for section links and [[Note D#Section|D Alias]] for both.
Embedded: ![[Note E]]

Duplicate test: [[Note A]] should be deduplicated.

## Content Section

Some actual content here for the chunking pipeline.
More content to ensure body chunks are created.
EOF
```

Wait **≥3s** for debounce + chunking + wikilink extraction.

#### Step 3: Create real target notes so some wikilinks RESOLVE as edges

The hub's `[[Note A]]` and `[[Note B]]` wikilinks resolve to `<watchRoot>/Note A.md` and `<watchRoot>/Note B.md`. Create those two real note files so the corresponding `backlink` edges resolve end-to-end (edges are resolved by path regardless of ingestion order — **but** they must not contain wikilinks of their own, or the one-way check in Step 11 breaks):

```bash
cat > tmp/obsidian/Note A.md <<'EOF'
# Note A

RB_OBS_NOTE_A. Linked note A body content.
EOF

cat > tmp/obsidian/Note B.md <<'EOF'
# Note B

RB_OBS_NOTE_B. Linked note B body content.
EOF
```

Wait **≥3s** for debounce + chunking + ingestion (so both notes have real `file_id`s, not `PENDING` stubs).

> `Note C`, `Note D`, `Note E` intentionally have **no** real files — they exercise the wikilink-metadata path only and remain dangling `PENDING` stubs (D4). Do not assert them as resolved edges.

#### Step 4: Discover file_ids via search (bank-scoped)

- Call `searchFiles("RB_OBS_HUB", memory_bank="tmp-obsidian", limit=5)` → `hub_id` = the file-backed group's `file.id` (`file != null`).
- Call `searchFiles("RB_OBS_NOTE_A", memory_bank="tmp-obsidian", limit=5)` → `note_a_id` (file-backed group's `file.id`).
- Call `searchFiles("RB_OBS_NOTE_B", memory_bank="tmp-obsidian", limit=5)` → `note_b_id` (file-backed group's `file.id`).
- **PASS:** all three `file.id`s are non-empty.

#### Step 5: Verify Frontmatter Preservation — Typed Fields

- Call `recallMemory("RB_OBS_HUB", memory_bank="tmp-obsidian", limit=5)`; find the hub row (row whose `file_enrichment.file.id == hub_id`).
- **PASS — typed fields:** the hub's chunks expose these metadata keys:
  - `note.aliases` = JSON array containing "Test Note Aliases"
  - `note.tags` = JSON array containing "obsidian" and "test"
  - `note.created` = "2026-08-08"
  - `note.modified` = "2026-08-08"
  - `note.base` = "[[Test Database.base]]"

#### Step 6: Verify Frontmatter Preservation — Generic Properties

- From the same hub recall results:
- **PASS — generic properties:**
  - `note.properties.notion-id` = "test-uuid-12345"
  - `note.properties.kind` = "note" (lowercased from `Kind`)
  - `note.properties.project` = "test-project" (lowercased from `Project`)
  - `note.properties.custom-array-field` = "[\"item1\",\"item2\"]" (JSON.stringify of array)
  - `note.properties.custom-number` = "42" (stringified number)

#### Step 7: Verify Wikilink Metadata (note.wikilinks)

- From the same hub recall results:
- **PASS — wikilink metadata:**
  - `note.wikilinks` = JSON array containing: "Note A", "Note B", "Note C", "Note D", "Note E"
  - Confirm "Note A" appears only **once** (dedup — it appeared twice in source)
  - Confirm section/alias stripped: target is "Note C" not "Note C#Section Header"

#### Step 8: Verify Chunk Coverage

- **PASS:** the hub recall returns at least 2 chunks:
  - Chunk 0 (frontmatter, importance 0.9): should have all metadata (note.base, note.properties.*, note.wikilinks)
  - Chunk 1+ (body, importance 0.5): should also have note.wikilinks (wikilinks are body-derived, attached to all chunks)

#### Step 9: Verify No-Frontmatter Wikilink Attachment

Create a second test file at `tmp/obsidian/obsidian-no-fm.md`:

```bash
cat > tmp/obsidian/obsidian-no-fm.md <<'EOF'
# No Frontmatter Note

RB_OBS_NO_FM. This note has no frontmatter but contains [[Link Alpha]] and [[Link Beta|Beta Alias]].
Some body content here.
EOF
```

- Wait **2s** for debounce
- Call `recallMemory("RB_OBS_NO_FM", memory_bank="tmp-obsidian", limit=5)`
- **PASS — wikilinks extracted:** returned chunks have `note.wikilinks` = JSON array containing "Link Alpha", "Link Beta"
- **PASS — no properties:** chunks do **NOT** have `note.base` or `note.properties.*` keys (no frontmatter = no properties)

#### Step 10: Verify Wikilink Backlink Edges Resolve (hub → linked notes)

This is the resolved-edge verification that now lives in this by-source-type runbook (moved out of the traversal runbook). Expand the hub's `backlink` relations and assert the two real target notes resolve:

- Call `expandFileRelations(hub_id, memory_bank="tmp-obsidian", relation_types=["backlink"])`
- **PASS — source:** `source_file.id == hub_id`.
- **PASS — linked notes resolve:** `related_files` contains an entry whose `file.id == note_a_id` **and** an entry whose `file.id == note_b_id`.
- **PASS — content reconstructed:** each of those two related entries has non-empty `content` (and `chunks_count >= 1`).
- **FAIL signature:** neither `note_a_id` nor `note_b_id` in `related_files` ⇒ wikilink edges not resolved to real files (D34 regression).
- Note: `Note C` / `Note D` / `Note E` are dangling metadata targets — if they appear as empty/`PENDING` stubs, that is expected and NOT a failure.

#### Step 11: Verify One-Way Edge Direction (linked note → no backlinks)

Wikilinks are one-way (hub → linked note). A linked note with no wikilinks of its own must yield no outgoing `backlink` edges:

- Call `expandFileRelations(note_a_id, memory_bank="tmp-obsidian", relation_types=["backlink"])`
- **PASS:** `source_file.id == note_a_id` and `related_files == []` (no `backlink` edge originates from Note A).

#### Step 12: Check Logs

- Check logs at `~/.local/share/racochu/logs` to verify the obsidian chunker was selected (look for `Chunker selected: sourceType="obsidian"` in the logs).

#### Step 13: Cleanup

- Delete all test files from `tmp/obsidian/`:
  - `tmp/obsidian/obsidian-test-note.md` (hub)
  - `tmp/obsidian/Note A.md`
  - `tmp/obsidian/Note B.md`
  - `tmp/obsidian/obsidian-no-fm.md`
- Wait **≥3s** for debounce + forget.
- Call `recallMemory("RB_OBS_HUB", memory_bank="tmp-obsidian", limit=5)`, `recallMemory("RB_OBS_NOTE_A", memory_bank="tmp-obsidian", limit=5)`, and `recallMemory("RB_OBS_NO_FM", memory_bank="tmp-obsidian", limit=5)` → confirm memories were cleaned up (0 results).

### Expected Outcomes Summary

| Check | Expected |
|-------|----------|
| Bank scoping | Every bank-scoped call uses `memory_bank="tmp-obsidian"` |
| Typed fields preserved | aliases, tags, created, modified, base all present |
| Generic properties | notion-id, kind, project, custom-array-field, custom-number in `note.properties.*` |
| Capitalized keys lowercased | `Kind` → `kind`, `Project` → `project` |
| Non-string values stringified | array → `JSON.stringify`, number → string |
| Wikilinks metadata extracted | All 5 targets captured (A, B, C, D, E) |
| Wikilink metadata dedup | "Note A" appears once |
| Section/alias stripped | "Note C" not "Note C#Section Header" |
| Wikilinks on all chunks | Frontmatter chunk + body chunks all have `note.wikilinks` |
| No-FM wikilinks | Chunks get wikilinks but no `note.base`/`note.properties.*` |
| Resolved backlink edges | `expandFileRelations(hub, backlink)` → Note A + Note B in `related_files` with non-empty content |
| One-way edge direction | `expandFileRelations(note_a, backlink)` → `related_files == []` |
| Cleanup | Memories forgotten after file deletion |
