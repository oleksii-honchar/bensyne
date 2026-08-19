> Shared conventions (prerequisites, MCP-only, file_id discovery, debounce, fixtures, cleanup): see the racochu-agentic-testing skill (SKILL.md §Runbook Conventions).

# Agent e2e test

## Traversal scenario

### Test Objective

Verify the `expandFileRelations` **tool contract** generically — response structure, `relation_types` filter isolation, and error handling.

> **Source-specific relation assertions live elsewhere:**
> - Obsidian wikilink `backlink` edges → `by-source-type/obsidian.test.runbook.md`
> - Agent-session companion (`parent_child`/`sibling`) + `cross_reference` edges (S0–S9) → `by-source-type/agent-sessions.test.runbook.md`
>
> This runbook tests the **tool contract only** — that `expandFileRelations` returns correctly structured responses, respects the `relation_types` filter, and handles errors. It does NOT assert on the semantic correctness of any specific source-type's edge production.

**Bank scoping is MANDATORY (D39):** Every `searchFiles`/`expandFileRelations` call must specify exactly one `memory_bank` — the bank where the fixture was placed.

## Fixtures

Uses `tmp-agent-sessions` bank (agent-session companion detection produces `parent_child` + `sibling` edges automatically — a deterministic, source-agnostic way to generate relations for tool-contract testing).

Root: `tmp/agent-sessions/rb-tool-contract/`

**Write `session.md` first, wait ≥3s, then write the companion:**

```bash
mkdir -p tmp/agent-sessions/rb-tool-contract/findings

cat > tmp/agent-sessions/rb-tool-contract/session.md <<'EOF'
---
sessionId: ses-rb-tool-contract
createdAt: "2026-08-19T00:00:00Z"
status: active
phase: research
---

# Tool Contract Test

RB_TOOL_CONTRACT_SESSION. Session root content.
EOF
```

Wait ≥3s, then:

```bash
cat > tmp/agent-sessions/rb-tool-contract/findings/findings.md <<'EOF'
# Findings

RB_TOOL_CONTRACT_FINDINGS. Companion findings content for tool-contract test.
EOF
```

Wait ≥3s for debounce + chunking + ingestion.

## Tool-Contract Test Steps

#### Step 1: Discover file_ids

- Call `searchFiles("RB_TOOL_CONTRACT_SESSION", memory_bank="tmp-agent-sessions", limit=5)` → `session_id` (file-backed group's `file.id`).
- Call `searchFiles("RB_TOOL_CONTRACT_FINDINGS", memory_bank="tmp-agent-sessions", limit=5)` → `findings_id` (file-backed group's `file.id`).
- **PASS:** both `session_id` and `findings_id` are non-empty.

#### Step 2: One-hop expansion — response structure

Expand from `findings_id` (which has outgoing `parent_child` → session.md and `sibling` → other companions if present).

- Call `expandFileRelations(findings_id, memory_bank="tmp-agent-sessions")`
- **PASS — `source_file` structure:** response contains a `source_file` object with:
  - `source_file.id` == `findings_id`
  - `source_file.path` non-empty string
  - `source_file.source_type` == `"agent-sessions"`
  - `source_file.id`, `source_file.path`, `source_file.source_type` keys all present
- **PASS — `related_files` is an array:** response contains a `related_files` array (may be empty if no outgoing relations from this file, but the key must exist).
- **PASS — `related_files` entry structure** (if array is non-empty): each entry has:
  - `file.id` — non-empty string (the related file's id)
  - `file.relation_type` — non-empty string (e.g. `"parent_child"`, `"sibling"`, `"backlink"`)
  - `content` — non-empty string when the related file is chunked and has content
  - `chunks_count` — integer ≥ 1 for chunked files
- **PASS — `file.id` matches a real file:** for the entry whose `file.relation_type == "parent_child"`, `file.id` == `session_id` (confirms the relation target is correctly resolved).

#### Step 3: `relation_types` filter isolation

The `relation_types` parameter must return **only** the requested relation types — no mixing.

- Call `expandFileRelations(findings_id, memory_bank="tmp-agent-sessions", relation_types=["parent_child"])`
- **PASS — filter respected:** `related_files` contains **only** entries where `file.relation_type == "parent_child"`. No `sibling`, no `backlink`, no `cross_reference` entries appear.
- **PASS — parent_child target correct:** if `related_files` is non-empty, the entry's `file.id` == `session_id` (the parent of `findings.md`).

- Call `expandFileRelations(findings_id, memory_bank="tmp-agent-sessions", relation_types=["sibling"])`
- **PASS — filter respected (sibling):** `related_files` contains **only** entries where `file.relation_type == "sibling"`. No `parent_child` entries appear.
- **NOTE:** `related_files` may be empty if there are no other sibling companions in this fixture tree — that is correct behavior (filter works, zero matches is valid).

#### Step 4: Non-existent relation type returns empty

- Call `expandFileRelations(findings_id, memory_bank="tmp-agent-sessions", relation_types=["nonexistent_type"])`
- **PASS:** `related_files == []` (no relations of that type; tool does not error on unknown filter value — returns empty).
- **PASS:** `source_file.id == findings_id` (source file still returned correctly).

## Part C — error case

#### Part C, Step 1: Unknown file_id

- Call `expandFileRelations("file_does_not_exist_rbx", memory_bank="tmp-agent-sessions")`
- **PASS:** error result with code `FILE_NOT_FOUND`.

## Cleanup

- Delete the tool-contract fixture tree: `rm -rf tmp/agent-sessions/rb-tool-contract`
- Wait ≥3s for debounce + forget.
- Verify with `ls tmp/agent-sessions/` that the fixture is gone.
- Call `searchFiles("RB_TOOL_CONTRACT_SESSION", memory_bank="tmp-agent-sessions", limit=5)` → 0 results (memories cleaned).
