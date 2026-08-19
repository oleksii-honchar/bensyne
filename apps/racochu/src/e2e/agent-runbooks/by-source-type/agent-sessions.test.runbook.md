# Agent e2e test

Test manually all the bensyne and racochu functionality — use mcp tools, do not try to call server via curl.

**MCP enforcement:** Use only Bensyne MCP tools available via `meta_search` / `meta_use` (e.g., `recallMemory`, `listMemoryBanks`). **Never curl the MCP server.**

Fixtures go to `tmp/agent-sessions/` (agent-sessions sourceType).

**Bank scoping is MANDATORY (D39):** Every MCP call must specify `memory_bank="tmp-agent-sessions"`.

## Agent-Sessions Scenario

### Test Objective

Verify end-to-end the **agent-sessions** chunking strategy's distinctive behavior, asserted against `recallMemory` output (the file-layer `file_enrichment` block):

1. Are **session metadata keys** (`session.*`) extracted from `session.md` frontmatter and attached to companion file chunks?
2. Does the recalled file surface **`source_type == "agent-sessions"`**?
3. Are **companion relation edges** (`parent_child`, `sibling`) created and surfaced as `relations` / `related_files` on recall?
4. Are **traversal handles** (`file_id` + `relation_ids`) present for a companion?
5. Are **content `cross_reference` edges** (D42) emitted for in-content references to other session files?
6. Are **cross-session references** (S9) allowed and resolved?

> **Companion filename contract (deterministic):** the strategy only recognizes these canonical companion files in a session root:
> - `session.md` (the root; emits **no** `parent_child` edge — only `sibling` edges to present companions)
> - `specifications/spec.md`
> - `findings/findings.md`
> - `decisions/decisions.md`
> - `plans/implementation-plan.md`
> - `materials/unified-chunk-contract.md`
>
> Each non-session companion emits: `parent_child` → `session.md`, and `sibling` → each other present companion (excluding itself and `session.md`).

> **Cross-reference edge contract (D42 §2):** Content references in agent-session files become `cross_reference` edges (strength 0.7). The detection:
> - **Pass 1 (path-pattern):** regex `[\w./~-]+\.md\b` → tilde expansion → resolve (abs→as-is, rel→vs session root) → existence gate → emit edge
> - **Pass 2 (basename, conservative):** distinctive basenames (under `archive/`, or `session.md`, or unique in tree) → standalone-token match → emit edge
> - **No containment guard:** cross-session refs are ALLOWED (user ruling 2026-08-19)
> - **No dangling edges:** nonexistent targets emit nothing
> - **No self-edges:** self-references excluded

### Prerequisites

- racochu running with `sourceType: agent-sessions` on the `tmp-agent-sessions` watch source
- bensyne-dev MCP tools available
- `tmp/agent-sessions/` directory writable

### Test Steps

#### Step 1: Check Current State

- Call `listMemoryBanks`; confirm the `tmp-agent-sessions` bank exists.
- Recall a query that should return 0 results (e.g., `RB_AS_SESSION_TOKEN`) to confirm a clean start.

#### Step 2: Create session.md FIRST (with frontmatter + cross-ref to materials)

Create the session root and write `session.md` **first**:

```bash
mkdir -p tmp/agent-sessions/rb-as/{findings,specifications,materials,plans} tmp/agent-sessions/rb-as/{findings,specifications,materials}/archive

cat > tmp/agent-sessions/rb-as/session.md <<'EOF'
---
sessionId: ses-rb-agent-sessions
createdAt: "2026-08-19T12:00:00Z"
status: active
phase: research
nextAgent: developer
---

# Agent Sessions Test

RB_AS_SESSION_TOKEN. Session root content.

Reference: materials/unified-chunk-contract.md (the unified chunk contract for this session).
EOF
```

Wait **≥3s** for debounce + chunking + ingestion of `session.md` (companion detection reads `session.md` from disk when processing companions).

#### Step 3: Create companion + archived fixtures (with cross-refs)

Now write the companion files (canonical names — required for detection) AND the archived fixtures, each with their content references:

