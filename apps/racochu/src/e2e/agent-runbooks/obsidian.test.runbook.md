# Agent e2e test

Test manually all the bensyne and racochu functionality — use mcp tools, do not try to call server via curl.

**MCP enforcement:** Use only Bensyne MCP tools available via `meta_search` / `meta_use` (e.g., `memory_recall`, `memory_list_banks`). **Never curl the MCP server.**

Fixtures go to `tmp/obsidian/` (obsidian strategy).

## Obsidian Frontmatter + Wikilink Scenario

### Test Objective

Verify end-to-end Obsidian frontmatter preservation and wikilink graph feature in racochu:
1. Are **all** frontmatter keys preserved (generic properties + typed `base` field)?
2. Are wikilink graph edges extracted and attached to chunks?
3. Are enriched chunks searchable by generic properties and wikilinks?

### Prerequisites

- racochu running with `strategy: obsidian` on the `tmp-obsidian` watch source
- bensyne-dev MCP tools available
- `tmp/obsidian/` directory writable

### Test Steps

#### Step 1: Check Current State

- List existing memory banks to confirm `tmp-obsidian` bank exists (use `memory_list_banks`)
- Get memory stats to see current memory count in `dev-watch`
- Recall a query that should return 0 results from an Obsidian-specific search (e.g., search by a property that doesn't exist yet)

#### Step 2: Create Test File with Full Frontmatter + Wikilinks

Create a test file at `tmp/obsidian/obsidian-test-note.md` (relative to project root):

```yaml
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

This note tests the full frontmatter + wikilink pipeline.

## Links Section

See [[Note A]] for basic links and [[Note B|Note B Alias]] for aliased links.
Also check [[Note C#Section Header]] for section links and [[Note D#Section|D Alias]] for both.
Embedded: ![[Note E]]

Duplicate test: [[Note A]] should be deduplicated.

## Content Section

Some actual content here for the chunking pipeline.
More content to ensure body chunks are created.
```

#### Step 3: Wait for Processing

- Wait 3 seconds for debounce + chunking + wikilink extraction

#### Step 4: Verify Frontmatter Preservation — Typed Fields

- Recall with query containing "obsidian test" or "Test Obsidian Note" (use `memory_recall`)
- Verify returned chunks have these metadata keys:
  - `note.aliases` = JSON array containing "Test Note Aliases"
  - `note.tags` = JSON array containing "obsidian" and "test"
  - `note.created` = "2026-08-08"
  - `note.modified` = "2026-08-08"
  - `note.base` = "[[Test Database.base]]"

#### Step 5: Verify Frontmatter Preservation — Generic Properties

- From the same recall results, verify these generic property metadata keys:
  - `note.properties.notion-id` = "test-uuid-12345"
  - `note.properties.kind` = "note" (lowercased from `Kind`)
  - `note.properties.project` = "test-project" (lowercased from `Project`)
  - `note.properties.custom-array-field` = "[\"item1\",\"item2\"]" (JSON.stringify of array)
  - `note.properties.custom-number` = "42" (stringified number)

#### Step 6: Verify Wikilink Graph

- From the same recall results, verify wikilink metadata:
  - `note.wikilinks` = JSON array containing: "Note A", "Note B", "Note C", "Note D", "Note E"
  - Confirm "Note A" appears only **once** (dedup — it appeared twice in source)
  - Confirm section/alias stripped: target is "Note C" not "Note C#Section Header"

#### Step 7: Verify Chunk Coverage

- Confirm the recall returns at least 2 chunks:
  - Chunk 0 (frontmatter, importance 0.9): should have all metadata (note.base, note.properties.*, note.wikilinks)
  - Chunk 1+ (body, importance 0.5): should also have note.wikilinks (wikilinks are body-derived, attached to all chunks)

#### Step 8: Verify No-Frontmatter Wikilink Attachment

Create a second test file at `tmp/obsidian/obsidian-no-fm.md` (relative to project root):

```markdown
# No Frontmatter Note

This note has no frontmatter but contains [[Link Alpha]] and [[Link Beta|Beta Alias]].
Some body content here.
```

- Wait 2 seconds for debounce
- Recall with query "No Frontmatter Note" or "Link Alpha" (use `memory_recall`)
- Verify returned chunks have `note.wikilinks` = JSON array containing "Link Alpha", "Link Beta"
- Verify chunks do **NOT** have `note.base` or `note.properties.*` keys (no frontmatter = no properties)

#### Step 9: Check Logs

- Check logs at `~/.local/share/racochu/logs` to verify obsidian strategy was selected (look for "Strategy selected: strategy=obsidian" in debug logs)

#### Step 10: Cleanup

- Delete both test files from `tmp/obsidian/`:
  - `tmp/obsidian/obsidian-test-note.md`
  - `tmp/obsidian/obsidian-no-fm.md`
- Wait 2 seconds for debounce + forget
- Recall the same queries to confirm memories were cleaned up

### Expected Outcomes Summary

| Check | Expected |
|-------|----------|
| Typed fields preserved | aliases, tags, created, modified, base all present |
| Generic properties | notion-id, kind, project, custom-array-field, custom-number in `note.properties.*` |
| Capitalized keys lowercased | `Kind` → `kind`, `Project` → `project` |
| Non-string values stringified | array → `JSON.stringify`, number → string |
| Wikilinks extracted | All 5 targets captured (A, B, C, D, E) |
| Wikilink dedup | "Note A" appears once |
| Section/alias stripped | "Note C" not "Note C#Section Header" |
| Wikilinks on all chunks | Frontmatter chunk + body chunks all have `note.wikilinks` |
| No-FM wikilinks | Chunks get wikilinks but no `note.base`/`note.properties.*` |
| Cleanup | Memories forgotten after file deletion |