```bash
# Materials (canonical + archived) — TARGETS for cross-refs
cat > tmp/agent-sessions/rb-as/materials/unified-chunk-contract.md <<'EOF'
# Unified Chunk Contract

RB_AS_MATERIALS_TOKEN. Companion materials content.
EOF

cat > tmp/agent-sessions/rb-as/materials/archive/260819-0001-materials.md <<'EOF'
# Unified Chunk Contract (Archived)

RB_AS_MATERIALS_ARCHIVE_TOKEN. Archived materials content (superseded).
EOF

# Findings (canonical + archived) — SOURCE for S2/S6/S8, TARGET for S3/S4
cat > tmp/agent-sessions/rb-as/findings/findings.md <<'EOF'
# Findings

RB_AS_FINDINGS_TOKEN. Companion findings content.

See materials/unified-chunk-contract.md for the chunk contract.
See materials/archive/260819-0001-materials.md for the previous (archived) contract.
This is findings.md (self-reference for S8 test).
EOF

cat > tmp/agent-sessions/rb-as/findings/archive/260819-0001-findings.md <<'EOF'
# Findings (Archived)

RB_AS_FINDINGS_ARCHIVE_TOKEN. Archived findings content.

See materials/archive/260819-0001-materials.md for the archived contract.
EOF

# Specifications (canonical + archived) — SOURCE for S3/S7, TARGET for none
cat > tmp/agent-sessions/rb-as/specifications/spec.md <<'EOF'
# Spec

RB_AS_SPEC_TOKEN. Specification content.

See materials/unified-chunk-contract.md for the contract.
See findings/findings.md for the findings.
Ref specifications/ghost.md (nonexistent file for S7 test).
EOF

cat > tmp/agent-sessions/rb-as/specifications/archive/260819-0001-spec.md <<'EOF'
# Spec (Archived)

RB_AS_SPEC_ARCHIVE_TOKEN. Archived specification content.

See materials/unified-chunk-contract.md for the contract.
EOF

# Plans (implementation plan) — SOURCE for S4/S9
cat > tmp/agent-sessions/rb-as/plans/implementation-plan.md <<'EOF'
# Implementation Plan

RB_AS_PLAN_TOKEN. Implementation plan content.

See materials/unified-chunk-contract.md for the contract.
See findings/findings.md for the findings.
Reference: ../rb-as2/materials/b-contract.md (cross-session ref for S9 test).
EOF
```

Wait **≥3s** for debounce + chunking + ingestion.

#### Step 4: Re-touch session.md (for cross-ref edge resolution)

The cross-reference existence gate checks at chunk time. Since session.md was chunked in Step 2 (before materials existed), re-touch it now:

```bash
# Append a trivial line to trigger re-chunking
echo "" >> tmp/agent-sessions/rb-as/session.md
```

Wait **≥3s** for debounce + re-chunking + ingestion.

#### Step 5: Create second session (rb-as2) for S9 cross-session test

```bash
mkdir -p tmp/agent-sessions/rb-as2/materials

cat > tmp/agent-sessions/rb-as2/session.md <<'EOF'
---
sessionId: ses-rb-agent-sessions-2
createdAt: "2026-08-19T13:00:00Z"
status: active
phase: research
nextAgent: developer
---

# Agent Sessions Test 2

RB_AS2_SESSION_TOKEN. Second session content.
EOF

cat > tmp/agent-sessions/rb-as2/materials/b-contract.md <<'EOF'
# B Contract

RB_AS2_CONTRACT_TOKEN. Second session materials content.
EOF
```

Wait **≥3s** for debounce + chunking + ingestion (so rb-as2 files have real `file_id`s, not PENDING stubs).

#### Step 6: Discover all file_ids via search

- Call `searchFiles("RB_AS_SESSION_TOKEN", memory_bank="tmp-agent-sessions", limit=5)` → `session_id`.
- Call `searchFiles("RB_AS_FINDINGS_TOKEN", memory_bank="tmp-agent-sessions", limit=5)` → `findings_id`.
- Call `searchFiles("RB_AS_MATERIALS_TOKEN", memory_bank="tmp-agent-sessions", limit=5)` → `materials_id`.
- Call `searchFiles("RB_AS_SPEC_TOKEN", memory_bank="tmp-agent-sessions", limit=5)` → `spec_id`.
- Call `searchFiles("RB_AS_PLAN_TOKEN", memory_bank="tmp-agent-sessions", limit=5)` → `plan_id`.
- Call `searchFiles("RB_AS2_CONTRACT_TOKEN", memory_bank="tmp-agent-sessions", limit=5)` → `b_contract_id`.
- **PASS:** all six `file.id`s are non-empty.

#### Step 7: S0 — Regression: Verify companion edges + metadata (findings.md)

- Call `recallMemory("RB_AS_FINDINGS_TOKEN", memory_bank="tmp-agent-sessions", limit=5)`.
- Find the result row for the findings file (the row whose `file_enrichment.file.id == findings_id`).
- **PASS — source_type:** `file_enrichment.file.source_type == "agent-sessions"`.
- **PASS — session.* metadata** (present in **both** `file_enrichment.source_type_enrichment` and `file_enrichment.file.metadata`):
  - `session.id` = "ses-rb-agent-sessions"
  - `session.createdAt` = "2026-08-19T12:00:00Z"
  - `session.status` = "active"
  - `session.phase` = "research"
  - `session.nextAgent` = "developer"
- **PASS — parent_child edge:** `file_enrichment.relations` contains an entry with `relation_type == "parent_child"`; and `file_enrichment.related_files` contains an entry whose `id == session_id`.
- **PASS — sibling edge:** `file_enrichment.relations` contains an entry with `relation_type == "sibling"`; and `file_enrichment.related_files` contains an entry whose `id == materials_id`.
- **PASS — traversal handles:** `file_enrichment.traversal.file_id == findings_id` and `file_enrichment.traversal.relation_ids` is a **non-empty** array.

#### Step 8: S1 — Cross-ref from session.md to materials

- Call `recallMemory("RB_AS_SESSION_TOKEN", memory_bank="tmp-agent-sessions", limit=5)`.
- Find the row whose `file_enrichment.file.id == session_id`.
- **PASS — cross_reference edge:** `file_enrichment.relations` contains an entry with `relation_type == "cross_reference"`; and `file_enrichment.related_files` contains an entry whose `id == materials_id`.

#### Step 9: S2 — Cross-refs from findings.md (2 edges)

- Using the findings recall result from Step 7 (or re-call it):
- **PASS — cross_reference to canonical material:** `file_enrichment.related_files` contains an entry whose `id == materials_id` with `relation_type == "cross_reference"`.
- **PASS — cross_reference to archived material:** `file_enrichment.related_files` contains an entry whose `path` ends with `260819-0001-materials.md` with `relation_type == "cross_reference"`.

#### Step 10: S3 — Cross-refs from spec.md (2 edges)

- Call `recallMemory("RB_AS_SPEC_TOKEN", memory_bank="tmp-agent-sessions", limit=5)`.
- Find the row whose `file_enrichment.file.id == spec_id`.
- **PASS — cross_reference to materials:** `file_enrichment.related_files` contains an entry whose `id == materials_id` with `relation_type == "cross_reference"`.
- **PASS — cross_reference to findings:** `file_enrichment.related_files` contains an entry whose `id == findings_id` with `relation_type == "cross_reference"`.

#### Step 11: S4 — Cross-refs from implementation-plan.md (2 edges)

- Call `recallMemory("RB_AS_PLAN_TOKEN", memory_bank="tmp-agent-sessions", limit=5)`.
- Find the row whose `file_enrichment.file.id == plan_id`.
- **PASS — cross_reference to materials:** `file_enrichment.related_files` contains an entry whose `id == materials_id` with `relation_type == "cross_reference"`.
- **PASS — cross_reference to findings:** `file_enrichment.related_files` contains an entry whose `id == findings_id` with `relation_type == "cross_reference"`.

#### Step 12: S5 — Cross-ref from archived spec

- Call `searchFiles("RB_AS_SPEC_ARCHIVE_TOKEN", memory_bank="tmp-agent-sessions", limit=5)` → `archived_spec_id`.
- Call `recallMemory("RB_AS_SPEC_ARCHIVE_TOKEN", memory_bank="tmp-agent-sessions", limit=5)`.
- Find the row whose `file_enrichment.file.id == archived_spec_id`.
- **PASS — cross_reference to materials:** `file_enrichment.related_files` contains an entry whose `id == materials_id` with `relation_type == "cross_reference"`.

#### Step 13: S6 — Cross-ref from archived findings to archived material

- Call `searchFiles("RB_AS_FINDINGS_ARCHIVE_TOKEN", memory_bank="tmp-agent-sessions", limit=5)` → `archived_findings_id`.
- Call `recallMemory("RB_AS_FINDINGS_ARCHIVE_TOKEN", memory_bank="tmp-agent-sessions", limit=5)`.
- Find the row whose `file_enrichment.file.id == archived_findings_id`.
- **PASS — cross_reference to archived material:** `file_enrichment.related_files` contains an entry whose `path` ends with `260819-0001-materials.md` with `relation_type == "cross_reference"`.

#### Step 14: S7 — No edge for nonexistent ref

- Using the spec recall result from Step 10 (or re-call it):
- **PASS — no edge to ghost:** `file_enrichment.related_files` contains **NO** entry whose `path` ends with `ghost.md`.
- **PASS — no PENDING stub:** Call `searchFiles("ghost", memory_bank="tmp-agent-sessions", limit=5)` → 0 results or no file with path ending in `ghost.md`.

#### Step 15: S8 — No self edge

- Using the findings recall result from Step 7 (or re-call it):
- **PASS — no self edge:** `file_enrichment.related_files` contains **NO** entry whose `id == findings_id` with `relation_type == "cross_reference"`.

#### Step 16: S9 — Cross-session reference (POSITIVE check)

- Using the plan recall result from Step 11 (or re-call it):
- **PASS — cross_reference to B contract:** `file_enrichment.related_files` contains an entry whose `id == b_contract_id` with `relation_type == "cross_reference"`.
- **PASS — B file in related_files:** The B file appears in A's `file_enrichment.related_files` (proving cross-session refs are allowed and resolved).

#### Step 17: Verify session.md emits no parent_child edge

- Call `recallMemory("RB_AS_SESSION_TOKEN", memory_bank="tmp-agent-sessions", limit=5)`.
- Find the row whose `file_enrichment.file.id == session_id`.
- **PASS:** `file_enrichment.relations` contains **no** entry with `relation_type == "parent_child"` originating from `session.md`. (Children reference `session.md` as a *target*; `session.md` never declares itself as a child of another file.)
- **NOTE:** `sibling` edges originating from `session.md` to present companions **are** emitted by the chunker — this is expected behavior and must NOT be treated as a failure.
- **PASS:** `file_enrichment.file.source_type == "agent-sessions"`.

#### Step 18: Check Logs

- Check logs at `~/.local/share/racochu/logs` to verify the agent-session chunker was selected (look for `Chunker selected: sourceType="agent-sessions"` in the logs).

#### Step 19: Cleanup

- Delete the fixture trees:
  - `rm -rf tmp/agent-sessions/rb-as`
  - `rm -rf tmp/agent-sessions/rb-as2`
- Wait **≥3s** for debounce + forget.
- Recall the queries (`RB_AS_SESSION_TOKEN`, `RB_AS_FINDINGS_TOKEN`, `RB_AS_MATERIALS_TOKEN`, `RB_AS2_CONTRACT_TOKEN`) to confirm memories were cleaned up (0 results).

### Expected Outcomes Summary

| Scenario | Check | Expected |
|----------|-------|----------|
| **S0** (regression) | source_type on companion | `agent-sessions` |
| **S0** (regression) | session.* metadata stamped | All 5 keys present with correct values |
| **S0** (regression) | parent_child edge | Present (findings → session.md) |
| **S0** (regression) | sibling edge | Present (findings → materials) |
| **S0** (regression) | traversal handles | `file_id` + non-empty `relation_ids` |
| **S1** | session.md → materials cross-ref | `cross_reference` edge resolves to materials |
| **S2** | findings.md → 2 cross-refs | Edges to canonical + archived material |
| **S3** | spec.md → 2 cross-refs | Edges to materials + findings |
| **S4** | implementation-plan.md → 2 cross-refs | Edges to materials + findings |
| **S5** | archived spec → materials cross-ref | Edge resolves to materials |
| **S6** | archived findings → archived material | Edge resolves to archived material |
| **S7** | nonexistent ref | NO edge, NO PENDING stub |
| **S8** | self ref | NO self edge |
| **S9** | cross-session ref (A→B) | Edge resolves; B file in A's related_files |
| — | session.md root edges | No outgoing `parent_child`; outgoing `sibling` allowed |
| — | Cleanup | Memories forgotten after file deletion |
